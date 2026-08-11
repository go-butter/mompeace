"""
backend/main.py 의 get_today_food_log() 테스트.

핵심 검증 대상:
- sugar_g/sodium_mg/caffeine_mg/protein_g가 food_log 행에서 그대로 반환된다
"""
from datetime import date

from backend.routers.food_log import get_today_food_log
from backend.models import FoodLogCreate
from backend.routers.food_log import create_food_log

from .conftest import make_food_log, make_user


def _make_food_item(db, **overrides):
    defaults = {
        "food_name": "테스트 식품",
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
    def test_entry_with_food_id_includes_nutrients(self, db):
        user_id = make_user(db)
        food_id = _make_food_item(db)
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

    def test_entry_without_food_id_includes_nutrients(self, db):
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
        assert entry["sugar_g"] == 3
        assert entry["sodium_mg"] == 50
        assert entry["caffeine_mg"] is None
        assert entry["protein_g"] == 1

    def test_entry_with_null_protein_returns_null_not_zero(self, db):
        # 단백질 미상(NULL)은 확정된 0으로 뭉개지 않고 그대로 null로 반환되어야 한다.
        user_id = make_user(db)
        today_dt = date.today().isoformat() + " 10:15:00"
        make_food_log(
            db,
            user_id,
            food_id=None,
            food_name="단백질 미상 음식",
            sugar_g=5,
            sodium_mg=30,
            caffeine_mg=None,
            protein_g=None,
            eaten_at=today_dt,
        )

        result = get_today_food_log(user_id=user_id, db=db)

        assert result["count"] == 1
        entry = result["logs"][0]
        assert entry["protein_g"] is None


class TestExtraNutrients:
    def test_extra_nutrients_persisted_and_returned(self, db):
        user_id = make_user(db)
        today_dt = date.today().isoformat() + " 10:00:00"
        log_payload = FoodLogCreate(
            user_id=user_id,
            food_name="비타민 음료",
            input_type="manual",
            sugar_g=5,
            sodium_mg=20,
            eaten_at=today_dt,
            extra_nutrients=[
                {"name": "비타민C", "value": "50mg"},
                {"name": "황산", "value": "약간"},
            ],
        )
        create_food_log(log=log_payload, db=db)

        result = get_today_food_log(user_id=user_id, db=db)

        assert result["count"] == 1
        entry = result["logs"][0]
        assert entry["extra_nutrients"] == [
            {"name": "비타민C", "value": "50mg", "unit": None},
            {"name": "황산", "value": "약간", "unit": None},
        ]

    def test_no_extra_nutrients_returns_empty_list(self, db):
        user_id = make_user(db)
        today_dt = date.today().isoformat() + " 11:00:00"
        log_payload = FoodLogCreate(
            user_id=user_id,
            food_name="일반 음식",
            input_type="manual",
            sugar_g=2,
            sodium_mg=100,
            eaten_at=today_dt,
        )
        create_food_log(log=log_payload, db=db)

        result = get_today_food_log(user_id=user_id, db=db)

        assert result["count"] == 1
        entry = result["logs"][0]
        assert entry["extra_nutrients"] == []


class TestPerItemStatusMatchesSharedThresholds:
    """회귀 가드: 개별 항목 상태 판정이 하드코딩 밴드(caffeine<=70, sugar<=30, sodium<=500)
    대신 get_status()의 트라이메스터 무관 절대 기준(200mg/50g/2300mg, ratio<=0.7 safe/
    <=1.0 caution)을 그대로 재사용하는지 확인한다. 하드코딩 시절에는 이 구간들의 값이
    실제와 다른 상태로 잘못 표시됐다."""

    def _status_by_name(self, result, name):
        items = result["logs"][0]["detail"]["nutrition_items"]
        return next(item["status"] for item in items if item["name"] == name)

    def test_caffeine_in_previously_divergent_zone_is_safe(self, db):
        # 100mg: 예전 하드코딩(<=70 safe)로는 caution이었지만, get_status()(<=140 safe)로는 safe.
        user_id = make_user(db)
        today_dt = date.today().isoformat() + " 08:00:00"
        make_food_log(db, user_id, caffeine_mg=100, eaten_at=today_dt)

        result = get_today_food_log(user_id=user_id, db=db)

        assert self._status_by_name(result, "카페인") == "safe"

    def test_sodium_in_previously_divergent_zone_is_safe(self, db):
        # 800mg: 예전 하드코딩(<=500 safe)로는 caution이었지만, get_status()(<=1610 safe)로는 safe.
        user_id = make_user(db)
        today_dt = date.today().isoformat() + " 08:00:00"
        make_food_log(db, user_id, sodium_mg=800, eaten_at=today_dt)

        result = get_today_food_log(user_id=user_id, db=db)

        assert self._status_by_name(result, "나트륨") == "safe"

    def test_sugar_in_previously_divergent_zone_is_caution_not_avoid(self, db):
        # 40g: 예전 하드코딩(>30 avoid)로는 avoid였지만, get_status()(35<40<=50 caution)로는 caution.
        user_id = make_user(db)
        today_dt = date.today().isoformat() + " 08:00:00"
        make_food_log(db, user_id, sugar_g=40, eaten_at=today_dt)

        result = get_today_food_log(user_id=user_id, db=db)

        assert self._status_by_name(result, "당류") == "caution"

    def test_avoid_boundary_parity_at_shared_limits(self, db):
        # 기준값과 정확히 같은 값(200/2300/50)은 세 영양소 모두 caution이어야 한다
        # (ratio<=1.0 경계, get_status() 정의상 <=이지 <가 아님).
        user_id = make_user(db)
        today_dt = date.today().isoformat() + " 08:00:00"
        make_food_log(
            db, user_id,
            caffeine_mg=200, sodium_mg=2300, sugar_g=50,
            eaten_at=today_dt,
        )

        result = get_today_food_log(user_id=user_id, db=db)

        assert self._status_by_name(result, "카페인") == "caution"
        assert self._status_by_name(result, "나트륨") == "caution"
        assert self._status_by_name(result, "당류") == "caution"

    def test_avoid_boundary_parity_just_above_shared_limits(self, db):
        user_id = make_user(db)
        today_dt = date.today().isoformat() + " 08:00:00"
        make_food_log(
            db, user_id,
            caffeine_mg=201, sodium_mg=2301, sugar_g=51,
            eaten_at=today_dt,
        )

        result = get_today_food_log(user_id=user_id, db=db)

        assert self._status_by_name(result, "카페인") == "avoid"
        assert self._status_by_name(result, "나트륨") == "avoid"
        assert self._status_by_name(result, "당류") == "avoid"

    def test_single_null_sodium_entry_still_unknown(self, db):
        # 개별 항목 자체가 NULL이면 기존과 동일하게 unknown이어야 한다
        # (known_count=0, logged_count=1인 단일 항목 매핑이 이 동작을 보존하는지 확인).
        user_id = make_user(db)
        today_dt = date.today().isoformat() + " 08:00:00"
        make_food_log(db, user_id, sodium_mg=None, eaten_at=today_dt)

        result = get_today_food_log(user_id=user_id, db=db)

        assert self._status_by_name(result, "나트륨") == "unknown"
