"""
user_food_items 테이블, eaten_at 지정 가능 여부, /foods/search 개인 기록 노출 테스트.

핵심 검증 대상:
- POST /foods/personal: 개인 음식 정보 저장 및 중복 방지(dedupe)
- POST /food-log: eaten_at을 지정하면 그 값이 그대로 저장되고, 지정하지 않으면 기존처럼 현재 시각이 적용된다
- GET /foods/search: user_id가 주어지면 개인 기록이 카탈로그 결과보다 먼저 나온다
"""
from datetime import date

import backend.routers.foods as foods_router
from backend.models import FoodLogCreate, UserFoodItemCreate
from backend.routers.food_log import create_food_log
from backend.routers.foods import create_personal_food_item, search_food

from .conftest import make_user, make_user_food_item


class TestCreatePersonalFoodItem:
    def test_roundtrip(self, db):
        user_id = make_user(db)
        item = UserFoodItemCreate(
            user_id=user_id,
            food_name="테스트 요거트",
            caffeine_mg=None,
            sugar_g=8,
            sodium_mg=50,
            calories_kcal=120,
            carbohydrate_g=15,
            protein_g=4,
        )

        result = create_personal_food_item(item=item, db=db)

        assert "user_food_item_id" in result
        cursor = db.cursor()
        cursor.execute(
            "SELECT * FROM user_food_items WHERE user_food_item_id = ?",
            (result["user_food_item_id"],),
        )
        row = dict(cursor.fetchone())
        assert row["food_name"] == "테스트 요거트"
        assert row["sugar_g"] == 8
        assert row["sodium_mg"] == 50
        assert row["calories_kcal"] == 120
        assert row["carbohydrate_g"] == 15
        assert row["protein_g"] == 4

    def test_dedupes_by_user_and_food_name(self, db):
        user_id = make_user(db)
        item = UserFoodItemCreate(user_id=user_id, food_name="중복 음식", sugar_g=5)

        first = create_personal_food_item(item=item, db=db)
        second = create_personal_food_item(item=item, db=db)

        assert first["user_food_item_id"] == second["user_food_item_id"]
        cursor = db.cursor()
        cursor.execute(
            "SELECT COUNT(*) AS cnt FROM user_food_items WHERE user_id = ? AND food_name = ?",
            (user_id, "중복 음식"),
        )
        assert cursor.fetchone()["cnt"] == 1


class TestCreateFoodLogEatenAt:
    def test_explicit_eaten_at_is_preserved(self, db):
        user_id = make_user(db)
        log = FoodLogCreate(
            user_id=user_id,
            food_name="과거 기록",
            input_type="manual",
            eaten_at="2026-06-19 08:00:00",
        )

        result = create_food_log(log=log, db=db)

        cursor = db.cursor()
        cursor.execute("SELECT eaten_at FROM food_log WHERE log_id = ?", (result["log_id"],))
        assert cursor.fetchone()["eaten_at"] == "2026-06-19 08:00:00"

    def test_omitted_eaten_at_defaults_to_now(self, db):
        user_id = make_user(db)
        log = FoodLogCreate(user_id=user_id, food_name="오늘 기록", input_type="manual")

        result = create_food_log(log=log, db=db)

        cursor = db.cursor()
        cursor.execute("SELECT eaten_at FROM food_log WHERE log_id = ?", (result["log_id"],))
        eaten_at = cursor.fetchone()["eaten_at"]
        assert eaten_at.startswith(date.today().isoformat())


class TestSearchFoodPersonalResults:
    def test_personal_item_appears_first_when_user_id_given(self, db, monkeypatch):
        monkeypatch.setattr(foods_router, "search_food_nutrition", lambda **kwargs: [])
        user_id = make_user(db)
        make_user_food_item(db, user_id, food_name="아메리카노 개인", caffeine_mg=150)

        result = search_food(query="아메리카노", pregnancy_week=20, page_no=1, num_of_rows=10, user_id=user_id, db=db)

        assert result["results"][0]["source"] == "personal"
        assert result["results"][0]["data"]["food_name"] == "아메리카노 개인"

    def test_no_user_id_returns_only_catalog_results(self, db, monkeypatch):
        monkeypatch.setattr(foods_router, "search_food_nutrition", lambda **kwargs: [])
        other_user_id = make_user(db)
        make_user_food_item(db, other_user_id, food_name="아메리카노 개인", caffeine_mg=150)

        result = search_food(query="아메리카노", pregnancy_week=20, page_no=1, num_of_rows=10, user_id=None, db=db)

        assert all(r["source"] != "personal" for r in result["results"])
