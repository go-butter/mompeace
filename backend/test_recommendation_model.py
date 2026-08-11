"""
backend/recommendation_model.py 의 핵심 안전 판정 로직 테스트.

대상:
- judge_food_rules(): 누적 섭취 비율 기반 1차 판정 (possible/caution/avoid)
- apply_safety_guard(): 임계 초과 등 안전 방향 보정 (절대 하향 금지)

DAILY_LIMITS (1일 허용 기준, 임신 시기 불변)을 직접 import해서 사용하므로,
이 파일의 수치가 나중에 바뀌어도 테스트는 "남은 허용량 안에 들어오면 possible,
100%를 넘기면 avoid"라는 *관계*를 검증하지, 하드코딩된 mg/g 값을 검증하지 않는다.
caution은 영양성분 값을 믿을 수 없을 때만 나오며, 섭취량 비율로는 발생하지 않는다.
"""
import inspect

import pytest

from backend.recommendation_model import (
    DAILY_LIMITS,
    STATUS_RANK,
    apply_safety_guard,
    compute_nutrient_budget,
    format_exceeded_label,
    judge_food_rules,
    make_reason,
    recommend_food,
)


def make_food(**overrides):
    """안전한 기본값을 가진 food dict. 필요한 필드만 덮어써서 사용.

    category/subcategory 기본값은 카페인 관련성 티어가 CAFFEINE_POSSIBLE인 조합이다
    (backend/caffeine_relevance.py). 이 파일의 기존 테스트는 대부분 카페인 판정을
    다루므로, 카페인이 의미 있는 식품군을 기본값으로 두어야 각 테스트가 검증하려던
    규칙이 그대로 발동한다. FREE/NOT_MEASURED 동작을 보려면 명시적으로 덮어쓴다.

    실제 food_items 행은 항상 category/subcategory를 갖는다 (19,514행 전부 non-NULL,
    두 호출부 모두 `SELECT * FROM food_items`) — 이 기본값은 그 현실을 픽스처에
    반영한 것이지, 없는 컬럼을 지어낸 것이 아니다.
    """
    defaults = {
        "food_name": "테스트 음식",
        "caffeine_mg": 0.0,
        "sugar_g": 0.0,
        "sodium_mg": 0.0,
        "data_source": "dish_db_download",
        "category": "음료 및 차류",
        "subcategory": "커피",
    }
    defaults.update(overrides)
    return defaults


def make_intake(**overrides):
    defaults = {"caffeine_mg": 0.0, "sugar_g": 0.0, "sodium_mg": 0.0}
    defaults.update(overrides)
    return defaults


# ── judge_food_rules: 경계값 ──────────────────────────────

