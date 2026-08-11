"""POST /recommendations 라우터 테스트.

이 라우터에는 그동안 테스트가 하나도 없었다. 판정 규칙(test_recommendation_model.py)과
달리 여기서만 결정되는 것들이 있다:

- 후보 SQL: 랜덤 샘플링 *전에* 영양소 조건으로 거르는가, NULL이 살아남는가,
  이미 초과한 영양소로는 조건을 만들지 않는가
- 다중 카테고리 IN 절과 파라미터 개수
- 이미 초과한 영양소 기준 정렬(NULL 최후) 및 exceeded_nutrients/exceeded_label 응답
- 영양소 칩(sort_nutrient)의 방향별 정렬과 panel_nutrients 응답
"""
import pytest

from backend.models import RecommendationRequest
from backend.nutrition_constants import DAILY_SODIUM_LIMIT_MG, DAILY_SUGAR_LIMIT_G
from backend.routers import recommendation
from backend.routers.recommendation import get_recommendations

from .conftest import make_food_item, make_food_log, make_user


def _req(user_id, **overrides):
    return RecommendationRequest(user_id=user_id, **overrides)


def _names(result):
    return [r["food_name"] for r in result["recommendations"]]


# ── 이미 초과한 영양소가 후보 전체를 막지 않는다 ──────────────

class TestExceededNutrientDoesNotEmptyTheScreen:
    def test_screen_is_not_empty_when_sodium_is_already_over(self, db):
        # 이 라우터가 고쳐야 했던 실제 증상: 나트륨을 이미 넘긴 날에 후보 전체가
        # avoid로 떨어져 화면이 비었다.
        user_id = make_user(db)
        make_food_log(db, user_id, sodium_mg=DAILY_SODIUM_LIMIT_MG * 1.5)
        for i in range(5):
            make_food_item(db, food_name=f"저염식 {i}", sodium_mg=50.0, sugar_g=1.0,
                           caffeine_mg=0.0, category="밥류")

        result = get_recommendations(_req(user_id), db=db)

        assert len(result["recommendations"]) == 5
        assert all(r["status"] != "avoid" for r in result["recommendations"])

    def test_response_names_the_exceeded_nutrients(self, db):
        user_id = make_user(db)
        make_food_log(
            db, user_id,
            sodium_mg=DAILY_SODIUM_LIMIT_MG * 1.2,
            sugar_g=DAILY_SUGAR_LIMIT_G * 1.2,
        )
        make_food_item(db, food_name="저염식", sodium_mg=10.0, sugar_g=1.0, caffeine_mg=0.0)

        result = get_recommendations(_req(user_id), db=db)

        assert result["exceeded_nutrients"] == ["sodium", "sugar"]
        assert result["exceeded_label"] == "나트륨·당류 초과"

    def test_no_exceeded_nutrients_on_a_clean_day(self, db):
        user_id = make_user(db)
        make_food_item(db, food_name="저염식", sodium_mg=10.0, sugar_g=1.0, caffeine_mg=0.0)

        result = get_recommendations(_req(user_id), db=db)

        assert result["exceeded_nutrients"] == []
        assert result["exceeded_label"] is None

    def test_exceeded_label_does_not_leak_into_per_food_reasons(self, db):
        # exceeded_label은 하루 단위 배너다. 음식마다 붙는 reason은 기존 계약 그대로.
        user_id = make_user(db)
        make_food_log(db, user_id, sodium_mg=DAILY_SODIUM_LIMIT_MG * 1.5)
        make_food_item(db, food_name="저염식", sodium_mg=10.0, sugar_g=1.0, caffeine_mg=0.0)

        result = get_recommendations(_req(user_id), db=db)

        assert all("초과" not in r["reason"] for r in result["recommendations"])


# ── 초과한 영양소 기준 오름차순 정렬 (NULL 최후) ──────────────

