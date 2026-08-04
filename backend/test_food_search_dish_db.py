"""
GET /foods/search의 dish_db_download 카탈로그 검색 경로 테스트.

핵심 검증 대상:
- food_items(data_source=dish_db_download)에서 food_name LIKE로 매칭한다
- 매칭되는 행이 없으면 카탈로그 결과는 빈 배열이다 (개인 기록은 별도)
- calories_kcal/fat_g가 응답 data에서 누락되지 않는다 (지방/에너지 임포트 이후)
- caffeine_mg/sodium_mg 등 결측값은 0으로 대체되지 않고 None 그대로 전달된다
- 실제 caffeine_mg 값이 있으면 그대로 응답에 포함된다
"""
from backend.routers.foods import search_food

from .conftest import make_food_item


def test_search_food_matches_dish_db_by_name(db):
    make_food_item(db, food_name="된장찌개", category="찌개류")

    result = search_food(query="된장찌개", page_no=1, num_of_rows=10, user_id=None, db=db)

    assert result["count"] == 1
    assert result["results"][0]["source"] == "dish_db_download"
    assert result["results"][0]["data"]["food_name"] == "된장찌개"
    # PRODUCT_LIMITS 기반 단일 제품 위험도 판정(evaluate_food_risk)은 은퇴했다 —
    # 응답에 "risk" 키가 되살아나지 않도록 가드한다.
    assert "risk" not in result["results"][0]


def test_search_food_no_match_returns_empty_catalog_results(db):
    make_food_item(db, food_name="된장찌개")

    result = search_food(query="존재하지않는음식이름", page_no=1, num_of_rows=10, user_id=None, db=db)

    assert result["results"] == []


def test_search_food_includes_calories_and_fat_for_dish_db(db):
    make_food_item(db, food_name="테스트도넛", calories_kcal=425.0, fat_g=19.18)

    result = search_food(query="테스트도넛", page_no=1, num_of_rows=10, user_id=None, db=db)

    data = result["results"][0]["data"]
    assert "calories_kcal" in data
    assert data["calories_kcal"] == 425.0
    assert "fat_g" in data
    assert data["fat_g"] == 19.18


def test_search_food_includes_saturated_trans_cholesterol_iron(db):
    make_food_item(
        db,
        food_name="테스트철분식품",
        saturated_fat_g=1.2,
        trans_fat_g=0.1,
        cholesterol_mg=5.0,
        iron_mg=2.3,
    )

    result = search_food(query="테스트철분식품", page_no=1, num_of_rows=10, user_id=None, db=db)

    data = result["results"][0]["data"]
    assert data["saturated_fat_g"] == 1.2
    assert data["trans_fat_g"] == 0.1
    assert data["cholesterol_mg"] == 5.0
    assert data["iron_mg"] == 2.3


def test_search_food_passes_through_null_nutrient_fields(db):
    make_food_item(db, food_name="정보부족음식", sodium_mg=None, caffeine_mg=None)

    result = search_food(query="정보부족음식", page_no=1, num_of_rows=10, user_id=None, db=db)

    data = result["results"][0]["data"]
    assert data["sodium_mg"] is None
    assert data["caffeine_mg"] is None


def test_search_food_returns_real_caffeine_value(db):
    make_food_item(db, food_name="아메리카노", caffeine_mg=150.0)

    result = search_food(query="아메리카노", page_no=1, num_of_rows=10, user_id=None, db=db)

    assert result["results"][0]["data"]["caffeine_mg"] == 150.0
