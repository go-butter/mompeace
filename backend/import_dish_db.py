"""
dish_nutrition_db Excel → food_items 임포트 스크립트

실행 방법:
    python -m backend.import_dish_db
"""
from __future__ import annotations
import json
import re
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
    "에너지(kcal)": "calories_kcal",
    "단백질(g)": "protein_g",
    "지방(g)": "fat_g",
    "탄수화물(g)": "carbohydrate_g",
    "당류(g)": "sugar_g",
    "나트륨(mg)": "sodium_mg",
    "카페인(mg)": "caffeine_mg",
    "포화지방산(g)": "saturated_fat_g",
    "트랜스지방산(g)": "trans_fat_g",
    "콜레스테롤(mg)": "cholesterol_mg",
}

# 대표식품명 or 식품소분류명 → subcategory (순서대로 시도)
SUBCATEGORY_CANDIDATES = ["대표식품명", "식품소분류명"]

# notes 에 포함할 메타 컬럼
NOTES_COLUMNS = ["데이터기준일자", "데이터생성일자", "제공처명", "DB구분명", "데이터구분명"]

# 필수 컬럼
REQUIRED_COLUMNS = {"식품명"}

# 숫자로 변환할 컬럼
NUMERIC_COLUMNS = {
    "에너지(kcal)", "단백질(g)", "지방(g)", "탄수화물(g)", "당류(g)",
    "나트륨(mg)", "카페인(mg)",
    "포화지방산(g)", "트랜스지방산(g)", "콜레스테롤(mg)",
}

# 실제 식품 중량 (영양성분함량기준량과 다를 수 있음 — 스케일링용, COLUMN_MAP에는 없음)
FOOD_WEIGHT_COLUMN = "식품중량"

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


_LEADING_NUMBER_RE = re.compile(r"[-+]?\d+(?:\.\d+)?")


def _parse_weight_value(value) -> float | None:
    """
    영양성분함량기준량/식품중량 전용 파서.
    "100g", "532ml", "462.60g", "100 ml" 처럼 단위(g/ml)가 붙은 값에서
    맨 앞의 숫자(소수 포함) 부분만 뽑아 float로 변환한다.
    숫자 부분이 전혀 없으면 None. (단백질/탄수화물/... 5개 영양소 컬럼에
    쓰이는 _to_float_or_none()과는 별개 — 그쪽은 순수 숫자 문자열만 다루므로
    그대로 둔다.)
    """
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
    match = _LEADING_NUMBER_RE.search(s)
    if not match:
        return None
    try:
        return float(match.group())
    except ValueError:
        return None


def _compute_scale(basis_amount: float | None, food_weight: float | None) -> float | None:
    """
    영양성분함량기준량(basis_amount) 대비 실제 식품중량(food_weight)의 배율.
    둘 중 하나라도 없거나 basis_amount 또는 food_weight가 0 이하면 스케일을 계산할 수 없음 (None).
    """
    if basis_amount is None or food_weight is None or basis_amount <= 0 or food_weight <= 0:
        return None
    return food_weight / basis_amount