class TestJudgeFoodRulesBoundaries:
    def test_zero_intake_is_possible(self):
        food = make_food()
        status = judge_food_rules(food, make_intake())
        assert status == "possible"

    @pytest.mark.parametrize("nutrient,key", [
        ("caffeine", "caffeine_mg"),
        ("sugar", "sugar_g"),
        ("sodium", "sodium_mg"),
    ])
    def test_just_under_limit_is_possible(self, nutrient, key):
        # 남은 허용량 안에 들어오면(99%) 추천 대상이다 — 완충 구간 없이 100%까지 possible.
        limit = DAILY_LIMITS[nutrient]
        food = make_food(**{key: limit * 0.99})
        status = judge_food_rules(food, make_intake())
        assert status == "possible"

    @pytest.mark.parametrize("nutrient,key", [
        ("caffeine", "caffeine_mg"),
        ("sugar", "sugar_g"),
        ("sodium", "sodium_mg"),
    ])
    def test_just_over_100_percent_is_avoid(self, nutrient, key):
        limit = DAILY_LIMITS[nutrient]
        food = make_food(**{key: limit * 1.01})
        status = judge_food_rules(food, make_intake())
        assert status == "avoid"

    @pytest.mark.parametrize("nutrient,key", [
        ("caffeine", "caffeine_mg"),
        ("sugar", "sugar_g"),
        ("sodium", "sodium_mg"),
    ])
    def test_exactly_at_limit_is_possible(self, nutrient, key):
        # 경계는 > 1.0 이므로 정확히 100%는 아직 possible이다.
        limit = DAILY_LIMITS[nutrient]
        food = make_food(**{key: limit})
        status = judge_food_rules(food, make_intake())
        assert status == "possible"

    def test_ratio_alone_never_produces_caution(self):
        # caution은 영양성분 값을 믿을 수 없을 때만 나온다. 값이 전부 알려져 있으면
        # 0%~100% 구간 어디에서도 caution이 나오지 않는다.
        limit = DAILY_LIMITS["sodium"]
        for fraction in (0.5, 0.71, 0.85, 0.99, 1.0):
            food = make_food(sodium_mg=limit * fraction)
            assert judge_food_rules(food, make_intake()) == "possible"

    def test_cumulative_intake_plus_food_can_tip_over(self):
        # 오늘 이미 60% 섭취한 상태에서 50%를 더 먹으면 110% → avoid
        limit = DAILY_LIMITS["sugar"]
        food = make_food(sugar_g=limit * 0.5)
        intake = make_intake(sugar_g=limit * 0.6)
        status = judge_food_rules(food, intake)
        assert status == "avoid"

    def test_cumulative_intake_within_limit_stays_possible(self):
        # 오늘 이미 60% 섭취한 상태에서 39%를 더 먹으면 99% → 아직 남은 허용량 안이다.
        limit = DAILY_LIMITS["sugar"]
        food = make_food(sugar_g=limit * 0.39)
        intake = make_intake(sugar_g=limit * 0.6)
        status = judge_food_rules(food, intake)
        assert status == "possible"

    def test_caffeine_missing_with_keyword_is_caution(self):
        # 카페인 정보가 없는 음식인데 이름에 카페인 키워드가 있으면 caution
        food = make_food(food_name="아이스 라떼", caffeine_mg=None, data_source="dish_db_download")
        status = judge_food_rules(food, make_intake())
        assert status == "caution"

    def test_caffeine_missing_without_keyword_is_possible(self):
        food = make_food(food_name="흰쌀밥", caffeine_mg=None, data_source="dish_db_download")
        status = judge_food_rules(food, make_intake())
        assert status == "possible"


# ── apply_safety_guard: 안전장치 ──────────────────────────

