"""
backend/routers/premium.py 의 get_premium_report() 테스트 (기존 커버리지 없음).

핵심 검증 대상:
- 403/400/404 기본 검증
- daily: 4개 시간대(새벽/오전/오후/저녁) 버킷팅, 항목별 caffeine_pct/sugar_pct/sodium_pct,
  항목별/전체 status가 unknown(NULL 존재)을 safe/caution/avoid와 구분해서 반영
- weekly: 요일별 버킷팅, 항목별/전체 status, daily_average는 항상 7일 기준
- weekly comparison(지난주 대비): 퍼센트포인트 차이로 계산되고, 지난주 기록이 전혀 없으면 null
- "기록 자체가 없음"과 "기록은 있지만 값이 NULL(unknown)"을 구분하는 회귀 가드
"""
import pytest
from fastapi import HTTPException

from backend.routers.premium import get_premium_report

from .conftest import make_food_log, make_user


class TestGetPremiumReportBasicValidation:
    def test_non_premium_user_returns_403(self, db):
        user_id = make_user(db, is_premium=0)
        with pytest.raises(HTTPException) as exc_info:
            get_premium_report(user_id=user_id, period="daily", db=db)
        assert exc_info.value.status_code == 403

    def test_invalid_period_returns_400(self, db):
        user_id = make_user(db, is_premium=1)
        with pytest.raises(HTTPException) as exc_info:
            get_premium_report(user_id=user_id, period="monthly", db=db)
        assert exc_info.value.status_code == 400

    def test_invalid_date_format_returns_400(self, db):
        user_id = make_user(db, is_premium=1)
        with pytest.raises(HTTPException) as exc_info:
            get_premium_report(user_id=user_id, period="daily", date="not-a-date", db=db)
        assert exc_info.value.status_code == 400

    def test_unknown_user_returns_404(self, db):
        with pytest.raises(HTTPException) as exc_info:
            get_premium_report(user_id=999999, period="daily", db=db)
        assert exc_info.value.status_code == 404


class TestGetPremiumReportDaily:
    def _item(self, result, label):
        return next(i for i in result["chart"]["items"] if i["label"] == label)

    def test_basic_totals_and_slot_bucketing(self, db):
        user_id = make_user(db, is_premium=1, pregnancy_week=20)
        make_food_log(db, user_id, caffeine_mg=20, sugar_g=0, sodium_mg=0,
                       eaten_at="2030-01-10 03:00:00")   # 새벽
        make_food_log(db, user_id, caffeine_mg=30, sugar_g=0, sodium_mg=0,
                       eaten_at="2030-01-10 08:00:00")   # 오전
        make_food_log(db, user_id, caffeine_mg=40, sugar_g=0, sodium_mg=0,
                       eaten_at="2030-01-10 15:00:00")   # 오후
        make_food_log(db, user_id, caffeine_mg=50, sugar_g=0, sodium_mg=0,
                       eaten_at="2030-01-10 20:00:00")   # 저녁

        result = get_premium_report(user_id=user_id, period="daily", date="2030-01-10", db=db)

        assert result["totals"]["caffeine_mg"] == 140.0
        assert result["percentages"]["caffeine"] == 70.0  # 140/200
        assert self._item(result, "새벽")["caffeine_mg"] == 20.0
        assert self._item(result, "새벽")["caffeine_pct"] == 10.0  # 20/200
        assert self._item(result, "오전")["caffeine_mg"] == 30.0
        assert self._item(result, "오후")["caffeine_mg"] == 40.0
        assert self._item(result, "저녁")["caffeine_mg"] == 50.0

    def test_unknown_sugar_marks_status_unknown_but_keeps_partial_sum(self, db):
        user_id = make_user(db, is_premium=1, pregnancy_week=20)
        make_food_log(db, user_id, caffeine_mg=0, sugar_g=8, sodium_mg=0,
                       eaten_at="2030-01-11 02:00:00")   # 새벽, 확인된 값
        make_food_log(db, user_id, caffeine_mg=0, sugar_g=None, sodium_mg=0,
                       eaten_at="2030-01-11 04:00:00")   # 새벽, unknown

        result = get_premium_report(user_id=user_id, period="daily", date="2030-01-11", db=db)

        dawn = self._item(result, "새벽")
        assert dawn["sugar_g"] == 8.0          # unknown은 0으로 뭉개지지 않고 부분합 유지
        assert dawn["sugar_status"] == "unknown"
        assert result["status"]["sugar_status"] == "unknown"  # 전체(top-level)에도 반영

    def test_empty_slot_is_safe_not_unknown(self, db):
        # 시간대에 로그가 아예 없는 것과 unknown 값이 있는 것은 다른 상태여야 한다
        user_id = make_user(db, is_premium=1, pregnancy_week=20)
        make_food_log(db, user_id, caffeine_mg=10, sugar_g=5, sodium_mg=50,
                       eaten_at="2030-01-12 03:00:00")   # 새벽만 기록

        result = get_premium_report(user_id=user_id, period="daily", date="2030-01-12", db=db)

        evening = self._item(result, "저녁")
        assert evening["caffeine_mg"] == 0.0
        assert evening["caffeine_status"] == "safe"
        assert evening["sugar_status"] == "safe"
        assert evening["sodium_status"] == "safe"
        assert evening["status"] == "safe"


