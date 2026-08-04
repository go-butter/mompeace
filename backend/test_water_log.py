"""
backend/routers/water_log.py 테스트.

핵심 검증 대상:
- 기록 생성/삭제가 본인 user_id에만 스코프된다
- 하루 합계/퍼센트 계산 (기록이 없는 날은 진짜 0)
- 주간 집계가 월~일 7일을 정확히 채우고 hit_target/is_today가 올바르다
"""
from datetime import date, timedelta

import pytest
from fastapi import HTTPException

from backend.models import WaterLogCreate
from backend.nutrition_constants import DAILY_WATER_TARGET_ML
from backend.routers.water_log import (
    WEEKDAY_LABELS,
    create_water_log,
    delete_water_log,
    get_today_water_log,
    get_water_log_by_date,
    get_water_log_week,
)

from .conftest import make_user, make_water_log


class TestCreateWaterLog:
    def test_create_inserts_row_and_returns_log_id(self, db):
        user_id = make_user(db)

        result = create_water_log(WaterLogCreate(user_id=user_id, amount_ml=250), db=db)

        assert result["log_id"] is not None
        assert "message" in result

        cursor = db.cursor()
        cursor.execute("SELECT * FROM water_log WHERE log_id = ?", (result["log_id"],))
        row = dict(cursor.fetchone())
        assert row["user_id"] == user_id
        assert row["amount_ml"] == 250

    def test_create_with_explicit_logged_at(self, db):
        user_id = make_user(db)
        custom_ts = "2024-03-01 09:00:00"

        result = create_water_log(
            WaterLogCreate(user_id=user_id, amount_ml=500, logged_at=custom_ts), db=db
        )

        cursor = db.cursor()
        cursor.execute("SELECT logged_at FROM water_log WHERE log_id = ?", (result["log_id"],))
        assert cursor.fetchone()["logged_at"] == custom_ts

    def test_create_unknown_user_raises_404(self, db):
        with pytest.raises(HTTPException) as exc_info:
            create_water_log(WaterLogCreate(user_id=999, amount_ml=250), db=db)
        assert exc_info.value.status_code == 404


class TestWaterSummaryForDate:
    def test_no_logs_is_a_real_zero(self, db):
        user_id = make_user(db)

        result = get_today_water_log(user_id=user_id, db=db)

        assert result["total_ml"] == 0
        assert result["percent"] == 0
        assert result["logs"] == []
        assert result["target_ml"] == DAILY_WATER_TARGET_ML

    def test_totals_and_percent_sum_todays_logs(self, db):
        user_id = make_user(db)
        today_dt = date.today().isoformat()
        make_water_log(db, user_id, amount_ml=250, logged_at=f"{today_dt} 09:00:00")
        make_water_log(db, user_id, amount_ml=300, logged_at=f"{today_dt} 15:30:00")

        result = get_today_water_log(user_id=user_id, db=db)

        assert result["total_ml"] == 550
        assert result["percent"] == round(550 / DAILY_WATER_TARGET_ML * 100, 1)
        assert len(result["logs"]) == 2
        assert result["logs"][0]["time"] == "09:00"
        assert result["logs"][1]["time"] == "15:30"

    def test_by_date_only_counts_the_requested_date(self, db):
        user_id = make_user(db)
        make_water_log(db, user_id, amount_ml=250, logged_at="2024-01-01 09:00:00")
        make_water_log(db, user_id, amount_ml=999, logged_at="2024-01-02 09:00:00")

        result = get_water_log_by_date(user_id=user_id, date="2024-01-01", db=db)

        assert result["total_ml"] == 250
        assert result["date"] == "2024-01-01"

    def test_by_date_invalid_format_raises_400(self, db):
        user_id = make_user(db)
        with pytest.raises(HTTPException) as exc_info:
            get_water_log_by_date(user_id=user_id, date="not-a-date", db=db)
        assert exc_info.value.status_code == 400

    def test_unknown_user_raises_404(self, db):
        with pytest.raises(HTTPException) as exc_info:
            get_today_water_log(user_id=999, db=db)
        assert exc_info.value.status_code == 404


