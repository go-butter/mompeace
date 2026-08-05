"""
backend/routers/tips.py 의 get_today_tip() 테스트.

핵심 검증 대상:
- 트라이메스터 경계값(12/13/27/28주)에 따라 올바른 팁 풀이 선택된다
- 응답 형태(trimester/trimester_label/trimester_tip/common_tip)
- 존재하지 않는 user_id는 404
- date 쿼리 파라미터에 따라 팁이 회전하고, 풀 크기만큼 지나면 다시 같은 팁으로 돌아온다
  (day_seed = date.toordinal() 기반이므로 unittest.mock 없이 date 파라미터로 직접 테스트)
"""
import pytest
from fastapi import HTTPException

from backend.routers.tips import get_today_tip
from backend.tips_data import TRIMESTER_TIPS, COMMON_TIPS

from .conftest import make_user


class TestGetTodayTipTrimesterBoundary:
    def test_week_12_is_early(self, db):
        user_id = make_user(db, pregnancy_week=12)
        result = get_today_tip(user_id=user_id, db=db)
        assert result["trimester"] == "early"
        assert result["trimester_tip"] in TRIMESTER_TIPS["early"]

    def test_week_13_is_middle(self, db):
        user_id = make_user(db, pregnancy_week=13)
        result = get_today_tip(user_id=user_id, db=db)
        assert result["trimester"] == "middle"
        assert result["trimester_tip"] in TRIMESTER_TIPS["middle"]

    def test_week_27_is_middle(self, db):
        user_id = make_user(db, pregnancy_week=27)
        result = get_today_tip(user_id=user_id, db=db)
        assert result["trimester"] == "middle"
        assert result["trimester_tip"] in TRIMESTER_TIPS["middle"]

    def test_week_28_is_late(self, db):
        user_id = make_user(db, pregnancy_week=28)
        result = get_today_tip(user_id=user_id, db=db)
        assert result["trimester"] == "late"
        assert result["trimester_tip"] in TRIMESTER_TIPS["late"]


class TestGetTodayTipResponseShape:
    def test_returns_all_required_keys(self, db):
        user_id = make_user(db, pregnancy_week=20)
        result = get_today_tip(user_id=user_id, db=db)

        assert set(result.keys()) == {"trimester", "trimester_label", "trimester_tip", "common_tip"}
        assert set(result["trimester_tip"].keys()) == {"category", "content"}
        assert set(result["common_tip"].keys()) == {"content"}
        assert result["common_tip"] in COMMON_TIPS

    def test_trimester_label_matches_trimester(self, db):
        user_id = make_user(db, pregnancy_week=20)
        result = get_today_tip(user_id=user_id, db=db)

        assert result["trimester"] == "middle"
        assert result["trimester_label"] == "임신 중기"


class TestGetTodayTipUnknownUser:
    def test_unknown_user_returns_404(self, db):
        with pytest.raises(HTTPException) as exc_info:
            get_today_tip(user_id=999999, db=db)
        assert exc_info.value.status_code == 404

    def test_invalid_date_format_returns_400(self, db):
        user_id = make_user(db, pregnancy_week=20)
        with pytest.raises(HTTPException) as exc_info:
            get_today_tip(user_id=user_id, date="not-a-date", db=db)
        assert exc_info.value.status_code == 400


class TestGetTodayTipRotation:
    def test_different_dates_return_different_tips(self, db):
        # early(6)/middle(5)/late(6)/common(7) 풀 전부에서 2030-01-10과 2030-01-11은
        # toordinal() % len(pool)이 서로 다른 인덱스를 가리킨다.
        user_id = make_user(db, pregnancy_week=5)  # early

        result_1 = get_today_tip(user_id=user_id, date="2030-01-10", db=db)
        result_2 = get_today_tip(user_id=user_id, date="2030-01-11", db=db)

        assert result_1["trimester_tip"] != result_2["trimester_tip"]
        assert result_1["common_tip"] != result_2["common_tip"]

    def test_rotation_wraps_around_at_pool_boundary(self, db):
        # early 풀 크기(6) 만큼 날짜가 지나면 toordinal() % 6 이 같아져 동일한 팁으로 돌아온다.
        user_id = make_user(db, pregnancy_week=5)  # early

        result_1 = get_today_tip(user_id=user_id, date="2030-01-10", db=db)
        result_2 = get_today_tip(user_id=user_id, date="2030-01-16", db=db)  # +6일

        assert result_1["trimester_tip"] == result_2["trimester_tip"]
