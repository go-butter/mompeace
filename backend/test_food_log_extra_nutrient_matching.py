"""
backend/routers/food_log.py::create_food_log()의 자유 텍스트 추가 성분(extra_nutrients)
이름 매칭 테스트.

핵심 검증 대상:
- 이름이 "지방"과 정확히 일치하고 값이 숫자로 파싱되면 food_log.fat_g에도 반영된다
- 이름이 "콜레스테롤"과 정확히 일치하고 값이 숫자로 파싱되면 food_log.cholesterol_mg에도 반영된다
- 이름이 "철분"과 정확히 일치하고 값이 숫자로 파싱되면 food_log.iron_mg에도 반영된다
- 이름은 일치하지만 값이 숫자로 파싱되지 않으면 크래시 없이 타입 컬럼은 None으로 남는다
- 이름이 알려진 라벨과 일치하지 않으면 타입 컬럼에 영향 없음 (기존 동작 그대로)
- 매칭 여부와 무관하게 모든 항목은 food_log_extra_nutrients에 그대로 저장된다
- food_id 경로에서 이미 구해진 값(food_items 기준)은 자유 텍스트 매칭으로 덮어쓰지 않는다
"""
import sqlite3

from backend.models import ExtraNutrientIn, FoodLogCreate
from backend.routers.food_log import create_food_log

from .conftest import make_food_item, make_user


def _fetch_log(db: sqlite3.Connection, log_id: int) -> dict:
    cursor = db.cursor()
    cursor.execute("SELECT * FROM food_log WHERE log_id = ?", (log_id,))
    return dict(cursor.fetchone())


def _fetch_extra_nutrients(db: sqlite3.Connection, log_id: int) -> list[dict]:
    cursor = db.cursor()
    cursor.execute(
        "SELECT name, value, unit FROM food_log_extra_nutrients WHERE food_log_id = ?",
        (log_id,),
    )
    return [dict(r) for r in cursor.fetchall()]


