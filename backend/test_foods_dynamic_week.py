"""
GET /foods/barcode, GET /foods/search의 임신 주차 서버 계산 검증.

핵심 검증 대상:
- pregnancy_entered_at 앵커로부터 경과일을 더한 "오늘" 기준 주차가 사용되는지
  (클라이언트가 보낸 값이 아니라 서버가 재계산한 값이어야 한다)
- user_id가 주어졌지만 존재하지 않는 사용자면 404
- user_id를 주지 않으면 기존과 동일하게 기본값 20주가 적용된다
"""
from datetime import date, timedelta

import pytest
from fastapi import HTTPException

import backend.routers.foods as foods_router
from backend.routers.foods import get_food_by_barcode, search_food

from .conftest import make_user

MOCK_FOOD = {
    "food_name": "테스트 음식",
    "caffeine_mg": 0,
    "sugar_g": 0,
    "sodium_mg": 0,
    "allergens": [],
}


class TestDynamicPregnancyWeek:
    def test_search_food_uses_recalculated_week_not_stale_anchor(self, db, monkeypatch):
        monkeypatch.setattr(foods_router, "search_food_nutrition", lambda **kwargs: [MOCK_FOOD])
        entered_at = (date.today() - timedelta(days=30)).isoformat()
        user_id = make_user(db, pregnancy_week=10, pregnancy_day=0, pregnancy_entered_at=entered_at)

        result = search_food(query="테스트", page_no=1, num_of_rows=10, user_id=user_id, db=db)

        # 10주0일 + 30일 경과 = 14주2일 (기존 정적 값 10주가 아니어야 한다)
        risk = result["results"][0]["risk"]
        assert risk["pregnancy_week"] == 14
        assert risk["trimester"] == "middle"

    def test_get_food_by_barcode_uses_recalculated_week(self, db, monkeypatch):
        entered_at = (date.today() - timedelta(days=30)).isoformat()
        user_id = make_user(db, pregnancy_week=10, pregnancy_day=0, pregnancy_entered_at=entered_at)
        monkeypatch.setattr(foods_router, "USE_MOCK_FOODQR", True)

        result = get_food_by_barcode(barcode="1234567890", user_id=user_id, db=db)

        assert result["risk"]["pregnancy_week"] == 14
        assert result["risk"]["trimester"] == "middle"

    def test_search_food_without_user_id_defaults_to_week_20(self, db, monkeypatch):
        monkeypatch.setattr(foods_router, "search_food_nutrition", lambda **kwargs: [MOCK_FOOD])

        result = search_food(query="테스트", page_no=1, num_of_rows=10, user_id=None, db=db)

        assert result["results"][0]["risk"]["pregnancy_week"] == 20

    def test_search_food_with_nonexistent_user_id_raises_404(self, db, monkeypatch):
        monkeypatch.setattr(foods_router, "search_food_nutrition", lambda **kwargs: [MOCK_FOOD])

        with pytest.raises(HTTPException) as exc_info:
            search_food(query="테스트", page_no=1, num_of_rows=10, user_id=999999, db=db)

        assert exc_info.value.status_code == 404

    def test_get_food_by_barcode_with_nonexistent_user_id_raises_404(self, db, monkeypatch):
        monkeypatch.setattr(foods_router, "USE_MOCK_FOODQR", True)

        with pytest.raises(HTTPException) as exc_info:
            get_food_by_barcode(barcode="1234567890", user_id=999999, db=db)

        assert exc_info.value.status_code == 404
