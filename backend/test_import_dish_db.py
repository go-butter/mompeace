"""
backend/import_dish_db.py 테스트.

핵심 검증 대상:
- 영양성분함량기준량 대비 식품중량으로 스케일이 정확히 계산/적용된다
- 기준량 또는 식품중량이 없으면 스케일을 적용하지 않고 raw 값을 유지하며,
  이 사실이 unscaled_count로 집계된다
- 영양소 원본 값이 None이면 스케일이 있어도 결과는 항상 None이다
- 재임포트 시 food_code가 매칭되는 행은 food_id가 보존된다 (UPDATE, not
  DROP+INSERT) — food_log.food_id 참조가 깨지지 않아야 하기 때문
- xlsx에서 사라진 food_code는 같은 data_source 범위 내에서만 삭제된다
"""
import sqlite3

import pandas as pd
import pytest

from backend import import_dish_db


# ── 순수 함수 단위 테스트 (영양성분함량기준량/식품중량 전용 파서) ──

def test_parse_weight_value_grams():
    assert import_dish_db._parse_weight_value("100g") == 100.0


def test_parse_weight_value_ml():
    assert import_dish_db._parse_weight_value("532ml") == 532.0


def test_parse_weight_value_decimal_grams():
    assert import_dish_db._parse_weight_value("462.60g") == pytest.approx(462.60)


def test_parse_weight_value_with_space_before_unit():
    assert import_dish_db._parse_weight_value("100 ml") == 100.0


def test_parse_weight_value_unparseable_returns_none():
    assert import_dish_db._parse_weight_value("알수없음") is None


def test_parse_weight_value_missing_marker_returns_none():
    assert import_dish_db._parse_weight_value("-") is None
    assert import_dish_db._parse_weight_value(None) is None


def test_parse_weight_value_pure_number_still_works():
    assert import_dish_db._parse_weight_value("100") == 100.0


# ── 순수 함수 단위 테스트 (스케일 계산 / 적용) ──────────────────

def test_compute_scale_basic_ratio():
    assert import_dish_db._compute_scale(100.0, 355.0) == pytest.approx(3.55)


def test_compute_scale_missing_basis_returns_none():
    assert import_dish_db._compute_scale(None, 355.0) is None


def test_compute_scale_missing_weight_returns_none():
    assert import_dish_db._compute_scale(100.0, None) is None


def test_compute_scale_zero_basis_returns_none():
    assert import_dish_db._compute_scale(0.0, 355.0) is None


def test_scale_applied_when_basis_and_weight_present():
    scale = import_dish_db._compute_scale(100.0, 355.0)
    assert import_dish_db._scale(10.0, scale) == pytest.approx(35.5)


def test_missing_weight_leaves_raw_value():
    scale = import_dish_db._compute_scale(100.0, None)
    assert import_dish_db._scale(10.0, scale) == 10.0


def test_missing_basis_leaves_raw_value():
    scale = import_dish_db._compute_scale(None, 355.0)
    assert import_dish_db._scale(10.0, scale) == 10.0


def test_null_nutrient_stays_null_through_scaling():
    scale = import_dish_db._compute_scale(100.0, 355.0)
    assert import_dish_db._scale(None, scale) is None


def test_null_nutrient_stays_null_when_unscaled():
    assert import_dish_db._scale(None, None) is None


# ── main() 통합 테스트 (임시 xlsx + 임시 sqlite db) ──────────────

FOOD_ITEMS_SCHEMA = """
CREATE TABLE food_items (
    food_id        INTEGER PRIMARY KEY AUTOINCREMENT,
    food_code      TEXT,
    food_name      TEXT NOT NULL,
    food_name_en   TEXT,
    barcode        TEXT,
    category       TEXT,
    subcategory    TEXT,
    serving_size_g REAL,
    serving_label  TEXT,
    caffeine_mg    REAL,
    sugar_g        REAL,
    sodium_mg      REAL,
    calories_kcal  REAL,
    carbohydrate_g REAL,
    protein_g      REAL,
    allergen_info  TEXT,
    additive_info  TEXT,
    data_source    TEXT,
    notes          TEXT,
    updated_at     TEXT DEFAULT (datetime('now'))
);
"""

XLSX_COLUMNS = [
    "식품코드", "식품명", "식품대분류명", "대표식품명",
    "영양성분함량기준량", "식품중량",
    "단백질(g)", "탄수화물(g)", "당류(g)", "나트륨(mg)", "카페인(mg)",
]