class TestWaterLogWeek:
    def test_returns_seven_days_monday_to_sunday(self, db):
        user_id = make_user(db)

        result = get_water_log_week(user_id=user_id, db=db)

        today = date.today()
        monday = today - timedelta(days=today.weekday())
        sunday = monday + timedelta(days=6)

        assert len(result["days"]) == 7
        assert [d["label"] for d in result["days"]] == WEEKDAY_LABELS
        assert [d["date"] for d in result["days"]] == [
            (monday + timedelta(days=i)).isoformat() for i in range(7)
        ]
        assert result["date_range"] == {"start": monday.isoformat(), "end": sunday.isoformat()}
        assert result["target_ml"] == DAILY_WATER_TARGET_ML

    def test_aggregates_multiple_logs_per_day_and_flags_hit_target(self, db):
        user_id = make_user(db)
        today = date.today()
        monday = today - timedelta(days=today.weekday())
        wednesday = monday + timedelta(days=2)

        make_water_log(db, user_id, amount_ml=500, logged_at=f"{monday.isoformat()} 09:00:00")
        make_water_log(db, user_id, amount_ml=300, logged_at=f"{monday.isoformat()} 15:00:00")
        make_water_log(
            db, user_id, amount_ml=DAILY_WATER_TARGET_ML, logged_at=f"{wednesday.isoformat()} 10:00:00"
        )

        result = get_water_log_week(user_id=user_id, db=db)
        days_by_date = {d["date"]: d for d in result["days"]}

        monday_day = days_by_date[monday.isoformat()]
        assert monday_day["amount_ml"] == 800
        assert monday_day["hit_target"] is False

        wednesday_day = days_by_date[wednesday.isoformat()]
        assert wednesday_day["amount_ml"] == DAILY_WATER_TARGET_ML
        assert wednesday_day["hit_target"] is True

        no_log_days = [d for d in result["days"] if d["date"] not in (monday.isoformat(), wednesday.isoformat())]
        for d in no_log_days:
            assert d["amount_ml"] == 0
            assert d["hit_target"] is False

    def test_is_today_flag_marks_exactly_today(self, db):
        user_id = make_user(db)

        result = get_water_log_week(user_id=user_id, db=db)

        today_str = date.today().isoformat()
        today_flags = [d for d in result["days"] if d["is_today"]]
        assert len(today_flags) == 1
        assert today_flags[0]["date"] == today_str
        for d in result["days"]:
            assert d["is_today"] == (d["date"] == today_str)

    def test_excludes_logs_outside_the_week(self, db):
        user_id = make_user(db)
        today = date.today()
        monday = today - timedelta(days=today.weekday())
        last_sunday = monday - timedelta(days=1)

        make_water_log(db, user_id, amount_ml=999, logged_at=f"{last_sunday.isoformat()} 09:00:00")

        result = get_water_log_week(user_id=user_id, db=db)

        assert sum(d["amount_ml"] for d in result["days"]) == 0

    def test_unknown_user_raises_404(self, db):
        with pytest.raises(HTTPException) as exc_info:
            get_water_log_week(user_id=999, db=db)
        assert exc_info.value.status_code == 404


class TestDeleteWaterLog:
    def test_delete_removes_row(self, db):
        user_id = make_user(db)
        log_id = make_water_log(db, user_id)

        result = delete_water_log(log_id=log_id, user_id=user_id, db=db)

        assert result["log_id"] == log_id
        cursor = db.cursor()
        cursor.execute("SELECT * FROM water_log WHERE log_id = ?", (log_id,))
        assert cursor.fetchone() is None

    def test_delete_scoped_to_owning_user(self, db):
        owner_id = make_user(db)
        other_user_id = make_user(db, nickname="다른유저")
        log_id = make_water_log(db, owner_id)

        with pytest.raises(HTTPException) as exc_info:
            delete_water_log(log_id=log_id, user_id=other_user_id, db=db)
        assert exc_info.value.status_code == 404

        cursor = db.cursor()
        cursor.execute("SELECT * FROM water_log WHERE log_id = ?", (log_id,))
        assert cursor.fetchone() is not None

    def test_delete_unknown_log_raises_404(self, db):
        user_id = make_user(db)
        with pytest.raises(HTTPException) as exc_info:
            delete_water_log(log_id=999, user_id=user_id, db=db)
        assert exc_info.value.status_code == 404