class TestApplySafetyGuard:
    @pytest.mark.parametrize("key,limit_key", [
        ("caffeine_mg", "caffeine"),
        ("sugar_g", "sugar"),
        ("sodium_mg", "sodium"),
    ])
    def test_absolute_excess_forces_avoid(self, key, limit_key):
        limit = DAILY_LIMITS[limit_key]
        food = make_food(**{key: limit * 1.5})
        result = apply_safety_guard(
            "possible", food,
            today_intake=make_intake(),
        )
        assert result == "avoid"

    def test_never_downgrades_below_input_status(self):
        # 안전장치는 always upgrade-only: avoid로 들어온 건 절대 내려가지 않는다
        food = make_food()  # 모든 영양소 0, 안전한 음식
        result = apply_safety_guard(
            "avoid", food,
            today_intake=make_intake(),
        )
        assert result == "avoid"

    def test_never_downgrades_caution_to_possible(self):
        food = make_food()
        result = apply_safety_guard(
            "caution", food,
            today_intake=make_intake(),
        )
        assert STATUS_RANK[result] >= STATUS_RANK["caution"]

    def test_missing_sugar_or_sodium_forces_at_least_caution(self):
        food = make_food(sugar_g=None)
        result = apply_safety_guard(
            "possible", food,
            today_intake=make_intake(),
        )
        assert result == "caution"

    def test_missing_sodium_forces_at_least_caution(self):
        food = make_food(sodium_mg=None)
        result = apply_safety_guard(
            "possible", food,
            today_intake=make_intake(),
        )
        assert result == "caution"

    @pytest.mark.parametrize("source", ["food_nutrition_api", "processed_food_db_download"])
    def test_caffeine_unsupported_sources_always_treated_as_missing(self, source):
        # food_nutrition_api / processed_food_db_download 는 caffeine_mg 값이
        # 있어도(예: 0으로 잘못 채워졌어도) 항상 missing 으로 처리되어야 한다.
        food = make_food(food_name="콜드브루", caffeine_mg=0, data_source=source)
        result = apply_safety_guard(
            "possible", food,
            today_intake=make_intake(),
        )
        # 카페인 키워드("콜드브루")가 있고 missing 처리되므로 최소 caution
        assert result == "caution"

    def test_caffeine_missing_real_value_not_counted_toward_ratio(self):
        # data_source가 missing-소스인 경우, 실제 caffeine_mg 값이 커도
        # 절대 초과(avoid) 트리거에 반영되면 안 된다 (missing 처리 정의상).
        limit = DAILY_LIMITS["caffeine"]
        food = make_food(
            food_name="커피",  # CAFFEINE_KEYWORDS에 포함된 단어
            caffeine_mg=limit * 5,  # 명백히 과한 값이지만 missing 소스
            data_source="food_nutrition_api",
        )
        result = apply_safety_guard(
            "possible", food,
            today_intake=make_intake(),
        )
        # avoid 가 아니라 caution 이어야 함 (missing + 키워드 규칙만 적용)
        assert result == "caution"

    def test_sensitivity_adjustment_loosens_limit(self):
        # user_adj가 양수(+)면 기준이 완화되어 동일 섭취량이 avoid가 안 될 수 있다
        limit = DAILY_LIMITS["sodium"]
        food = make_food(sodium_mg=limit * 1.05)  # 조정 없으면 avoid
        result_no_adj = apply_safety_guard(
            "possible", food,
            today_intake=make_intake(),
        )
        result_with_adj = apply_safety_guard(
            "possible", food,
            today_intake=make_intake(),
            user_adj={"sodium": 0.15},  # 최대 완화
        )
        assert result_no_adj == "avoid"
        assert result_with_adj != "avoid"

    def test_caffeine_missing_with_keyword_triggers_caution_independently(self):
        # judge_food_rules에도 동일한 missing+키워드 → caution 규칙이 있지만,
        # 이 테스트는 apply_safety_guard 단독으로도 그 규칙을 강제하는지 확인한다.
        # 즉 judge_food_rules가 호출되지 않거나 다른 값을 반환하더라도,
        # 안전장치 레이어 자체가 독립적으로 caution 이상을 보장해야 한다.
        food = make_food(food_name="아이스 라떼", caffeine_mg=None, data_source="dish_db_download")
        result = apply_safety_guard(
            "possible", food,
            today_intake=make_intake(),
        )
        assert result == "caution"


# ── make_reason: 한국어 이유 + reason_nutrient 태그 ────────

