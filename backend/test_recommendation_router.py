"""POST /recommendations 라우터 테스트.

이 라우터에는 그동안 테스트가 하나도 없었다. 판정 규칙(test_recommendation_model.py)과
달리 여기서만 결정되는 것들이 있다:

- 후보 SQL: 랜덤 샘플링 *전에* 영양소 조건으로 거르는가, NULL이 살아남는가,
  이미 초과한 영양소로는 조건을 만들지 않는가
- 다중 카테고리 IN 절과 파라미터 개수
- 이미 초과한 영양소 기준 정렬(NULL 최후) 및 exceeded_nutrients/exceeded_label 응답
"""
import pytest

from backend.models import RecommendationRequest
from backend.nutrition_constants import DAILY_SODIUM_LIMIT_MG, DAILY_SUGAR_LIMIT_G
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
