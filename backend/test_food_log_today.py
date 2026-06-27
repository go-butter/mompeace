"""
backend/main.py 의 get_today_food_log() 테스트.

핵심 검증 대상:
- sugar_g/sodium_mg/caffeine_mg/protein_g가 food_log 행에서 그대로 반환된다
- food_id가 있으면 food_items.allergen_info를 리스트로 파싱해 allergens로 반환한다
- food_id가 없으면 allergens는 빈 리스트다 (None이 아니고, 에러도 아니다)
"""
from datetime import date

from backend.main import get_today_food_log

from .conftest import make_food_log, make_user


def _make_food_item(db, **overrides):
    defaults = {
        "food_name": "테스트 식품",
        "allergen_info": None,
    }
    defaults.update(overrides)
    cols = ", ".join(defaults.keys())
    placeholders = ", ".join("?" for _ in defaults)
    cursor = db.cursor()
    cursor.execute(
        f"INSERT INTO food_items ({cols}) VALUES ({placeholders})",
        list(defaults.values()),
    )
    db.commit()
    return cursor.lastrowid


class TestGetTodayFoodLog:
    def test_entry_with_food_id_includes_nutrients_and_allergens(self, db):
        user_id = make_user(db)
        food_id = _make_food_item(db, allergen_info="우유, 대두")
        today_dt = date.today().isoformat() + " 12:00:00"
        make_food_log(
            db,
            user_id,
            food_id=food_id,
            food_name="요거트",
            sugar_g=8,
            sodium_mg=95,
            caffeine_mg=10,
            protein_g=4,
            eaten_at=today_dt,
        )

        result = get_today_food_log(user_id=user_id, db=db)

        assert result["count"] == 1
        entry = result["logs"][0]
        assert entry["sugar_g"] == 8
        assert entry["sodium_mg"] == 95
        assert entry["caffeine_mg"] == 10
        assert entry["protein_g"] == 4
        assert entry["allergens"] == ["우유", "대두"]

    def test_entry_without_food_id_has_empty_allergens(self, db):
        user_id = make_user(db)
        today_dt = date.today().isoformat() + " 09:30:00"
        make_food_log(
            db,
            user_id,
            food_id=None,
            food_name="직접 입력 음식",
            sugar_g=3,
            sodium_mg=50,
            caffeine_mg=None,
            protein_g=1,
            eaten_at=today_dt,
        )

        result = get_today_food_log(user_id=user_id, db=db)

        assert result["count"] == 1
        entry = result["logs"][0]
        assert entry["allergens"] == []
        assert entry["sugar_g"] == 3
        assert entry["sodium_mg"] == 50
        assert entry["caffeine_mg"] is None
        assert entry["protein_g"] == 1