class TestMakeReason:
    def test_avoid_picks_caffeine_when_caffeine_exceeds_limit(self):
        limit = DAILY_LIMITS["caffeine"]
        food = make_food(caffeine_mg=limit * 1.1)
        reason, reason_nutrient = make_reason(
            "avoid", food, today_intake=make_intake(),
        )
        assert "카페인" in reason
        assert reason_nutrient == "caffeine"

    def test_avoid_picks_sugar_when_sugar_exceeds_limit(self):
        limit = DAILY_LIMITS["sugar"]
        food = make_food(sugar_g=limit * 1.1)
        reason, reason_nutrient = make_reason(
            "avoid", food, today_intake=make_intake(),
        )
        assert "당류" in reason
        assert reason_nutrient == "sugar"

    def test_avoid_picks_sodium_when_sodium_exceeds_limit(self):
        limit = DAILY_LIMITS["sodium"]
        food = make_food(sodium_mg=limit * 1.1)
        reason, reason_nutrient = make_reason(
            "avoid", food, today_intake=make_intake(),
        )
        assert "나트륨" in reason
        assert reason_nutrient == "sodium"

    def test_avoid_falls_back_to_generic_message_when_no_single_nutrient_exceeds(self):
        # avoid로 들어왔지만(예: 상위 로직에서 강제 승급) 개별 영양소 비율이
        # 100%를 넘지 않는 경우 일반 문구 + reason_nutrient=None 이어야 한다
        food = make_food()
        reason, reason_nutrient = make_reason(
            "avoid", food, today_intake=make_intake(),
        )
        assert reason_nutrient is None
        assert "비추천" in reason

    def test_caution_reason_never_cites_a_high_ratio(self):
        # 비율이 아무리 높아도(99%) caution 이유는 섭취량을 근거로 대지 않는다 —
        # 그 구간은 이제 possible이고, caution은 데이터 문제에만 붙기 때문이다.
        limit = DAILY_LIMITS["sodium"]
        food = make_food(sodium_mg=limit * 0.99)
        reason, reason_nutrient = make_reason(
            "caution", food, today_intake=make_intake(),
        )
        assert reason_nutrient is None
        assert "높아" not in reason
        assert "가까워지고" not in reason

    def test_caution_missing_sugar_names_sugar(self):
        food = make_food(sugar_g=None)
        reason, reason_nutrient = make_reason(
            "caution", food, today_intake=make_intake(),
        )
        assert "당류" in reason
        assert "정보가 없어" in reason
        assert reason_nutrient == "sugar"

    def test_caution_missing_sodium_names_sodium(self):
        food = make_food(sodium_mg=None)
        reason, reason_nutrient = make_reason(
            "caution", food, today_intake=make_intake(),
        )
        assert "나트륨" in reason
        assert "정보가 없어" in reason
        assert reason_nutrient == "sodium"

    def test_caution_falls_back_to_generic_data_message(self):
        # 어떤 성분이 문제인지 지목할 수 없는 경우(카페인은 FREE 티어라 언급하지 않고,
        # 당류·나트륨은 값이 있는 경우)에도 이유는 데이터 문제를 가리켜야 한다.
        food = make_food(
            food_name="유자차", caffeine_mg=None,
            category="음료 및 차류", subcategory="유자차",
        )
        reason, reason_nutrient = make_reason(
            "caution", food, today_intake=make_intake(),
        )
        assert reason_nutrient is None
        assert "정확히 확인하기 어려워요" in reason

    def test_possible_with_real_caffeine_value_mentions_caffeine(self):
        # caffeine_mg가 missing이 아닌 실제 값으로 존재하면 possible이어도
        # 카페인 안내 문구를 우선 반환해야 한다
        food = make_food(caffeine_mg=30.0, data_source="dish_db_download")
        reason, reason_nutrient = make_reason(
            "possible", food, today_intake=make_intake(),
        )
        assert "카페인" in reason
        assert reason_nutrient == "caffeine"

    def test_possible_without_caffeine_returns_generic_low_burden_message(self):
        food = make_food()  # caffeine_mg=0.0 (실제 값, missing 아님)
        reason, reason_nutrient = make_reason(
            "possible", food, today_intake=make_intake(),
        )
        assert reason_nutrient is None
        assert "부담이 낮은" in reason


# ── 카페인 관련성 티어 연동 ────────────────────────────────
# "정보 없음"과 "확인된 0"을 구분하기 위한 규칙 (backend/caffeine_relevance.py).
# 티어는 category/subcategory로만 결정되고, 카페인 값이 실제로 있으면(missing이 아니면)
# 티어와 무관하게 그 값으로 판정한다.