def _make_row(food_code, food_name, basis, weight, caffeine):
    return {
        "식품코드": food_code,
        "식품명": food_name,
        "식품대분류명": "테스트분류",
        "대표식품명": "",
        "영양성분함량기준량": basis,
        "식품중량": weight,
        "단백질(g)": "1",
        "탄수화물(g)": "2",
        "당류(g)": "3",
        "나트륨(mg)": "4",
        "카페인(mg)": caffeine,
    }


@pytest.fixture
def import_env(tmp_path, monkeypatch):
    """EXCEL_PATH/DB_PATH를 임시 파일로 바꾸고, food_items 스키마를 미리 만들어둔다."""
    db_path = tmp_path / "test.db"
    conn = sqlite3.connect(str(db_path))
    conn.executescript(FOOD_ITEMS_SCHEMA)
    conn.commit()
    conn.close()

    monkeypatch.setattr(import_dish_db, "DB_PATH", db_path)

    def _write_xlsx(rows):
        xlsx_path = tmp_path / "dish.xlsx"
        df = pd.DataFrame(rows, columns=XLSX_COLUMNS)
        df.to_excel(xlsx_path, index=False)
        monkeypatch.setattr(import_dish_db, "EXCEL_PATH", xlsx_path)

    return db_path, _write_xlsx


def _query_food_items(db_path):
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM food_items")
    rows = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return rows


def test_import_scales_nutrients_by_food_weight_ratio(import_env, capsys):
    db_path, write_xlsx = import_env
    write_xlsx([_make_row("F001", "테스트음식", "100g", "355g", "10")])

    import_dish_db.main()

    rows = _query_food_items(db_path)
    assert len(rows) == 1
    # scale = 355/100 = 3.55, caffeine 10 * 3.55 = 35.5
    assert rows[0]["caffeine_mg"] == pytest.approx(35.5)
    assert rows[0]["sugar_g"] == pytest.approx(3 * 3.55)


def test_import_missing_weight_row_left_unscaled_and_flagged(import_env, capsys):
    db_path, write_xlsx = import_env
    write_xlsx([_make_row("F002", "기준량만있음", "100g", "-", "10")])

    import_dish_db.main()

    rows = _query_food_items(db_path)
    assert rows[0]["caffeine_mg"] == 10.0  # raw 값 그대로

    out = capsys.readouterr().out
    assert "스케일 미적용 (raw 값 유지): 1" in out
    assert "스케일 계산 불가" in out


def test_import_null_caffeine_stays_null_even_when_scaled(import_env):
    db_path, write_xlsx = import_env
    write_xlsx([_make_row("F003", "카페인없음", "100g", "355g", "-")])

    import_dish_db.main()

    rows = _query_food_items(db_path)
    assert rows[0]["caffeine_mg"] is None


def test_reimport_preserves_food_id_for_matched_food_code(import_env):
    db_path, write_xlsx = import_env
    write_xlsx([_make_row("F004", "재수입테스트", "100g", "355g", "10")])
    import_dish_db.main()
    first_pass = _query_food_items(db_path)
    original_id = first_pass[0]["food_id"]

    # 같은 food_code, 값만 변경된 두 번째 임포트
    write_xlsx([_make_row("F004", "재수입테스트", "100g", "710g", "10")])
    import_dish_db.main()
    second_pass = _query_food_items(db_path)

    assert len(second_pass) == 1
    assert second_pass[0]["food_id"] == original_id
    # scale = 710/100 = 7.1
    assert second_pass[0]["caffeine_mg"] == pytest.approx(71.0)


def test_stale_food_code_removed_on_reimport_scoped_to_data_source(import_env):
    db_path, write_xlsx = import_env
    write_xlsx([
        _make_row("F005", "곧사라질음식", "100g", "355g", "10"),
        _make_row("F006", "계속남을음식", "100g", "355g", "10"),
    ])
    import_dish_db.main()

    # dish_db_download가 아닌 다른 출처의 행 (건드리면 안 됨)
    conn = sqlite3.connect(str(db_path))
    conn.execute(
        "INSERT INTO food_items (food_code, food_name, data_source) "
        "VALUES ('F005', '다른출처음식', 'manual_test')"
    )
    conn.commit()
    conn.close()

    # F005가 사라진 새 xlsx로 재임포트
    write_xlsx([_make_row("F006", "계속남을음식", "100g", "355g", "10")])
    import_dish_db.main()

    rows = _query_food_items(db_path)
    codes_and_sources = {(r["food_code"], r["data_source"]) for r in rows}

    assert ("F006", "dish_db_download") in codes_and_sources
    assert ("F005", "dish_db_download") not in codes_and_sources
    # 다른 data_source의 F005는 그대로 남아 있어야 한다
    assert ("F005", "manual_test") in codes_and_sources