class TestSortingWhenANutrientIsExceeded:
    def test_lowest_burden_first(self, db):
        user_id = make_user(db)
        make_food_log(db, user_id, sodium_mg=DAILY_SODIUM_LIMIT_MG * 1.5)
        for name, sodium in [("높음", 300.0), ("낮음", 10.0), ("중간", 100.0)]:
            make_food_item(db, food_name=name, sodium_mg=sodium, sugar_g=1.0, caffeine_mg=0.0)

        result = get_recommendations(_req(user_id), db=db)

        assert _names(result) == ["낮음", "중간", "높음"]

    def test_null_sorts_last_and_is_never_treated_as_zero(self, db):
        # NULL을 0으로 취급하면 "정보가 없는 음식"이 가장 부담 없는 선택지로 맨 앞에 온다.
        #
        # 두 후보의 status를 일부러 똑같이(caution) 맞춘다. 나트륨이 NULL이면 그것만으로
        # caution이 되므로, 비교 대상도 당류 NULL로 caution을 만들어야 이 테스트가
        # status 정렬이 아니라 NULL 정렬 규칙을 실제로 검증한다.
        user_id = make_user(db)
        make_food_log(db, user_id, sodium_mg=DAILY_SODIUM_LIMIT_MG * 1.5)
        make_food_item(db, food_name="나트륨정보없음", sodium_mg=None, sugar_g=1.0, caffeine_mg=0.0)
        make_food_item(db, food_name="나트륨있음", sodium_mg=300.0, sugar_g=None, caffeine_mg=0.0)

        result = get_recommendations(_req(user_id), db=db)

        assert [r["status"] for r in result["recommendations"]] == ["caution", "caution"]
        assert _names(result) == ["나트륨있음", "나트륨정보없음"]

    def test_status_still_outranks_the_burden_sort(self, db):
        # 정렬 1순위는 여전히 status다 — 나트륨이 적어도 avoid면 뒤로 간다.
        user_id = make_user(db)
        make_food_log(db, user_id, sodium_mg=DAILY_SODIUM_LIMIT_MG * 1.5)
        make_food_item(db, food_name="당류초과", sodium_mg=1.0, sugar_g=DAILY_SUGAR_LIMIT_G * 2,
                       caffeine_mg=0.0)
        make_food_item(db, food_name="정상", sodium_mg=200.0, sugar_g=1.0, caffeine_mg=0.0)

        result = get_recommendations(_req(user_id), db=db)

        assert _names(result)[0] == "정상"


# ── 후보 SQL: 샘플링 전에 거른다 ──────────────────────────────

class TestCandidateQueryFiltersBeforeSampling:
    def test_obviously_disqualified_rows_are_excluded(self, db):
        user_id = make_user(db)
        make_food_item(db, food_name="초과", sodium_mg=DAILY_SODIUM_LIMIT_MG * 2,
                       sugar_g=1.0, caffeine_mg=0.0)
        make_food_item(db, food_name="통과", sodium_mg=100.0, sugar_g=1.0, caffeine_mg=0.0)

        result = get_recommendations(_req(user_id), db=db)

        assert _names(result) == ["통과"]

    def test_null_survives_the_filter(self, db):
        # 값이 없다는 것은 큰 값이라는 뜻이 아니다. NULL 행은 후보로 남아 caution이 된다.
        user_id = make_user(db)
        make_food_item(db, food_name="정보없음", sodium_mg=None, sugar_g=1.0, caffeine_mg=0.0)

        result = get_recommendations(_req(user_id), db=db)

        assert _names(result) == ["정보없음"]
        assert result["recommendations"][0]["status"] == "caution"

    def test_filter_uses_remaining_not_the_full_limit(self, db):
        # 오늘 이미 한도의 80%를 먹었으면, 남은 20%를 넘기는 음식은 후보에서 빠진다.
        user_id = make_user(db)
        make_food_log(db, user_id, sodium_mg=DAILY_SODIUM_LIMIT_MG * 0.8)
        make_food_item(db, food_name="남은양초과", sodium_mg=DAILY_SODIUM_LIMIT_MG * 0.5,
                       sugar_g=1.0, caffeine_mg=0.0)
        make_food_item(db, food_name="남은양이내", sodium_mg=DAILY_SODIUM_LIMIT_MG * 0.1,
                       sugar_g=1.0, caffeine_mg=0.0)

        result = get_recommendations(_req(user_id), db=db)

        assert _names(result) == ["남은양이내"]

    def test_exceeded_nutrient_adds_no_predicate_so_the_pool_is_not_emptied(self, db):
        # remaining == 0일 때 `sodium_mg <= 0` 조건을 걸면 후보 풀이 통째로 빈다 —
        # 판정 게이트에서 고친 것과 똑같은 버그의 SQL 버전.
        user_id = make_user(db)
        make_food_log(db, user_id, sodium_mg=DAILY_SODIUM_LIMIT_MG * 1.5)
        make_food_item(db, food_name="나트륨있음", sodium_mg=500.0, sugar_g=1.0, caffeine_mg=0.0)

        result = get_recommendations(_req(user_id), db=db)

        assert _names(result) == ["나트륨있음"]

    def test_empty_pool_returns_the_guidance_message_with_exceeded_fields(self, db):
        user_id = make_user(db)
        make_food_log(db, user_id, sodium_mg=DAILY_SODIUM_LIMIT_MG * 1.5)

        result = get_recommendations(_req(user_id), db=db)

        assert result["recommendations"] == []
        assert "message" in result
        assert result["exceeded_nutrients"] == ["sodium"]
        assert result["exceeded_label"] == "나트륨 초과"

    def test_only_allowed_source_is_used(self, db):
        user_id = make_user(db)
        make_food_item(db, food_name="허용", sodium_mg=10.0, sugar_g=1.0, caffeine_mg=0.0)
        make_food_item(db, food_name="비허용", sodium_mg=10.0, sugar_g=1.0, caffeine_mg=0.0,
                       data_source="food_nutrition_api")

        result = get_recommendations(_req(user_id), db=db)

        assert _names(result) == ["허용"]


