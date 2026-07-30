"""
food_log 행은 free/premium 여부와 관계없이 영구 보존되어야 한다는 정책 회귀 테스트.

cleanup_expired_food_logs()가 다시 도입되어 과거 기록이 삭제되는 일이 없도록
by-date 조회와 캘린더 조회 양쪽에서 과거 기록이 그대로 남아있는지 확인한다.
"""
import pytest
from fastapi import HTTPException

from backend.routers.food_log import delete_food_log, get_food_log_by_date
from backend.routers.intake import get_food_log_calendar

from .conftest import make_food_log, make_user


class TestFoodLogRetention:
    def test_old_food_log_survives_by_date_and_calendar(self, db):
        user_id = make_user(db, pregnancy_week=20)
        past_date = "2026-06-19"
        make_food_log(
            db,
            user_id,
            food_name="오래된 기록",
            eaten_at=f"{past_date} 08:00:00",
        )

        by_date_result = get_food_log_by_date(user_id=user_id, date=past_date, db=db)
        assert by_date_result["count"] == 1
        assert by_date_result["logs"][0]["food_name"] == "오래된 기록"

        calendar_result = get_food_log_calendar(user_id=user_id, year=2026, month=6, db=db)
        days_with_data = {d["date"] for d in calendar_result["days"]}
        assert past_date in days_with_data


class TestDeleteFoodLog:
    def test_delete_own_log_removes_it(self, db):
        user_id = make_user(db)
        log_id = make_food_log(db, user_id, eaten_at="2026-07-01 08:00:00")

        result = delete_food_log(log_id=log_id, user_id=user_id, db=db)
        assert result["log_id"] == log_id

        by_date_result = get_food_log_by_date(user_id=user_id, date="2026-07-01", db=db)
        assert by_date_result["count"] == 0

    def test_delete_nonexistent_log_returns_404(self, db):
        user_id = make_user(db)

        with pytest.raises(HTTPException) as exc_info:
            delete_food_log(log_id=999999, user_id=user_id, db=db)
        assert exc_info.value.status_code == 404

    def test_delete_other_users_log_returns_404_not_403(self, db):
        owner_id = make_user(db, nickname="소유자")
        other_user_id = make_user(db, nickname="다른유저")
        log_id = make_food_log(db, owner_id, eaten_at="2026-07-01 08:00:00")

        with pytest.raises(HTTPException) as exc_info:
            delete_food_log(log_id=log_id, user_id=other_user_id, db=db)
        assert exc_info.value.status_code == 404

        by_date_result = get_food_log_by_date(user_id=owner_id, date="2026-07-01", db=db)
        assert by_date_result["count"] == 1