class TestCaffeineTierIntegration:
    def test_possible_tier_with_missing_caffeine_forces_caution(self):
        # 핵심 변경: 카페인이 있을 수 있는 식품군인데 값이 없으면 조용히 넘어가지 않는다.
        food = make_food(
            food_name="딸기 스무디", caffeine_mg=None,
            category="음료 및 차류", subcategory="스무디",
        )
        result = apply_safety_guard(
            "possible", food,
            today_intake=make_intake(),
        )
        assert result == "caution"

    def test_free_tier_with_missing_caffeine_stays_possible(self):
        # 유자차는 실측 28행 전부 0.0 — NULL을 확인된 0으로 취급해도 되는 식품군.
        food = make_food(
            food_name="유자차", caffeine_mg=None,
            category="음료 및 차류", subcategory="유자차",
        )
        result = apply_safety_guard(
            "possible", food,
            today_intake=make_intake(),
        )
        assert result == "possible"

    def test_bakery_category_is_free_regardless_of_subcategory(self):
        food = make_food(
            food_name="초코 케이크", caffeine_mg=None,
            category="빵 및 과자류", subcategory="케이크",
        )
        result = apply_safety_guard(
            "possible", food,
            today_intake=make_intake(),
        )
        assert result == "possible"

    def test_not_measured_tier_with_missing_caffeine_stays_possible(self):
        # 국·탕류는 카페인을 잰 적이 없다. 값이 없다고 경고하면 근거 없는 경고가 된다.
        food = make_food(
            food_name="호박 된장국", caffeine_mg=None,
            category="국 및 탕류", subcategory="된장국",
        )
        result = apply_safety_guard(
            "possible", food,
            today_intake=make_intake(),
        )
        assert result == "possible"

    def test_herbal_tea_is_flagged(self):
        # 허브차에 자스민티(녹차)·얼그레이(홍차)가 묶여 있어 POSSIBLE로 분류했다.
        food = make_food(
            food_name="자스민티 아이스(ICED)", caffeine_mg=None,
            category="음료 및 차류", subcategory="허브차",
        )
        result = apply_safety_guard(
            "possible", food,
            today_intake=make_intake(),
        )
        assert result == "caution"

    def test_unlisted_subcategory_in_measured_category_is_flagged(self):
        # 실측 0건이라 목록에 없는 subcategory는 기본값(POSSIBLE)으로 처리된다.
        food = make_food(
            food_name="카페라떼", caffeine_mg=None,
            category="음료 및 차류", subcategory="카페라떼",
        )
        result = apply_safety_guard(
            "possible", food,
            today_intake=make_intake(),
        )
        assert result == "caution"

    def test_known_caffeine_value_is_unaffected_by_tier(self):
        # 값이 있으면 티어와 무관하게 그 값으로 판정한다 (티어는 missing일 때만 개입).
        food = make_food(
            food_name="딸기 스무디", caffeine_mg=0.0,
            category="음료 및 차류", subcategory="스무디",
        )
        result = apply_safety_guard(
            "possible", food,
            today_intake=make_intake(),
        )
        assert result == "possible"

    def test_tier_rule_uses_is_caffeine_missing_not_raw_none(self):
        # 카페인 미제공 소스는 값이 있어도 missing이므로 티어 규칙도 발동해야 한다.
        # (raw None 검사였다면 caffeine_mg=0이 있으니 발동하지 않았을 것이다.)
        food = make_food(
            food_name="이름에 단서 없음", caffeine_mg=0,
            data_source="food_nutrition_api",
            category="음료 및 차류", subcategory="스무디",
        )
        result = apply_safety_guard(
            "possible", food,
            today_intake=make_intake(),
        )
        assert result == "caution"

    def test_tier_rule_never_downgrades(self):
        # 안전장치 전체의 upgrade-only 성질은 티어 규칙에도 그대로 적용된다.
        food = make_food(
            food_name="유자차", caffeine_mg=None,
            category="음료 및 차류", subcategory="유자차",
        )
        result = apply_safety_guard(
            "avoid", food,
            today_intake=make_intake(),
        )
        assert result == "avoid"

    def test_judge_food_rules_is_not_affected_by_tier(self):
        # 티어 검사는 apply_safety_guard/make_reason에만 있다 (당류·나트륨 missing
        # 규칙과 같은 위치). judge_food_rules는 건드리지 않았다.
        food = make_food(
            food_name="이름에 단서 없음", caffeine_mg=None,
            category="음료 및 차류", subcategory="스무디",
        )
        assert judge_food_rules(food, make_intake()) == "possible"

    def test_recommend_food_end_to_end_flags_missing_caffeine(self):
        result = recommend_food(
            food=make_food(
                food_name="딸기 스무디", caffeine_mg=None,
                category="음료 및 차류", subcategory="스무디",
            ),
            today_intake=make_intake(),
        )
        assert result["status"] == "caution"
        assert result["reason_nutrient"] == "caffeine"