# ── 카테고리 필터: 단일/다중/빈 값 ────────────────────────────

class TestCategoryFilter:
    @pytest.fixture(autouse=True)
    def _catalog(self, db):
        for name, category in [
            ("빵1", "빵 및 과자류"),
            ("빵2", "빵 및 과자류"),
            ("음료1", "음료 및 차류"),
            ("밥1", "밥류"),
        ]:
            make_food_item(db, food_name=name, category=category,
                           sodium_mg=10.0, sugar_g=1.0, caffeine_mg=0.0)

    def test_single_string_category_still_works(self, db):
        # 기존 클라이언트는 문자열 하나를 보낸다 — 계속 동작해야 한다.
        user_id = make_user(db)

        result = get_recommendations(_req(user_id, category="밥류"), db=db)

        assert _names(result) == ["밥1"]

    def test_multiple_categories_are_ored_together(self, db):
        user_id = make_user(db)

        result = get_recommendations(_req(user_id, category=["밥류", "음료 및 차류"]), db=db)

        assert sorted(_names(result)) == ["밥1", "음료1"]

    def test_single_element_list_behaves_like_a_string(self, db):
        user_id = make_user(db)

        result = get_recommendations(_req(user_id, category=["밥류"]), db=db)

        assert _names(result) == ["밥1"]

    def test_empty_list_means_all_categories(self, db):
        user_id = make_user(db)

        result = get_recommendations(_req(user_id, category=[]), db=db)

        assert sorted(_names(result)) == ["밥1", "빵1", "빵2", "음료1"]

    def test_omitted_category_means_all_categories(self, db):
        user_id = make_user(db)

        result = get_recommendations(_req(user_id), db=db)

        assert len(result["recommendations"]) == 4

    def test_three_categories_do_not_desync_the_parameter_list(self, db):
        # IN 절 플레이스홀더 개수와 파라미터 개수가 어긋나면 sqlite3가 예외를 던진다.
        # 영양소 조건까지 함께 붙는 조합에서 특히 어긋나기 쉬웠다.
        user_id = make_user(db)

        result = get_recommendations(
            _req(user_id, category=["밥류", "음료 및 차류", "빵 및 과자류"]), db=db
        )

        assert len(result["recommendations"]) == 4

    def test_category_filter_combines_with_query_and_nutrient_predicates(self, db):
        user_id = make_user(db)
        make_food_log(db, user_id, sodium_mg=DAILY_SODIUM_LIMIT_MG * 0.5)
        make_food_item(db, food_name="빵3", category="빵 및 과자류",
                       sodium_mg=DAILY_SODIUM_LIMIT_MG * 0.9, sugar_g=1.0, caffeine_mg=0.0)

        result = get_recommendations(
            _req(user_id, query="빵", category=["빵 및 과자류", "밥류"]), db=db
        )

        # 빵3은 남은 허용량(50%)을 넘겨 SQL 단계에서 빠지고, 이름에 "빵"이 없는 밥1도 빠진다.
        assert sorted(_names(result)) == ["빵1", "빵2"]


