"""
backend/routers/intake.py 의 get_food_log_calendar() 테스트.

핵심 검증 대상:
- 월별로 음식 기록이 있는 날짜마다 overall_status가 계산되어 days에 포함된다
- 기록이 없는 달은 days가 빈 리스트다
- 존재하지 않는 사용자는 404
"""
import pytest
from fastapi import HTTPException

from backend.routers.intake import get_food_log_calendar

from .conftest import make_user, make_food_log


class TestGetFoodLogCalendar:
    def test_mixed_status_days_in_month(self, db):
        # food_log cleanup deletes non-premium rows older than 1 day, so use
        # a month far in the future to keep these rows from being purged
        # regardless of when the suite actually runs.
        user_id = make_user(db, pregnancy_week=20)

        # safe: well under limits (caffeine 50/200=25%)
        make_food_log(db, user_id, caffeine_mg=50, sugar_g=5, sodium_mg=200,
                       eaten_at="2030-01-03 09:00:00")
        # caution: caffeine 150/200=75%
        make_food_log(db, user_id, caffeine_mg=150, sugar_g=5, sodium_mg=200,
                       eaten_at="2030-01-05 09:00:00")
        # avoid: caffeine 250/200=125%
        make_food_log(db, user_id, caffeine_mg=250, sugar_g=5, sodium_mg=200,
                       eaten_at="2030-01-12 09:00:00")
        # unknown: caffeine_mg NULL
        make_food_log(db, user_id, caffeine_mg=None, sugar_g=5, sodium_mg=200,
                       eaten_at="2030-01-20 09:00:00")

        result = get_food_log_calendar(user_id=user_id, year=2030, month=1, db=db)

        days_by_date = {d["date"]: d["overall_status"] for d in result["days"]}
        assert days_by_date == {
            "2030-01-03": "safe",
            "2030-01-05": "caution",
            "2030-01-12": "avoid",
            "2030-01-20": "unknown",
        }
        assert result["user_id"] == user_id
        assert result["year"] == 2030
        assert result["month"] == 1

    def test_empty_month_returns_empty_days(self, db):
        user_id = make_user(db)

        result = get_food_log_calendar(user_id=user_id, year=2030, month=2, db=db)

        assert result["days"] == []

    def test_unknown_user_404(self, db):
        with pytest.raises(HTTPException) as exc_info:
            get_food_log_calendar(user_id=9999, year=2026, month=6, db=db)

        assert exc_info.value.status_code == 404
