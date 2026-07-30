"""
backend/food_search_api.py 의 to_float()/simplify_food_nutrition_item() 테스트.

핵심 검증 대상:
- to_float(value, default=None)은 값이 없을 때 0이 아닌 None을 반환한다
- simplify_food_nutrition_item()에서 sugar_g/sodium_mg/carbohydrate_g/protein_g는
  원본 API 응답에 해당 키가 없으면 None이어야 한다 (0으로 collapse되면 안 됨)
"""
from backend.food_search_api import simplify_food_nutrition_item, to_float


def test_to_float_missing_value_defaults_to_none_when_requested():
    assert to_float(None, default=None) is None


def test_to_float_blank_string_defaults_to_none_when_requested():
    assert to_float("", default=None) is None
    assert to_float("-", default=None) is None
    assert to_float("N/A", default=None) is None


def test_to_float_still_parses_valid_numbers_with_none_default():
    assert to_float("58.00g", default=None) == 58.0


def test_to_float_default_still_zero_when_unspecified():
    assert to_float(None) == 0


def test_normalize_items_missing_nutrients_stay_none():
    item = {
        "FOOD_NM_KR": "테스트식품",
        "FOOD_CD": "T001",
        # AMT_NUM23(당류), AMT_NUM13(나트륨), AMT_NUM6(탄수화물), AMT_NUM3(단백질) 모두 없음
    }

    result = simplify_food_nutrition_item(item)

    assert result["sugar_g"] is None
    assert result["sodium_mg"] is None
    assert result["carbohydrate_g"] is None
    assert result["protein_g"] is None
    assert result["caffeine_mg"] is None


def test_normalize_items_present_nutrients_are_parsed():
    item = {
        "FOOD_NM_KR": "테스트식품",
        "FOOD_CD": "T002",
        "AMT_NUM23": "5.5g",
        "AMT_NUM13": "120",
        "AMT_NUM6": "20g",
        "AMT_NUM3": "3g",
    }

    result = simplify_food_nutrition_item(item)

    assert result["sugar_g"] == 5.5
    assert result["sodium_mg"] == 120.0
    assert result["carbohydrate_g"] == 20.0
    assert result["protein_g"] == 3.0