# ── limit ────────────────────────────────────────────────────

class TestLimit:
    def test_limit_caps_the_returned_list(self, db):
        user_id = make_user(db)
        for i in range(8):
            make_food_item(db, food_name=f"음식{i}", sodium_mg=10.0, sugar_g=1.0, caffeine_mg=0.0)

        result = get_recommendations(_req(user_id, limit=3), db=db)

        assert len(result["recommendations"]) == 3


# ── panel_nutrients: 카페인 + 사용자가 고른 영양소 ────────────

class TestPanelNutrientsInResponse:
    def test_caffeine_is_present_even_when_user_selected_three_others(self, db):
        user_id = make_user(db, selected_nutrients="protein,iron,fat")
        make_food_item(db, food_name="음식", sodium_mg=10.0, sugar_g=1.0, caffeine_mg=0.0)

        result = get_recommendations(_req(user_id), db=db)

        assert [n["key"] for n in result["panel_nutrients"]] == [
            "caffeine", "protein", "iron", "fat",
        ]

    def test_panel_is_present_even_when_no_candidates_match(self, db):
        # 후보가 하나도 없어도 상단 카드는 그려져야 한다.
        user_id = make_user(db, selected_nutrients="protein")

        result = get_recommendations(_req(user_id), db=db)

        assert result["recommendations"] == []
        assert [n["key"] for n in result["panel_nutrients"]] == ["caffeine", "protein"]

    def test_directions_travel_with_each_entry(self, db):
        user_id = make_user(db, selected_nutrients="protein,fat,sugar")
        make_food_item(db, food_name="음식", sodium_mg=10.0, sugar_g=1.0, caffeine_mg=0.0)

        by_key = {n["key"]: n for n in get_recommendations(_req(user_id), db=db)["panel_nutrients"]}

        assert by_key["caffeine"]["type"] == "ceiling" and "limit" in by_key["caffeine"]
        assert by_key["protein"]["type"] == "floor" and "target" in by_key["protein"]
        assert by_key["fat"]["type"] == "band" and by_key["fat"]["remaining"] is None

    def test_exceeded_nutrients_field_is_untouched_by_the_panel(self, db):
        # 기존 필드는 판정 게이트가 쓰고 있다. 패널이 추가돼도 그대로여야 한다.
        user_id = make_user(db, selected_nutrients="protein")
        make_food_log(db, user_id, sodium_mg=DAILY_SODIUM_LIMIT_MG * 1.5)
        make_food_item(db, food_name="음식", sodium_mg=10.0, sugar_g=1.0, caffeine_mg=0.0)

        result = get_recommendations(_req(user_id), db=db)

        assert result["exceeded_nutrients"] == ["sodium"]
        assert result["exceeded_label"] == "나트륨 초과"


# ── 영양소 칩 정렬: 방향에 따라 오름/내림 ─────────────────────

class TestSortNutrientDirection:
    @pytest.fixture(autouse=True)
    def _catalog(self, db):
        # 세 후보 모두 possible이 되도록 상한형 값은 낮게 유지한다 —
        # status가 1순위 정렬 키라 그렇지 않으면 방향을 검증할 수 없다.
        for name, protein, sodium in [("적음", 5.0, 300.0), ("많음", 40.0, 100.0), ("중간", 20.0, 200.0)]:
            make_food_item(db, food_name=name, protein_g=protein, sodium_mg=sodium,
                           sugar_g=1.0, caffeine_mg=0.0)

    def test_ceiling_chip_sorts_ascending(self, db):
        # 상한형: 남은 허용량에 부담이 적은 것부터.
        user_id = make_user(db)

        result = get_recommendations(_req(user_id, sort_nutrient="sodium"), db=db)

        assert _names(result) == ["많음", "중간", "적음"]  # 나트륨 100 < 200 < 300

    def test_floor_chip_sorts_descending(self, db):
        # 하한형: 아직 채워야 하는 것이므로 많이 든 것부터. 방향이 반대다.
        user_id = make_user(db)

        result = get_recommendations(_req(user_id, sort_nutrient="protein"), db=db)

        assert _names(result) == ["많음", "중간", "적음"]  # 단백질 40 > 20 > 5

    def test_chip_overrides_the_automatic_exceeded_sort(self, db):
        # 사용자가 명시적으로 고른 기준이 자동 초과 정렬보다 우선한다.
        user_id = make_user(db)
        make_food_log(db, user_id, sodium_mg=DAILY_SODIUM_LIMIT_MG * 1.5)

        result = get_recommendations(_req(user_id, sort_nutrient="protein"), db=db)

        assert result["exceeded_nutrients"] == ["sodium"]
        assert _names(result) == ["많음", "중간", "적음"]  # 나트륨 오름차순이 아니라 단백질 내림차순

    def test_unknown_sort_nutrient_is_rejected(self, db):
        with pytest.raises(ValueError):
            _req(make_user(db), sort_nutrient="potassium")


