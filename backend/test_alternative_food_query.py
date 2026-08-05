"""
backend/alternative_food_query.py 테스트.

핵심 검증 대상:
- determine_trigger_nutrient(): avoid인 영양소가 없으면 None, 여러 개 동시에
  avoid면 nutrition_constants.NUTRIENT_STATUS_TYPE 선언 순서(sugar > fat > iron
  > sodium, carbohydrate/energy/protein은 애초에 후보 아님)를 결정론적으로 따른다
- find_subcategory_alternatives(): 같은 subcategory만, trigger_nutrient 컬럼
  오름차순으로, dish_db_download 소스만, NULL 값 행은 제외하고, limit을 지킨다
"""
import pytest

from backend.alternative_food_query import determine_trigger_nutrient, find_subcategory_alternatives

from .conftest import make_food_item

_ALL_KEYS = ["carbohydrate", "sugar", "energy", "fat", "iron", "protein", "sodium"]


def _statuses(**overrides) -> list[dict]:
    """7개 영양소 상태를 모두 'safe'로 채운 뒤 overrides로 지정한 키만 바꾼다."""
    return [{"key": k, "status": overrides.get(k, "safe")} for k in _ALL_KEYS]


# ── determine_trigger_nutrient ───────────────────────────────────

def test_no_avoid_returns_none():
    assert determine_trigger_nutrient(_statuses()) is None


def test_single_sodium_avoid():
    assert determine_trigger_nutrient(_statuses(sodium="avoid")) == "sodium"


def test_sugar_and_sodium_both_avoid_prefers_sugar():
    assert determine_trigger_nutrient(_statuses(sugar="avoid", sodium="avoid")) == "sugar"


def test_sodium_fat_iron_avoid_sugar_safe_prefers_fat():
    assert determine_trigger_nutrient(_statuses(sodium="avoid", fat="avoid", iron="avoid")) == "fat"


def test_iron_and_sodium_avoid_prefers_iron():
    assert determine_trigger_nutrient(_statuses(iron="avoid", sodium="avoid")) == "iron"


def test_floor_type_avoid_is_ignored_even_if_present():
    # carbohydrate/energy/protein은 실제로는 avoid가 될 수 없지만(floor 타입은
    # get_item_nutrient_status에서 항상 unknown), 방어적으로 avoid가 섞여
    # 들어와도 트리거 후보에서 제외된다.
    assert determine_trigger_nutrient(_statuses(carbohydrate="avoid", sodium="avoid")) == "sodium"


def test_determinism_same_input_same_output():
    statuses = _statuses(sugar="avoid", iron="avoid")
    assert determine_trigger_nutrient(statuses) == determine_trigger_nutrient(statuses) == "sugar"


# ── find_subcategory_alternatives ────────────────────────────────

def test_find_alternatives_filters_by_subcategory(db):
    make_food_item(db, food_name="라면A", subcategory="라면", sodium_mg=500)
    make_food_item(db, food_name="짜장면A", subcategory="짜장면", sodium_mg=100)

    results = find_subcategory_alternatives(db, "라면", "sodium")

    assert [r["food_name"] for r in results] == ["라면A"]


@pytest.mark.parametrize("nutrient,column", [
    ("sugar", "sugar_g"), ("sodium", "sodium_mg"), ("fat", "fat_g"), ("iron", "iron_mg"),
])
def test_find_alternatives_sorts_ascending_by_trigger_column(db, nutrient, column):
    make_food_item(db, food_name="높음", subcategory="라면", **{column: 300})
    make_food_item(db, food_name="낮음", subcategory="라면", **{column: 50})
    make_food_item(db, food_name="중간", subcategory="라면", **{column: 150})

    results = find_subcategory_alternatives(db, "라면", nutrient)

    assert [r["food_name"] for r in results] == ["낮음", "중간", "높음"]


def test_find_alternatives_excludes_null_trigger_column_rows(db):
    """SQLite는 ASC 정렬에서 NULL을 가장 작은 값으로 취급해 맨 앞에 놓으므로,
    IS NOT NULL 가드가 없으면 정보가 없는 행이 '가장 좋은 대안'으로 잘못 표시된다."""
    make_food_item(db, food_name="정보없음", subcategory="라면", sodium_mg=None)
    make_food_item(db, food_name="정보있음", subcategory="라면", sodium_mg=200)

    results = find_subcategory_alternatives(db, "라면", "sodium")

    assert [r["food_name"] for r in results] == ["정보있음"]


def test_find_alternatives_excludes_non_dish_db_sources(db):
    make_food_item(db, food_name="API라면", subcategory="라면", sodium_mg=10,
                    data_source="food_nutrition_api")
    make_food_item(db, food_name="DB라면", subcategory="라면", sodium_mg=200)

    results = find_subcategory_alternatives(db, "라면", "sodium")

    assert [r["food_name"] for r in results] == ["DB라면"]


def test_find_alternatives_respects_limit(db):
    for i in range(7):
        make_food_item(db, food_name=f"라면{i}", subcategory="라면", sodium_mg=float(i))

    results = find_subcategory_alternatives(db, "라면", "sodium", limit=5)

    assert len(results) == 5


def test_find_alternatives_invalid_trigger_nutrient_raises(db):
    with pytest.raises(ValueError):
        find_subcategory_alternatives(db, "라면", "energy")