class TestCaffeineTierReason:
    def test_possible_tier_missing_caffeine_reason_names_caffeine(self):
        food = make_food(
            food_name="이름에 단서 없음", caffeine_mg=None,
            category="음료 및 차류", subcategory="스무디",
        )
        reason, reason_nutrient = make_reason(
            "caution", food, today_intake=make_intake(),
        )
        assert "카페인" in reason
        assert "정보가 없어요" in reason
        assert reason_nutrient == "caffeine"

    def test_tier_reason_is_more_specific_than_generic_missing_message(self):
        # 당류까지 없는 경우에도, 어떤 성분인지 아는 카페인 문구가 우선한다.
        food = make_food(
            food_name="이름에 단서 없음", caffeine_mg=None, sugar_g=None,
            category="음료 및 차류", subcategory="스무디",
        )
        reason, reason_nutrient = make_reason(
            "caution", food, today_intake=make_intake(),
        )
        assert reason_nutrient == "caffeine"
        assert "당류" not in reason

    def test_free_tier_missing_caffeine_does_not_name_caffeine(self):
        # FREE 식품군은 카페인을 지목하지 않는다. 당류가 없으면 당류 쪽을 지목한다.
        food = make_food(
            food_name="유자차", caffeine_mg=None, sugar_g=None,
            category="음료 및 차류", subcategory="유자차",
        )
        reason, reason_nutrient = make_reason(
            "caution", food, today_intake=make_intake(),
        )
        assert reason_nutrient == "sugar"
        assert "카페인" not in reason


class TestKeywordRuleTierGate:
    """키워드 규칙(음식명 기반)의 티어 게이트.

    이 클래스의 테스트는 recommendation_model.py의 "[키워드 규칙 티어 게이트]" 표시가
    붙은 두 곳에 대응한다. 그 게이트를 되돌리면 여기가 함께 깨진다.
    """

    def test_keyword_rule_does_not_fire_for_free_tier(self):
        # 모카빵은 이름에 "모카"가 있지만 빵 및 과자류는 FREE다.
        # 게이트가 없으면 티어는 "확인된 0", 키워드는 "카페인 있을 수 있음"으로 충돌한다.
        food = make_food(
            food_name="모카빵", caffeine_mg=None,
            category="빵 및 과자류", subcategory="번",
        )
        result = apply_safety_guard(
            "possible", food,
            today_intake=make_intake(),
        )
        assert result == "possible"

    def test_keyword_rule_does_not_fire_for_not_measured_tier(self):
        food = make_food(
            food_name="이디야초콜릿디핑소스", caffeine_mg=None,
            category="장류, 양념류", subcategory="소스/드레싱",
        )
        result = apply_safety_guard(
            "possible", food,
            today_intake=make_intake(),
        )
        assert result == "possible"

    def test_keyword_reason_does_not_fire_for_free_tier(self):
        food = make_food(
            food_name="모카빵", caffeine_mg=None, sugar_g=None,
            category="빵 및 과자류", subcategory="번",
        )
        reason, reason_nutrient = make_reason(
            "caution", food, today_intake=make_intake(),
        )
        assert reason_nutrient != "caffeine"
        assert "음식명에" not in reason

    def test_keyword_reason_still_fires_for_possible_tier(self):
        # POSSIBLE 식품군에서는 이름 단서가 더 구체적이므로 기존 문구를 유지한다.
        food = make_food(
            food_name="아이스 라떼", caffeine_mg=None,
            category="음료 및 차류", subcategory="라떼",
        )
        reason, reason_nutrient = make_reason(
            "caution", food, today_intake=make_intake(),
        )
        assert "음식명에" in reason
        assert reason_nutrient == "caffeine"