# ── band 칩은 재정렬하지 않는다 ───────────────────────────────

class TestBandChipDoesNotReorder:
    """의도적 선택이다: 경계가 둘이라 한 방향으로 줄을 세우면 반드시 다른 쪽 경계를
    무시하게 된다.

    "재정렬하지 않는다"를 두 호출의 순서를 비교해 검증할 수는 없다 — 정렬 키가 없으면
    남는 순서는 ORDER BY RANDOM()이라 호출마다 달라지기 때문이다. 대신 status 다음의
    결정적 타이브레이크인 data_confidence로 순서를 고정하고, 오름차순·내림차순이 각각
    그 순서를 뒤집을 값 배치를 써서 두 방향 모두 일어나지 않음을 확인한다.
    신뢰도는 카페인 값 유무로 갈린다(있으면 0.9, 없으면 0.65 — data_confidence.py).
    """

    def test_band_chip_does_not_sort_ascending(self, db):
        user_id = make_user(db)
        make_food_item(db, food_name="신뢰높음", iron_mg=100.0, caffeine_mg=0.0,
                       sugar_g=1.0, sodium_mg=10.0)
        make_food_item(db, food_name="신뢰낮음", iron_mg=1.0, caffeine_mg=None,
                       sugar_g=1.0, sodium_mg=10.0)

        result = get_recommendations(_req(user_id, sort_nutrient="iron"), db=db)

        # 철분 오름차순이었다면 신뢰낮음(1mg)이 앞에 왔을 것이다.
        assert _names(result) == ["신뢰높음", "신뢰낮음"]

    def test_band_chip_does_not_sort_descending(self, db):
        user_id = make_user(db)
        make_food_item(db, food_name="신뢰높음", iron_mg=1.0, caffeine_mg=0.0,
                       sugar_g=1.0, sodium_mg=10.0)
        make_food_item(db, food_name="신뢰낮음", iron_mg=100.0, caffeine_mg=None,
                       sugar_g=1.0, sodium_mg=10.0)

        result = get_recommendations(_req(user_id, sort_nutrient="iron"), db=db)

        # 철분 내림차순이었다면 신뢰낮음(100mg)이 앞에 왔을 것이다.
        assert _names(result) == ["신뢰높음", "신뢰낮음"]


# ── NULL이 대부분인 컬럼으로 정렬해도 목록이 비지 않는다 ────────