class TestExtraNutrientNameMatching:
    def test_matching_fat_name_with_numeric_value_populates_fat_g(self, db):
        user_id = make_user(db)
        log = FoodLogCreate(
            user_id=user_id,
            food_name="테스트 음식",
            input_type="manual",
            extra_nutrients=[ExtraNutrientIn(name="지방", value="12.5", unit="g")],
        )
        result = create_food_log(log=log, db=db)
        row = _fetch_log(db, result["log_id"])
        assert row["fat_g"] == 12.5
        assert _fetch_extra_nutrients(db, result["log_id"]) == [
            {"name": "지방", "value": "12.5", "unit": "g"}
        ]

    def test_matching_cholesterol_name_with_numeric_value_populates_cholesterol_mg(self, db):
        user_id = make_user(db)
        log = FoodLogCreate(
            user_id=user_id,
            food_name="테스트 음식",
            input_type="manual",
            extra_nutrients=[ExtraNutrientIn(name="콜레스테롤", value="30", unit="mg")],
        )
        result = create_food_log(log=log, db=db)
        row = _fetch_log(db, result["log_id"])
        assert row["cholesterol_mg"] == 30.0

    def test_matching_iron_name_with_numeric_value_populates_iron_mg(self, db):
        user_id = make_user(db)
        log = FoodLogCreate(
            user_id=user_id,
            food_name="테스트 음식",
            input_type="manual",
            extra_nutrients=[ExtraNutrientIn(name="철분", value="5", unit="mg")],
        )
        result = create_food_log(log=log, db=db)
        row = _fetch_log(db, result["log_id"])
        assert row["iron_mg"] == 5.0

    def test_matching_name_with_non_numeric_value_leaves_column_none(self, db):
        user_id = make_user(db)
        log = FoodLogCreate(
            user_id=user_id,
            food_name="테스트 음식",
            input_type="manual",
            extra_nutrients=[ExtraNutrientIn(name="지방", value="많음", unit=None)],
        )
        result = create_food_log(log=log, db=db)
        row = _fetch_log(db, result["log_id"])
        assert row["fat_g"] is None
        assert _fetch_extra_nutrients(db, result["log_id"]) == [
            {"name": "지방", "value": "많음", "unit": None}
        ]

    def test_non_matching_name_stays_extra_table_only(self, db):
        user_id = make_user(db)
        log = FoodLogCreate(
            user_id=user_id,
            food_name="테스트 음식",
            input_type="manual",
            extra_nutrients=[ExtraNutrientIn(name="칼륨", value="5", unit="mg")],
        )
        result = create_food_log(log=log, db=db)
        row = _fetch_log(db, result["log_id"])
        assert row["fat_g"] is None
        assert row["cholesterol_mg"] is None
        assert row["iron_mg"] is None
        assert _fetch_extra_nutrients(db, result["log_id"]) == [
            {"name": "칼륨", "value": "5", "unit": "mg"}
        ]

    # ── 7개 추적 대상 영양소 중 새로 추가된 5개(탄수화물/당류/에너지/단백질/나트륨) ──

    def test_matching_carbohydrate_name_populates_carbohydrate_g(self, db):
        user_id = make_user(db)
        log = FoodLogCreate(
            user_id=user_id,
            food_name="테스트 음식",
            input_type="manual",
            extra_nutrients=[ExtraNutrientIn(name="탄수화물", value="45.5", unit="g")],
        )
        result = create_food_log(log=log, db=db)
        row = _fetch_log(db, result["log_id"])
        assert row["carbohydrate_g"] == 45.5

    def test_matching_sugar_name_populates_sugar_g(self, db):
        user_id = make_user(db)
        log = FoodLogCreate(
            user_id=user_id,
            food_name="테스트 음식",
            input_type="manual",
            extra_nutrients=[ExtraNutrientIn(name="당류", value="8", unit="g")],
        )
        result = create_food_log(log=log, db=db)
        row = _fetch_log(db, result["log_id"])
        assert row["sugar_g"] == 8.0

    def test_matching_energy_name_populates_calories_kcal(self, db):
        user_id = make_user(db)
        log = FoodLogCreate(
            user_id=user_id,
            food_name="테스트 음식",
            input_type="manual",
            extra_nutrients=[ExtraNutrientIn(name="에너지", value="250", unit="kcal")],
        )
        result = create_food_log(log=log, db=db)
        row = _fetch_log(db, result["log_id"])
        assert row["calories_kcal"] == 250.0

    def test_matching_energy_name_does_not_overwrite_explicit_nonzero_calories(self, db):
        # 이미 값이 명시적으로 전달됐다면(0이든 아니든) 자유 텍스트로 덮어쓰지 않는다 —
        # calories_kcal도 다른 컬럼과 동일하게 None만 "미입력"으로 취급한다.
        user_id = make_user(db)
        log = FoodLogCreate(
            user_id=user_id,
            food_name="테스트 음식",
            input_type="manual",
            calories_kcal=300.0,
            extra_nutrients=[ExtraNutrientIn(name="에너지", value="999", unit="kcal")],
        )
        result = create_food_log(log=log, db=db)
        row = _fetch_log(db, result["log_id"])
        assert row["calories_kcal"] == 300.0

    def test_matching_energy_name_does_not_overwrite_explicit_zero_calories(self, db):
        # 회귀 테스트: 아메리카노처럼 진짜 0kcal인 음식은 명시적으로 calories_kcal=0을
        # 보낸다. _already_known()이 0을 "미입력"으로 취급하던 과거 버그에서는 이
        # 확정된 0이 자유 텍스트 매칭("에너지":"999")에 덮어써졌다 — 이 값이 999로
        # 바뀌면 그 버그가 되돌아온 것이다.
        user_id = make_user(db)
        log = FoodLogCreate(
            user_id=user_id,
            food_name="아메리카노",
            input_type="manual",
            calories_kcal=0.0,
            extra_nutrients=[ExtraNutrientIn(name="에너지", value="999", unit="kcal")],
        )
        result = create_food_log(log=log, db=db)
        row = _fetch_log(db, result["log_id"])
        assert row["calories_kcal"] == 0.0

    def test_matching_protein_name_populates_protein_g(self, db):
        user_id = make_user(db)
        log = FoodLogCreate(
            user_id=user_id,
            food_name="테스트 음식",
            input_type="manual",
            extra_nutrients=[ExtraNutrientIn(name="단백질", value="12", unit="g")],
        )
        result = create_food_log(log=log, db=db)
        row = _fetch_log(db, result["log_id"])
        assert row["protein_g"] == 12.0

    def test_matching_sodium_name_populates_sodium_mg(self, db):
        user_id = make_user(db)
        log = FoodLogCreate(
            user_id=user_id,
            food_name="테스트 음식",
            input_type="manual",
            extra_nutrients=[ExtraNutrientIn(name="나트륨", value="420", unit="mg")],
        )
        result = create_food_log(log=log, db=db)
        row = _fetch_log(db, result["log_id"])
        assert row["sodium_mg"] == 420.0

    def test_food_id_derived_sodium_is_not_overwritten_by_extra_nutrient_match(self, db):
        user_id = make_user(db)
        food_id = make_food_item(db, sodium_mg=100.0)
        log = FoodLogCreate(
            user_id=user_id,
            food_name="무시됨",
            input_type="food_id",
            food_id=food_id,
            amount=1.0,
            extra_nutrients=[ExtraNutrientIn(name="나트륨", value="999", unit="mg")],
        )
        result = create_food_log(log=log, db=db)
        row = _fetch_log(db, result["log_id"])
        # food_items에서 구한 100.0이 유지되어야 한다 (자유 텍스트 999로 덮어쓰면 안 됨)
        assert row["sodium_mg"] == 100.0

    def test_food_id_derived_fat_is_not_overwritten_by_extra_nutrient_match(self, db):
        user_id = make_user(db)
        food_id = make_food_item(db, fat_g=10.0)
        log = FoodLogCreate(
            user_id=user_id,
            food_name="무시됨",
            input_type="food_id",
            food_id=food_id,
            amount=1.0,
            extra_nutrients=[ExtraNutrientIn(name="지방", value="999", unit="g")],
        )
        result = create_food_log(log=log, db=db)
        row = _fetch_log(db, result["log_id"])
        # food_items에서 구한 10.0이 유지되어야 한다 (자유 텍스트 999로 덮어쓰면 안 됨)
        assert row["fat_g"] == 10.0
        assert _fetch_extra_nutrients(db, result["log_id"]) == [
            {"name": "지방", "value": "999", "unit": "g"}
        ]