# ── 임신 시기 무관성 ───────────────────────────────────────
# 카페인 200mg·나트륨 2300mg은 임신 시기와 무관한 고정 기준이므로, 판정도 시기에
# 따라 달라지지 않는다. 시기별 민감도 규칙(초기 카페인 60%, 후기 나트륨 80%)은
# 그 기준에 근거가 없어 제거했다.

class TestPregnancyStageDoesNotAffectJudgment:
    @pytest.mark.parametrize("func", [
        judge_food_rules,
        apply_safety_guard,
        make_reason,
        recommend_food,
    ])
    def test_judging_functions_take_no_pregnancy_input(self, func):
        # 입력 자체가 없으므로 같은 음식·같은 섭취량이면 임신 초기·중기·후기가
        # 모두 같은 결과다. 규칙이 되살아나면 파라미터가 먼저 되살아난다.
        params = set(inspect.signature(func).parameters)
        assert "trimester" not in params
        assert "pregnancy_week" not in params

    def test_caffeine_above_sixty_percent_is_possible(self):
        # 예전 초기 규칙(카페인 60% 초과 → caution)에 걸리던 값.
        food = make_food(caffeine_mg=DAILY_LIMITS["caffeine"] * 0.61)
        assert recommend_food(food=food, today_intake=make_intake())["status"] == "possible"

    def test_sodium_above_eighty_percent_is_possible(self):
        # 예전 후기 규칙(나트륨 80% 초과 → caution)에 걸리던 값.
        food = make_food(sodium_mg=DAILY_LIMITS["sodium"] * 0.81)
        assert recommend_food(food=food, today_intake=make_intake())["status"] == "possible"


# ── 이미 초과한 영양소는 게이트를 걸지 않는다 ──────────────
# 예전에는 세 영양소를 `> 1.0`으로 OR 판정해서, 어느 하나라도 오늘 한도를 넘긴 순간
# after_<n>_ratio가 모든 음식에 대해 참이 되어 후보 전체가 avoid로 떨어졌다(화면이 빔).
# 이미 먹은 음식은 되돌릴 수 없으므로 그렇게 막아도 사용자가 더 안전해지지 않는다.

class TestExceededNutrientDoesNotGateEveryFood:
    def test_food_is_still_possible_when_an_unrelated_nutrient_is_exceeded(self):
        # 오늘 당류를 이미 넘긴 상태. 당류가 0인 음식까지 avoid가 되면 안 된다.
        intake = make_intake(sugar_g=DAILY_LIMITS["sugar"] * 1.5)
        food = make_food(sugar_g=0.0, sodium_mg=0.0, caffeine_mg=0.0)

        assert judge_food_rules(food, intake) == "possible"

    def test_food_high_in_the_exceeded_nutrient_is_also_still_possible(self):
        # 초과한 영양소는 게이트에서 아예 빠진다 — 그 영양소를 많이 가진 음식이라도
        # 이 규칙만으로는 avoid가 되지 않는다. 경고와 정렬로 드러내는 것이 새 규칙이다.
        intake = make_intake(sodium_mg=DAILY_LIMITS["sodium"] * 1.2)
        food = make_food(sodium_mg=DAILY_LIMITS["sodium"] * 0.9)

        assert judge_food_rules(food, intake) == "possible"

    def test_a_nutrient_with_budget_left_still_gates_normally(self):
        # 초과 규칙이 나머지 영양소의 판정까지 느슨하게 만들면 안 된다.
        intake = make_intake(sugar_g=DAILY_LIMITS["sugar"] * 1.5)
        food = make_food(sodium_mg=DAILY_LIMITS["sodium"] * 1.1)

        assert judge_food_rules(food, intake) == "avoid"

    def test_safety_guard_agrees_with_judge_on_an_exceeded_day(self):
        # 안전장치에도 같은 게이트가 있어서, 여기만 고치지 않으면 버그가 그대로 돌아온다.
        intake = make_intake(sodium_mg=DAILY_LIMITS["sodium"] * 1.2)
        food = make_food(sodium_mg=10.0)

        assert apply_safety_guard("possible", food, today_intake=intake) == "possible"

    def test_exact_limit_leaves_no_budget_and_stops_gating(self):
        # remaining == 0 경계: 정확히 한도만큼 먹은 날은 "남은 허용량 없음"이므로
        # 그 영양소는 게이트에서 빠진다.
        intake = make_intake(sodium_mg=DAILY_LIMITS["sodium"])
        food = make_food(sodium_mg=500.0)

        assert judge_food_rules(food, intake) == "possible"


