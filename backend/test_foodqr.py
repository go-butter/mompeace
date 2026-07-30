"""
backend/foodqr.py 의 simplify_food_info() 테스트.

핵심 검증 대상:
- nutrition 리스트에 특정 영양성분이 없으면 해당 값은 None이어야 한다
  (0으로 collapse되면 안 됨 — 카페인/나트륨 임계값 판정에 실사용되는 값이므로)
"""
from backend.foodqr import simplify_food_info


def _api_data(nutrition_items, basic_overrides=None):
    basic = {"brcdNo": "123", "prdctNm": "테스트제품"}
    if basic_overrides:
        basic.update(basic_overrides)
    return {
        "basic": [basic],
        "nutrition": nutrition_items,
        "allergy": [],
        "safety": [],
        "intake_warning": [],
    }


def test_simplify_food_info_missing_nutrient_stays_none():
    # "나트륨"이 아예 응답에 없는 경우
    data = _api_data([
        {"nirwmtNm": "열량", "cta": "100", "igrdUcd": "kcal"},
        {"nirwmtNm": "당류", "cta": "5", "igrdUcd": "g"},
    ])

    result = simplify_food_info(data)

    assert result["sodium_mg"] is None
    assert result["calories_kcal"] == "100"
    assert result["sugar_g"] == "5"


def test_simplify_food_info_all_nutrients_missing_stay_none():
    data = _api_data([])

    result = simplify_food_info(data)

    assert result["calories_kcal"] is None
    assert result["sodium_mg"] is None
    assert result["sugar_g"] is None
    assert result["carbohydrate_g"] is None
    assert result["protein_g"] is None


def test_simplify_food_info_returns_none_when_no_basic():
    data = {"basic": [], "nutrition": [], "allergy": [], "safety": [], "intake_warning": []}
    assert simplify_food_info(data) is None
