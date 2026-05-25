"""
dish_nutrition_db Excel → food_items 임포트 스크립트

실행 방법:
    python -m backend.import_dish_db
"""
import json
import sqlite3
from pathlib import Path

import pandas as pd

_HERE = Path(__file__).resolve().parent
EXCEL_PATH = _HERE / "data" / "dish_nutrition_db_20251229.xlsx"
PROJECT_ROOT = _HERE.parent
DB_PATH = PROJECT_ROOT / "mompeace.db"

DATA_SOURCE = "dish_db_download"

# Excel 컬럼 → food_items 컬럼 매핑
COLUMN_MAP = {
    "식품코드": "food_code",
    "식품명": "food_name",
    "식품대분류명": "category",
    "영양성분함량기준량": "serving_label",
    "단백질(g)": "protein_g",
    "탄수화물(g)": "carbohydrate_g",
    "당류(g)": "sugar_g",
    "나트륨(mg)": "sodium_mg",
    "카페인(mg)": "caffeine_mg",
}

# 대표식품명 or 식품소분류명 → subcategory (순서대로 시도)
SUBCATEGORY_CANDIDATES = ["대표식품명", "식품소분류명"]

# notes 에 포함할 메타 컬럼
NOTES_COLUMNS = ["데이터기준일자", "데이터생성일자", "제공처명", "DB구분명", "데이터구분명"]

# 필수 컬럼
REQUIRED_COLUMNS = {"식품명"}

# 숫자로 변환할 컬럼
NUMERIC_COLUMNS = {"단백질(g)", "탄수화물(g)", "당류(g)", "나트륨(mg)", "카페인(mg)"}

MISSING_VALUES = {"", "-", "N/A", "n/a"}


def _to_float_or_none(value) -> float | None:
    """빈 값·대시·NaN → None, 나머지 → float"""
    if value is None:
        return None
    if isinstance(value, float):
        import math
        if math.isnan(value):
            return None
        return value
    s = str(value).strip()
    if s in MISSING_VALUES:
        return None
    try:
        return float(s)
    except (ValueError, TypeError):
        return None


def _clean_text(value) -> str:
    if value is None:
        return ""
    return str(value).replace("﻿", "").strip()


def main():
    if not EXCEL_PATH.exists():
        print(f"❌ Excel 파일을 찾을 수 없습니다: {EXCEL_PATH}")
        return

    # ── Excel 읽기 ──────────────────────────────────────────
    try:
        df = pd.read_excel(EXCEL_PATH, dtype=str)
    except Exception as e:
        print(f"❌ Excel 읽기 실패: {e}")
        return

    # BOM 제거 (컬럼명 첫 글자에 붙는 경우)
    df.columns = [c.replace("﻿", "").strip() for c in df.columns]

    # 필수 컬럼 확인
    missing_required = REQUIRED_COLUMNS - set(df.columns)
    if missing_required:
        print(f"❌ Excel에 필수 컬럼이 없습니다: {missing_required}")
        print(f"   실제 컬럼 목록: {list(df.columns)}")
        return

    total_rows = len(df)
    print(f"전체 엑셀 행 수: {total_rows}")

    # subcategory 컬럼 결정
    subcategory_col = None
    for cand in SUBCATEGORY_CANDIDATES:
        if cand in df.columns:
            subcategory_col = cand
            break

    # ── DB 연결 ─────────────────────────────────────────────
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    insert_count = 0
    update_count = 0
    skip_count = 0
    caffeine_has = 0
    caffeine_missing = 0

    for _, excel_row in df.iterrows():
        try:
            # food_name 정제
            food_name = _clean_text(excel_row.get("식품명", ""))
            if not food_name:
                skip_count += 1
                continue

            # 기본 필드
            food_code_raw = _clean_text(excel_row.get("식품코드", "")) or None
            category = _clean_text(excel_row.get("식품대분류명", "")) or None
            serving_label = _clean_text(excel_row.get("영양성분함량기준량", "")) or None
            subcategory = (
                _clean_text(excel_row.get(subcategory_col, "")) or None
                if subcategory_col else None
            )

            # 영양소 (None = 미기재)
            protein_g = _to_float_or_none(excel_row.get("단백질(g)"))
            carbohydrate_g = _to_float_or_none(excel_row.get("탄수화물(g)"))
            sugar_g = _to_float_or_none(excel_row.get("당류(g)"))
            sodium_mg = _to_float_or_none(excel_row.get("나트륨(mg)"))
            caffeine_mg = _to_float_or_none(excel_row.get("카페인(mg)"))

            if caffeine_mg is not None:
                caffeine_has += 1
            else:
                caffeine_missing += 1

            # notes: 메타 컬럼 JSON 직렬화
            notes_dict = {}
            for col in NOTES_COLUMNS:
                if col in excel_row.index:
                    v = _clean_text(excel_row.get(col, ""))
                    if v:
                        notes_dict[col] = v
            notes = json.dumps(notes_dict, ensure_ascii=False) if notes_dict else None

        except Exception as e:
            print(f"  ⚠️ 행 변환 오류 (skip): {e}")
            skip_count += 1
            continue

        # ── 중복 체크 및 INSERT/UPDATE ────────────────────────
        try:
            existing_id = None

            if food_code_raw:
                cursor.execute(
                    "SELECT food_id FROM food_items "
                    "WHERE food_code = ? AND data_source = ?",
                    (food_code_raw, DATA_SOURCE),
                )
                row = cursor.fetchone()
                if row:
                    existing_id = row["food_id"]

            if existing_id is None:
                cursor.execute(
                    "SELECT food_id FROM food_items "
                    "WHERE food_name = ? AND data_source = ?",
                    (food_name, DATA_SOURCE),
                )
                row = cursor.fetchone()
                if row:
                    existing_id = row["food_id"]

            if existing_id is not None:
                cursor.execute("""
                    UPDATE food_items SET
                        food_code      = ?,
                        food_name      = ?,
                        category       = ?,
                        subcategory    = ?,
                        serving_label  = ?,
                        protein_g      = ?,
                        carbohydrate_g = ?,
                        sugar_g        = ?,
                        sodium_mg      = ?,
                        caffeine_mg    = ?,
                        notes          = ?,
                        updated_at     = datetime('now')
                    WHERE food_id = ?
                """, (
                    food_code_raw, food_name, category, subcategory,
                    serving_label, protein_g, carbohydrate_g, sugar_g,
                    sodium_mg, caffeine_mg, notes, existing_id,
                ))
                update_count += 1
            else:
                cursor.execute("""
                    INSERT INTO food_items (
                        food_code, food_name, category, subcategory,
                        serving_label, protein_g, carbohydrate_g,
                        sugar_g, sodium_mg, caffeine_mg,
                        data_source, notes, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
                """, (
                    food_code_raw, food_name, category, subcategory,
                    serving_label, protein_g, carbohydrate_g,
                    sugar_g, sodium_mg, caffeine_mg,
                    DATA_SOURCE, notes,
                ))
                insert_count += 1

        except Exception as e:
            print(f"  ⚠️ DB 쓰기 오류 (skip): {food_name!r} — {e}")
            skip_count += 1
            continue

    conn.commit()
    conn.close()

    print(f"insert: {insert_count}")
    print(f"update: {update_count}")
    print(f"skip: {skip_count}")
    print(f"카페인 값 있음: {caffeine_has}")
    print(f"카페인 값 없음: {caffeine_missing}")
    print("✅ dish_db_download 임포트 완료")


if __name__ == "__main__":
    main()