class TestNutrientBudget:
    def test_remaining_is_clamped_at_zero_and_lists_exceeded(self):
        intake = make_intake(
            sugar_g=DAILY_LIMITS["sugar"] * 2,
            sodium_mg=DAILY_LIMITS["sodium"] * 1.1,
        )
        budget = compute_nutrient_budget(intake)

        assert budget["remaining"]["sugar"] == 0.0
        assert budget["remaining"]["sodium"] == 0.0
        assert budget["remaining"]["caffeine"] == DAILY_LIMITS["caffeine"]
        # EXCEEDED_PRIORITY 순서(카페인·나트륨·당류)를 따른다.
        assert budget["exceeded"] == ["sodium", "sugar"]

    def test_nothing_exceeded_on_an_empty_day(self):
        budget = compute_nutrient_budget(make_intake())

        assert budget["exceeded"] == []
        assert budget["remaining"]["sodium"] == DAILY_LIMITS["sodium"]

    def test_label_joins_exceeded_nutrients_in_korean(self):
        assert format_exceeded_label(["sugar", "sodium"]) == "당류·나트륨 초과"
        assert format_exceeded_label(["sodium"]) == "나트륨 초과"
        assert format_exceeded_label([]) is None


class TestNullIsNotCoercedToZeroInTheGate:
    def test_null_nutrient_does_not_pass_the_gate_as_zero(self):
        # NULL은 "0mg 확정"이 아니다. 게이트 비교를 건너뛰되(0으로 바꿔 통과시키지 않음),
        # 값을 믿을 수 없다는 사실은 caution으로 드러난다.
        food = make_food(sodium_mg=None)
        intake = make_intake()

        assert recommend_food(food=food, today_intake=intake)["status"] == "caution"

    def test_null_nutrient_is_never_excluded_from_candidates(self):
        # 반대 방향: NULL을 큰 값처럼 취급해 avoid로 떨어뜨려서도 안 된다.
        food = make_food(sugar_g=None)

        assert recommend_food(food=food, today_intake=make_intake())["status"] != "avoid"

    def test_null_on_an_exceeded_day_still_does_not_become_avoid(self):
        food = make_food(sodium_mg=None)
        intake = make_intake(sodium_mg=DAILY_LIMITS["sodium"] * 1.5)

        assert recommend_food(food=food, today_intake=intake)["status"] == "caution"


class TestReasonNamesTheNutrientThatActuallyCausedAvoid:
    def test_reason_does_not_blame_an_already_exceeded_nutrient(self):
        # 회귀 가드: 예전 make_reason은 (오늘+음식)/한도 > 1.0을 카페인부터 다시
        # 계산했다. 카페인을 이미 넘긴 날에는 그 식이 음식과 무관하게 참이라,
        # 나트륨 때문에 avoid가 된 음식의 이유로 카페인이 나왔다.
        intake = make_intake(caffeine_mg=DAILY_LIMITS["caffeine"] * 2)
        food = make_food(sodium_mg=DAILY_LIMITS["sodium"] * 1.1)

        status = judge_food_rules(food, intake)
        reason, reason_nutrient = make_reason(status, food, intake)

        assert status == "avoid"
        assert reason_nutrient == "sodium"
        assert "나트륨" in reason
