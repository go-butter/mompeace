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
- food_code만으로 매칭한다 (food_name 폴백 없음) — 같은 food_name이라도
  food_code가 다르면 서로 다른 행으로 보존된다
- food_name에는 실제 식품중량이 "(<중량><단위>)" 형식으로 라벨로 붙는다.
  식품중량을 파싱할 수 없는 행은 라벨 없이 원래 이름 그대로 저장된다
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


def test_compute_scale_zero_weight_returns_none():
    assert import_dish_db._compute_scale(100.0, 0.0) is None


def test_compute_scale_negative_weight_returns_none():
    assert import_dish_db._compute_scale(100.0, -50.0) is None


def test_compute_scale_ratio_one_is_noop():
    scale = import_dish_db._compute_scale(100.0, 100.0)
    assert scale == 1.0
    assert import_dish_db._scale(42.25, scale) == 42.25


def test_compute_scale_ignores_unit_label_mismatch_known_limitation():
    """
    _parse_weight_value는 g/ml 단위 라벨을 버리고 숫자만 취하므로, 기준량과
    식품중량의 단위가 실제로 다르더라도(예: g vs ml) 검증 없이 비율을 계산한다.
    현재 xlsx 19,495행 전수 확인 결과 기준량/식품중량 단위가 어긋나는 행은
    0건이라 지금은 발생하지 않지만, 향후 데이터에 섞인 단위 행이 들어올 경우
    이 동작이 그대로 적용된다는 것을 명시적으로 고정해두는 회귀 테스트
    (단위 변환 로직은 의도적으로 추가하지 않음 — 알려진 한계).
    """
    basis = import_dish_db._parse_weight_value("100g")
    weight = import_dish_db._parse_weight_value("355ml")
    scale = import_dish_db._compute_scale(basis, weight)
    assert scale == pytest.approx(3.55)


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
    fat_g          REAL,
    saturated_fat_g REAL,
    trans_fat_g    REAL,
    cholesterol_mg REAL,
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
    "에너지(kcal)", "단백질(g)", "지방(g)", "탄수화물(g)", "당류(g)",
    "나트륨(mg)", "카페인(mg)",
]


def _make_row(food_code, food_name, basis, weight, caffeine):
    return {
        "식품코드": food_code,
        "식품명": food_name,
        "식품대분류명": "테스트분류",
        "대표식품명": "",
        "영양성분함량기준량": basis,
        "식품중량": weight,
        "에너지(kcal)": "50",
        "단백질(g)": "1",
        "지방(g)": "5",
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
    assert rows[0]["calories_kcal"] == pytest.approx(50 * 3.55)
    assert rows[0]["fat_g"] == pytest.approx(5 * 3.55)


def test_import_missing_weight_row_left_unscaled_and_flagged(import_env, capsys):
    db_path, write_xlsx = import_env
    write_xlsx([_make_row("F002", "기준량만있음", "100g", "-", "10")])

    import_dish_db.main()

    rows = _query_food_items(db_path)
    assert rows[0]["caffeine_mg"] == 10.0  # raw 값 그대로

    out = capsys.readouterr().out
    assert "스케일 미적용 (raw 값 유지): 1" in out
    assert "스케일 계산 불가" in out


def test_import_zero_weight_row_left_unscaled_and_flagged(import_env, capsys):
    db_path, write_xlsx = import_env
    write_xlsx([_make_row("F007", "식품중량0", "100g", "0g", "10")])

    import_dish_db.main()

    rows = _query_food_items(db_path)
    assert rows[0]["caffeine_mg"] == 10.0  # raw 값 그대로, 0으로 덮이지 않음

    out = capsys.readouterr().out
    assert "스케일 미적용 (raw 값 유지): 1" in out


def test_import_appends_weight_label_to_food_name(import_env):
    db_path, write_xlsx = import_env
    write_xlsx([_make_row("F012", "테스트음식", "100g", "355g", "10")])

    import_dish_db.main()

    rows = _query_food_items(db_path)
    assert rows[0]["food_name"] == "테스트음식 (355g)"


def test_import_weight_label_preserves_ml_unit(import_env):
    db_path, write_xlsx = import_env
    write_xlsx([_make_row("F013", "테스트음료", "100ml", "591ml", "10")])

    import_dish_db.main()

    rows = _query_food_items(db_path)
    assert rows[0]["food_name"] == "테스트음료 (591ml)"


def test_import_unparseable_weight_leaves_food_name_unlabeled(import_env):
    db_path, write_xlsx = import_env
    write_xlsx([_make_row("F014", "기준량만있음", "100g", "-", "10")])

    import_dish_db.main()

    rows = _query_food_items(db_path)
    assert rows[0]["food_name"] == "기준량만있음"


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


def test_distinct_food_codes_with_same_name_are_not_collapsed(import_env):
    """food_name이 같아도 food_code가 다르면 서로 다른 행으로 보존된다
    (food_name 폴백 매칭 제거 확인)."""
    db_path, write_xlsx = import_env
    write_xlsx([
        _make_row("F010", "아메리카노", "100g", "355g", "40"),
        _make_row("F011", "아메리카노", "100g", "591g", "30"),
    ])

    import_dish_db.main()

    rows = _query_food_items(db_path)
    assert len(rows) == 2
    codes = {r["food_code"] for r in rows}
    assert codes == {"F010", "F011"}


def test_reimport_on_unchanged_xlsx_is_idempotent_with_duplicate_names(import_env):
    """food_code로만 매칭하므로, 이름이 같은 두 행이 있어도 변경 없는 xlsx를
    재실행하면 행 수·food_id·값이 완전히 동일하게 유지된다 (서로 덮어쓰지 않음)."""
    db_path, write_xlsx = import_env
    rows_in = [
        _make_row("F020", "아메리카노", "100g", "355g", "40"),
        _make_row("F021", "아메리카노", "100g", "591g", "30"),
        _make_row("F022", "다른음식", "100g", "200g", "5"),
    ]
    write_xlsx(rows_in)
    import_dish_db.main()
    first_pass = {r["food_code"]: dict(r) for r in _query_food_items(db_path)}

    write_xlsx(rows_in)  # 동일한 xlsx로 재실행
    import_dish_db.main()
    second_pass = {r["food_code"]: dict(r) for r in _query_food_items(db_path)}

    assert len(first_pass) == 3
    assert first_pass.keys() == second_pass.keys()
    for code in first_pass:
        assert first_pass[code]["food_id"] == second_pass[code]["food_id"]
        assert first_pass[code]["caffeine_mg"] == second_pass[code]["caffeine_mg"]
        assert first_pass[code]["food_name"] == second_pass[code]["food_name"]


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
