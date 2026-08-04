"""
GET /foods/search의 사용자 검증 동작 테스트.

과거에는 서버가 재계산한 임신 주차가 응답의 risk 필드로 노출되어 이를 검증했지만,
PRODUCT_LIMITS 기반 위험도 판정(evaluate_food_risk)이 은퇴하면서 risk 필드와 함께
주차 노출도 사라졌다. 남은 관찰 가능한 동작은 알 수 없는 user_id에 대한 404뿐이다.
"""
import pytest
from fastapi import HTTPException

from backend.routers.foods import search_food


class TestSearchFoodUserValidation:
    def test_search_food_with_nonexistent_user_id_raises_404(self, db):
        with pytest.raises(HTTPException) as exc_info:
            search_food(query="테스트", page_no=1, num_of_rows=10, user_id=999999, db=db)

        assert exc_info.value.status_code == 404