def _scale(value: float | None, scale: float | None) -> float | None:
    """None은 그대로 None 유지. scale이 없으면 raw 값 그대로 반환.
    스케일 곱셈 후 소수점 2자리로 반올림해 부동소수점 오차(예: 405.59999999999997)를 제거한다."""
    if value is None or scale is None:
        return value
    return round(value * scale, 2)


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
    unscaled_count = 0

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

            # 영양성분함량기준량 대비 실제 식품중량 스케일 계산
            # (기준량과 식품중량이 다른 경우가 93%+ — 스케일 없이는 영양소가
            #  최대 ~30배까지 과소/과대 보고됨)
            basis_amount = _parse_weight_value(excel_row.get("영양성분함량기준량"))
            food_weight = _parse_weight_value(excel_row.get(FOOD_WEIGHT_COLUMN))

            # 같은 food_name이라도 food_code가 다른 행(예: 다른 매장의 "아메리카노")을
            # 구분할 수 있도록 실제 식품중량을 이름에 라벨로 붙인다. food_weight를
            # 파싱할 수 없는 행은 라벨 없이 원래 이름을 그대로 둔다.
            if food_weight is not None:
                weight_label = _clean_text(excel_row.get(FOOD_WEIGHT_COLUMN))
                food_name = f"{food_name} ({weight_label})"

            scale = _compute_scale(basis_amount, food_weight)
            if scale is None:
                unscaled_count += 1
                print(
                    f"  ⚠️ 스케일 계산 불가 (raw 값 사용): {food_name!r} "
                    f"기준량={excel_row.get('영양성분함량기준량')!r} "
                    f"식품중량={excel_row.get(FOOD_WEIGHT_COLUMN)!r}"
                )

            # 영양소 (None = 미기재, 스케일 적용 후에도 None 유지)
            calories_kcal = _scale(_to_float_or_none(excel_row.get("에너지(kcal)")), scale)
            protein_g = _scale(_to_float_or_none(excel_row.get("단백질(g)")), scale)
            fat_g = _scale(_to_float_or_none(excel_row.get("지방(g)")), scale)
            carbohydrate_g = _scale(_to_float_or_none(excel_row.get("탄수화물(g)")), scale)
            sugar_g = _scale(_to_float_or_none(excel_row.get("당류(g)")), scale)
            sodium_mg = _scale(_to_float_or_none(excel_row.get("나트륨(mg)")), scale)
            caffeine_mg = _scale(_to_float_or_none(excel_row.get("카페인(mg)")), scale)
            saturated_fat_g = _scale(_to_float_or_none(excel_row.get("포화지방산(g)")), scale)
            trans_fat_g = _scale(_to_float_or_none(excel_row.get("트랜스지방산(g)")), scale)
            cholesterol_mg = _scale(_to_float_or_none(excel_row.get("콜레스테롤(mg)")), scale)

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

            if existing_id is not None:
                cursor.execute("""
                    UPDATE food_items SET
                        food_code      = ?,
                        food_name      = ?,
                        category       = ?,
                        subcategory    = ?,
                        serving_label  = ?,
                        calories_kcal  = ?,
                        protein_g      = ?,
                        fat_g          = ?,
                        carbohydrate_g = ?,
                        sugar_g        = ?,
                        sodium_mg      = ?,
                        caffeine_mg    = ?,
                        saturated_fat_g = ?,
                        trans_fat_g    = ?,
                        cholesterol_mg = ?,
                        notes          = ?,
                        updated_at     = datetime('now')
                    WHERE food_id = ?
                """, (
                    food_code_raw, food_name, category, subcategory,
                    serving_label, calories_kcal, protein_g, fat_g,
                    carbohydrate_g, sugar_g, sodium_mg, caffeine_mg,
                    saturated_fat_g, trans_fat_g, cholesterol_mg,
                    notes, existing_id,
                ))
                update_count += 1
            else:
                cursor.execute("""
                    INSERT INTO food_items (
                        food_code, food_name, category, subcategory,
                        serving_label, calories_kcal, protein_g, fat_g,
                        carbohydrate_g, sugar_g, sodium_mg, caffeine_mg,
                        saturated_fat_g, trans_fat_g, cholesterol_mg,
                        data_source, notes, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
                """, (
                    food_code_raw, food_name, category, subcategory,
                    serving_label, calories_kcal, protein_g, fat_g,
                    carbohydrate_g, sugar_g, sodium_mg, caffeine_mg,
                    saturated_fat_g, trans_fat_g, cholesterol_mg,
                    DATA_SOURCE, notes,
                ))
                insert_count += 1

        except Exception as e:
            print(f"  ⚠️ DB 쓰기 오류 (skip): {food_name!r} — {e}")
            skip_count += 1
            continue

    # ── xlsx에서 사라진 food_code 정리 (data_source 범위 한정) ──────
    # DROP+재삽입 대신 UPDATE/INSERT로 food_id를 보존한 뒤, 더 이상
    # xlsx에 없는 dish_db_download 행만 삭제한다 (다른 data_source나
    # food_log가 참조 중인 food_id의 불필요한 churn을 피하기 위함).
    xlsx_food_codes = {
        _clean_text(v) for v in df["식품코드"].dropna() if _clean_text(v)
    }
    cursor.execute(
        "SELECT food_id, food_code FROM food_items WHERE data_source = ?",
        (DATA_SOURCE,),
    )
    stale_ids = [
        row["food_id"] for row in cursor.fetchall()
        if row["food_code"] and row["food_code"] not in xlsx_food_codes
    ]
    if stale_ids:
        cursor.executemany(
            "DELETE FROM food_items WHERE food_id = ?",
            [(i,) for i in stale_ids],
        )

    conn.commit()
    conn.close()

    print(f"insert: {insert_count}")
    print(f"update: {update_count}")
    print(f"skip: {skip_count}")
    print(f"카페인 값 있음: {caffeine_has}")
    print(f"카페인 값 없음: {caffeine_missing}")
    print(f"스케일 미적용 (raw 값 유지): {unscaled_count}")
    print(f"삭제된 stale food_code: {len(stale_ids)}")
    print("✅ dish_db_download 임포트 완료")


if __name__ == "__main__":
    main()
