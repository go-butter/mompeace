"""
backend/routers/coffee.py 의 get_coffee_options() 테스트.

핵심 검증 대상:
- COFFEE_CAFFEINE_DATA/HOME_COFFEE_PRESETS를 가공 없이 그대로 반환한다
  (필터링/변형이 나중에 실수로 추가되는 것을 방지)
"""
from backend.routers.coffee import get_coffee_options
from backend.coffee_caffeine_data import COFFEE_CAFFEINE_DATA, HOME_COFFEE_PRESETS


class TestGetCoffeeOptions:
    def test_returns_brands_and_home_presets_keys(self):
        result = get_coffee_options()
        assert "brands" in result
        assert "home_presets" in result

    def test_returns_full_unfiltered_data(self):
        result = get_coffee_options()
        assert result["brands"] == COFFEE_CAFFEINE_DATA
        assert result["home_presets"] == HOME_COFFEE_PRESETS
        assert len(result["brands"]) == len(COFFEE_CAFFEINE_DATA)
        assert len(result["home_presets"]) == len(HOME_COFFEE_PRESETS)