class TestSortOnASparselyPopulatedColumn:
    """실제 데이터에서 탄수화물 65.4% / 지방 68.2% / 철분 78.1%가 NULL이다.
    이런 컬럼으로 정렬해도 목록이 무너지면 안 된다 — NULL은 뒤로 밀릴 뿐,
    걸러지지 않는다."""

    def test_list_is_not_collapsed_when_most_rows_are_null(self, db):
        user_id = make_user(db)
        for i in range(4):
            make_food_item(db, food_name=f"정보없음{i}", carbohydrate_g=None,
                           sodium_mg=10.0, sugar_g=1.0, caffeine_mg=0.0)
        make_food_item(db, food_name="값있음", carbohydrate_g=30.0,
                       sodium_mg=10.0, sugar_g=1.0, caffeine_mg=0.0)

        result = get_recommendations(_req(user_id, sort_nutrient="carbohydrate"), db=db)

        assert len(result["recommendations"]) == 5  # 하나도 사라지지 않는다
        assert _names(result)[0] == "값있음"  # 값이 있는 행이 먼저
        assert all(n.startswith("정보없음") for n in _names(result)[1:])

    def test_all_null_column_still_returns_every_row(self, db):
        # 전부 NULL이어도 빈 화면이 되면 안 된다.
        user_id = make_user(db)
        for i in range(3):
            make_food_item(db, food_name=f"음식{i}", iron_mg=None,
                           sodium_mg=10.0, sugar_g=1.0, caffeine_mg=0.0)

        result = get_recommendations(_req(user_id, sort_nutrient="carbohydrate"), db=db)

        assert len(result["recommendations"]) == 3

    def test_null_sorts_last_in_descending_direction_too(self, db):
        # 내림차순에서 NULL을 0으로 보면 맨 뒤가 맞지만, 큰 값으로 보면 맨 앞에 온다.
        # 어느 쪽으로도 해석하지 않는다는 것을 방향을 바꿔서도 확인한다.
        user_id = make_user(db)
        make_food_item(db, food_name="정보없음", protein_g=None,
                       sodium_mg=10.0, sugar_g=1.0, caffeine_mg=0.0)
        make_food_item(db, food_name="적음", protein_g=1.0,
                       sodium_mg=10.0, sugar_g=1.0, caffeine_mg=0.0)

        result = get_recommendations(_req(user_id, sort_nutrient="protein"), db=db)

        assert _names(result) == ["적음", "정보없음"]


# ── 카테고리 다중 선택: 라운드로빈 배분 ────────────────────────
# 확인된 편중: 빵 및 과자류 44.1% + 음료 및 차류 29.6% = 전체의 73.7%.
# 빵 및 과자류 + 밥류만 고르면 필터링된 풀의 95.3%가 빵이 된다.

class TestCategoryBalancing:
    def test_round_robin_splits_evenly_across_two_categories(self, db):
        user_id = make_user(db)
        for i in range(5):
            make_food_item(db, food_name=f"밥{i}", category="밥류",
                           sodium_mg=10.0, sugar_g=1.0, caffeine_mg=0.0)
        for i in range(5):
            make_food_item(db, food_name=f"빵{i}", category="빵 및 과자류",
                           sodium_mg=10.0, sugar_g=1.0, caffeine_mg=0.0)

        result = get_recommendations(
            _req(user_id, category=["밥류", "빵 및 과자류"], limit=6), db=db
        )

        categories = [r["category"] for r in result["recommendations"]]
        assert categories.count("밥류") == 3
        assert categories.count("빵 및 과자류") == 3

    def test_starved_category_does_not_shrink_the_response(self, db):
        # 밥류가 쿼터(5)를 채우지 못해도 응답 전체가 짧아지지 않는다 — 남는
        # 자리는 빵으로 채운다. 카테고리를 다 합친 후보 자체가 limit보다 적을
        # 때만(여기서는 22개 > 10) 응답이 짧아져야 한다.
        user_id = make_user(db)
        for i in range(2):
            make_food_item(db, food_name=f"밥{i}", category="밥류",
                           sodium_mg=10.0, sugar_g=1.0, caffeine_mg=0.0)
        for i in range(20):
            make_food_item(db, food_name=f"빵{i}", category="빵 및 과자류",
                           sodium_mg=10.0, sugar_g=1.0, caffeine_mg=0.0)

        result = get_recommendations(
            _req(user_id, category=["밥류", "빵 및 과자류"], limit=10), db=db
        )

        assert len(result["recommendations"]) == 10
        categories = [r["category"] for r in result["recommendations"]]
        assert categories.count("밥류") == 2
        assert categories.count("빵 및 과자류") == 8

    def test_avoid_never_precedes_possible_across_categories(self, db):
        # 카테고리 배분이 상태 등급을 절대 넘지 않는다는 것을 직접 검증한다.
        # 이미 초과한 영양소는 게이트에서 빠지므로(오늘 나트륨을 이미 넘긴
        # 것으로는 avoid를 만들 수 없다), 여기서는 remaining > 0인 당류를
        # 이 음식 자체가 넘기게 해서 avoid를 만든다 — 정상적인(초과-면제가
        # 아닌) avoid 경로다.
        user_id = make_user(db)
        for i in range(3):
            make_food_item(db, food_name=f"당류과다{i}", category="밥류",
                           sugar_g=DAILY_SUGAR_LIMIT_G * 2, sodium_mg=10.0, caffeine_mg=0.0)
        for i in range(5):
            make_food_item(db, food_name=f"저당식{i}", category="빵 및 과자류",
                           sodium_mg=10.0, sugar_g=1.0, caffeine_mg=0.0)

        result = get_recommendations(
            _req(user_id, category=["밥류", "빵 및 과자류"], limit=3), db=db
        )

        assert len(result["recommendations"]) == 3
        assert all(r["status"] == "possible" for r in result["recommendations"])
        assert all(r["category"] == "빵 및 과자류" for r in result["recommendations"])

    def test_categories_interleave_within_a_tier(self, db):
        # ORDER BY RANDOM()에 좌우되지 않는 결정적 검증: 라운드로빈의 카테고리
        # 순회 순서는 req.category 순서 고정이라, 신뢰도/부담 동점 처리나 SQL의
        # 행 순서와 무관하게 "밥,빵,밥,빵,밥,빵" 패턴이 항상 나온다. 특정 음식이
        # 몇 번째로 뽑히는지가 아니라 카테고리 자리 순서만 확인한다.
        user_id = make_user(db)
        for i in range(3):
            make_food_item(db, food_name=f"밥{i}", category="밥류",
                           sodium_mg=10.0, sugar_g=1.0, caffeine_mg=0.0)
        for i in range(3):
            make_food_item(db, food_name=f"빵{i}", category="빵 및 과자류",
                           sodium_mg=10.0, sugar_g=1.0, caffeine_mg=0.0)

        result = get_recommendations(
            _req(user_id, category=["밥류", "빵 및 과자류"], limit=6), db=db
        )

        categories = [r["category"] for r in result["recommendations"]]
        assert categories == ["밥류", "빵 및 과자류", "밥류", "빵 및 과자류", "밥류", "빵 및 과자류"]

    def test_single_category_selection_is_unaffected(self, db):
        # len(categories) == 1은 라운드로빈 경로를 아예 타지 않는다 — 기존과
        # 동일하게 status/burden/confidence 순서 그대로 반환된다.
        user_id = make_user(db)
        for i in range(4):
            make_food_item(db, food_name=f"밥{i}", category="밥류",
                           sodium_mg=10.0, sugar_g=1.0, caffeine_mg=0.0)

        result = get_recommendations(_req(user_id, category=["밥류"], limit=10), db=db)

        assert len(result["recommendations"]) == 4
        assert all(r["category"] == "밥류" for r in result["recommendations"])