class TestGetPremiumReportWeekly:
    def _item(self, result, label):
        return next(i for i in result["chart"]["items"] if i["label"] == label)

    def test_basic_totals_and_weekday_bucketing(self, db):
        user_id = make_user(db, is_premium=1, pregnancy_week=20)
        make_food_log(db, user_id, caffeine_mg=100, sugar_g=20, sodium_mg=500,
                       eaten_at="2030-01-07 09:00:00")   # 월요일
        make_food_log(db, user_id, caffeine_mg=50, sugar_g=10, sodium_mg=300,
                       eaten_at="2030-01-08 09:00:00")   # 화요일

        result = get_premium_report(user_id=user_id, period="weekly", date="2030-01-07", db=db)

        assert result["date_range"]["start"] == "2030-01-07"
        assert result["date_range"]["end"] == "2030-01-13"
        assert result["totals"]["caffeine_mg"] == 150.0
        assert self._item(result, "월")["caffeine_mg"] == 100.0
        assert self._item(result, "화")["caffeine_mg"] == 50.0
        assert self._item(result, "수")["caffeine_mg"] == 0.0

    def test_unknown_status_propagates_top_level_and_per_item(self, db):
        user_id = make_user(db, is_premium=1, pregnancy_week=20)
        make_food_log(db, user_id, caffeine_mg=None, sugar_g=10, sodium_mg=300,
                       eaten_at="2030-01-08 09:00:00")   # 화요일, 카페인 unknown

        result = get_premium_report(user_id=user_id, period="weekly", date="2030-01-07", db=db)

        tuesday = self._item(result, "화")
        assert tuesday["caffeine_status"] == "unknown"
        assert result["status"]["caffeine_status"] == "unknown"

    def test_daily_average_divides_by_days_with_data(self, db):
        # 7일 중 3일(월/수/금)에만 기록이 있으면 daily_average는 3으로 나눈다 (7로 나누지 않는다)
        user_id = make_user(db, is_premium=1, pregnancy_week=20)
        make_food_log(db, user_id, caffeine_mg=210, sugar_g=0, sodium_mg=0,
                       eaten_at="2030-01-07 09:00:00")  # 월
        make_food_log(db, user_id, caffeine_mg=210, sugar_g=0, sodium_mg=0,
                       eaten_at="2030-01-09 09:00:00")  # 수
        make_food_log(db, user_id, caffeine_mg=210, sugar_g=0, sodium_mg=0,
                       eaten_at="2030-01-11 09:00:00")  # 금

        result = get_premium_report(user_id=user_id, period="weekly", date="2030-01-07", db=db)

        assert result["daily_average"]["caffeine_mg"] == 210.0  # 630/3, not 630/7

    def test_daily_average_is_zero_not_error_when_week_is_entirely_empty(self, db):
        user_id = make_user(db, is_premium=1, pregnancy_week=20)

        result = get_premium_report(user_id=user_id, period="weekly", date="2030-01-07", db=db)

        assert result["daily_average"] == {"caffeine_mg": 0.0, "sugar_g": 0.0, "sodium_mg": 0.0}

    def test_comparison_uses_days_with_data_on_previous_week_too(self, db):
        user_id = make_user(db, is_premium=1, pregnancy_week=20)
        # 이번 주: 7일 모두 기록, 하루 평균 카페인 100mg = 50%
        for i in range(7):
            day = 14 + i
            make_food_log(db, user_id, caffeine_mg=100, sugar_g=0, sodium_mg=0,
                           eaten_at=f"2030-01-{day:02d} 09:00:00")
        # 지난 주: 2일(월/화)에만 기록, 각 50mg -> 기록 있는 날 기준 평균 50mg = 25%
        make_food_log(db, user_id, caffeine_mg=50, sugar_g=0, sodium_mg=0,
                       eaten_at="2030-01-07 09:00:00")
        make_food_log(db, user_id, caffeine_mg=50, sugar_g=0, sodium_mg=0,
                       eaten_at="2030-01-08 09:00:00")

        result = get_premium_report(user_id=user_id, period="weekly", date="2030-01-14", db=db)

        # 지난 주 평균이 100/7(=14.3%)이 아니라 50/2(=25%)로 계산되어야 delta가 25.0이 된다
        assert result["comparison"]["caffeine_vs_previous_pct"] == 25.0  # 50% - 25%

    def test_comparison_percentage_point_delta(self, db):
        user_id = make_user(db, is_premium=1, pregnancy_week=20)
        # 이번 주(2030-01-14~01-20): 하루 평균 카페인 100mg = 50%
        for i in range(7):
            day = 14 + i
            make_food_log(db, user_id, caffeine_mg=100, sugar_g=0, sodium_mg=0,
                           eaten_at=f"2030-01-{day:02d} 09:00:00")
        # 지난 주(2030-01-07~01-13): 하루 평균 카페인 50mg = 25%
        for i in range(7):
            day = 7 + i
            make_food_log(db, user_id, caffeine_mg=50, sugar_g=0, sodium_mg=0,
                           eaten_at=f"2030-01-{day:02d} 09:00:00")

        result = get_premium_report(user_id=user_id, period="weekly", date="2030-01-14", db=db)

        assert result["comparison"]["previous_period"]["start"] == "2030-01-07"
        assert result["comparison"]["previous_period"]["end"] == "2030-01-13"
        assert result["comparison"]["caffeine_vs_previous_pct"] == 25.0  # 50% - 25%

    def test_comparison_is_null_when_previous_week_has_no_logs(self, db):
        user_id = make_user(db, is_premium=1, pregnancy_week=20)
        make_food_log(db, user_id, caffeine_mg=100, sugar_g=10, sodium_mg=100,
                       eaten_at="2030-01-14 09:00:00")
        # 지난 주(2030-01-07~01-13)에는 아무 기록도 없음

        result = get_premium_report(user_id=user_id, period="weekly", date="2030-01-14", db=db)

        assert result["comparison"]["caffeine_vs_previous_pct"] is None
        assert result["comparison"]["sugar_vs_previous_pct"] is None
        assert result["comparison"]["sodium_vs_previous_pct"] is None

    def test_comparison_is_null_only_for_nutrient_unknown_on_every_previous_week_row(self, db):
        # 지난 주에 기록은 있지만, sugar_g만 모든 행에서 NULL(unknown)인 경우
        # sugar만 null이고 caffeine/sodium은 정상적으로 계산되어야 한다.
        user_id = make_user(db, is_premium=1, pregnancy_week=20)
        for i in range(7):
            day = 14 + i
            make_food_log(db, user_id, caffeine_mg=100, sugar_g=0, sodium_mg=100,
                           eaten_at=f"2030-01-{day:02d} 09:00:00")
        for i in range(7):
            day = 7 + i
            make_food_log(db, user_id, caffeine_mg=50, sugar_g=None, sodium_mg=50,
                           eaten_at=f"2030-01-{day:02d} 09:00:00")

        result = get_premium_report(user_id=user_id, period="weekly", date="2030-01-14", db=db)

        assert result["comparison"]["sugar_vs_previous_pct"] is None
        assert result["comparison"]["caffeine_vs_previous_pct"] is not None
        assert result["comparison"]["sodium_vs_previous_pct"] is not None
        assert result["comparison"]["caffeine_vs_previous_pct"] == 25.0  # 50% - 25%
        assert result["comparison"]["sodium_vs_previous_pct"] == 2.1     # 4.3% - 2.2%