class TestCategoryPoolIsNotStarvedBySharedSampling:
    def test_small_category_survives_a_binding_pool_limit(self, db, monkeypatch):
        # 기본 _CANDIDATE_POOL_LIMIT(500)은 이 테스트 규모(99행)에서 사실상 전부를
        # 통과시켜 두 구현(공유 샘플링 vs 카테고리별 분할)이 같은 결과를 낸다 —
        # 그러면 이 테스트가 아무것도 보장하지 못한다. 풀 한도를 실제로 걸리는
        # 값(10)으로 낮춰야 두 구현이 갈린다.
        monkeypatch.setattr(recommendation, "_CANDIDATE_POOL_LIMIT", 10)

        user_id = make_user(db)
        for i in range(98):
            make_food_item(db, food_name=f"밥{i}", category="밥류",
                           sodium_mg=10.0, sugar_g=1.0, caffeine_mg=0.0)
        make_food_item(db, food_name="희귀빵", category="빵 및 과자류",
                       sodium_mg=10.0, sugar_g=1.0, caffeine_mg=0.0)

        result = get_recommendations(
            _req(user_id, category=["밥류", "빵 및 과자류"], limit=10), db=db
        )

        # 카테고리별 분할 쿼리에서 빵 전용 쿼리는 LIMIT 5(10 // 2)를 걸어도
        # 빵이 1행뿐이므로 항상 그 1행을 돌려준다 — 결정적이다. 공유 샘플링이었다면
        # 99행 중 10행을 무작위로 뽑을 때 그 1행이 빠질 확률이 약 90%였다
        # (아래 프로덕션 코드 없이 진행한 별도 확인에서 실제로 실패를 관찰함).
        categories = [r["category"] for r in result["recommendations"]]
        assert "빵 및 과자류" in categories
