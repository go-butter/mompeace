"""
backend/recommendation_model.py 의 핵심 안전 판정 로직 테스트.

대상:
- judge_food_rules(): 누적 섭취 비율 기반 1차 판정 (possible/caution/avoid)
- apply_safety_guard(): 임계 초과 등 안전 방향 보정 (절대 하향 금지)

DAILY_LIMITS (1일 허용 기준, 트라이메스터 불변)을 직접 import해서 사용하므로,
이 파일의 수치가 나중에 바뀌어도 테스트는 "70% 이상이면 caution, 100% 이상이면
avoid"라는 *관계*를 검증하지, 하드코딩된 mg/g 값을 검증하지 않는다.
"""
import pytest

from backend.recommendation_model import (
    DAILY_LIMITS,
    STATUS_RANK,
    apply_safety_guard,
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
    @pytest.mark.parametrize("trimester", ["early", "middle", "late"])
    def test_zero_intake_is_possible(self, trimester):
        food = make_food()
        status = judge_food_rules(food, trimester, make_intake())
        assert status == "possible"

    @pytest.mark.parametrize("trimester", ["early", "middle", "late"])
    @pytest.mark.parametrize("nutrient,key", [
        ("caffeine", "caffeine_mg"),
        ("sugar", "sugar_g"),
        ("sodium", "sodium_mg"),
    ])
    def test_just_under_70_percent_is_possible(self, trimester, nutrient, key):
        limit = DAILY_LIMITS[nutrient]
        food = make_food(**{key: limit * 0.69})
        status = judge_food_rules(food, trimester, make_intake())
        assert status == "possible"

    @pytest.mark.parametrize("trimester", ["early", "middle", "late"])
    @pytest.mark.parametrize("nutrient,key", [
        ("caffeine", "caffeine_mg"),
        ("sugar", "sugar_g"),
        ("sodium", "sodium_mg"),
    ])
    def test_just_over_70_percent_is_caution(self, trimester, nutrient, key):
        limit = DAILY_LIMITS[nutrient]
        food = make_food(**{key: limit * 0.71})
        status = judge_food_rules(food, trimester, make_intake())
        assert status == "caution"

    @pytest.mark.parametrize("trimester", ["early", "middle", "late"])
    @pytest.mark.parametrize("nutrient,key", [
        ("caffeine", "caffeine_mg"),
        ("sugar", "sugar_g"),
        ("sodium", "sodium_mg"),
    ])
    def test_just_over_100_percent_is_avoid(self, trimester, nutrient, key):
        limit = DAILY_LIMITS[nutrient]
        food = make_food(**{key: limit * 1.01})
        status = judge_food_rules(food, trimester, make_intake())
        assert status == "avoid"

    def test_cumulative_intake_plus_food_can_tip_over(self):
        # 오늘 이미 60% 섭취한 상태에서 50%를 더 먹으면 110% → avoid
        limit = DAILY_LIMITS["sugar"]
        food = make_food(sugar_g=limit * 0.5)
        intake = make_intake(sugar_g=limit * 0.6)
        status = judge_food_rules(food, "middle", intake)
        assert status == "avoid"

    def test_caffeine_missing_with_keyword_is_caution(self):
        # 카페인 정보가 없는 음식인데 이름에 카페인 키워드가 있으면 caution
        food = make_food(food_name="아이스 라떼", caffeine_mg=None, data_source="dish_db_download")
        status = judge_food_rules(food, "middle", make_intake())
        assert status == "caution"

    def test_caffeine_missing_without_keyword_is_possible(self):
        food = make_food(food_name="흰쌀밥", caffeine_mg=None, data_source="dish_db_download")
        status = judge_food_rules(food, "middle", make_intake())
        assert status == "possible"


# ── apply_safety_guard: 안전장치 ──────────────────────────

class TestApplySafetyGuard:
    @pytest.mark.parametrize("trimester", ["early", "middle", "late"])
    @pytest.mark.parametrize("key,limit_key", [
        ("caffeine_mg", "caffeine"),
        ("sugar_g", "sugar"),
        ("sodium_mg", "sodium"),
    ])
    def test_absolute_excess_forces_avoid(self, trimester, key, limit_key):
        limit = DAILY_LIMITS[limit_key]
        food = make_food(**{key: limit * 1.5})
        result = apply_safety_guard(
            "possible", food,
            today_intake=make_intake(), trimester=trimester,
        )
        assert result == "avoid"

    def test_never_downgrades_below_input_status(self):
        # 안전장치는 always upgrade-only: avoid로 들어온 건 절대 내려가지 않는다
        food = make_food()  # 모든 영양소 0, 안전한 음식
        result = apply_safety_guard(
            "avoid", food,
            today_intake=make_intake(), trimester="middle",
        )
        assert result == "avoid"

    def test_never_downgrades_caution_to_possible(self):
        food = make_food()
        result = apply_safety_guard(
            "caution", food,
            today_intake=make_intake(), trimester="middle",
        )
        assert STATUS_RANK[result] >= STATUS_RANK["caution"]

    def test_early_trimester_caffeine_60_percent_triggers_caution(self):
        limit = DAILY_LIMITS["caffeine"]
        food = make_food(caffeine_mg=limit * 0.61)
        result = apply_safety_guard(
            "possible", food,
            today_intake=make_intake(), trimester="early",
        )
        assert result == "caution"

    def test_early_trimester_caffeine_under_60_percent_stays_possible(self):
        limit = DAILY_LIMITS["caffeine"]
        food = make_food(caffeine_mg=limit * 0.5)
        result = apply_safety_guard(
            "possible", food,
            today_intake=make_intake(), trimester="early",
        )
        assert result == "possible"

    def test_middle_trimester_does_not_apply_early_caffeine_rule(self):
        # early 전용 60% 카페인 규칙이 다른 트라이메스터에 새지 않는지 확인
        limit = DAILY_LIMITS["caffeine"]
        food = make_food(caffeine_mg=limit * 0.61)
        result = apply_safety_guard(
            "possible", food,
            today_intake=make_intake(), trimester="middle",
        )
        assert result == "possible"

    def test_late_trimester_sodium_80_percent_triggers_caution(self):
        limit = DAILY_LIMITS["sodium"]
        food = make_food(sodium_mg=limit * 0.81)
        result = apply_safety_guard(
            "possible", food,
            today_intake=make_intake(), trimester="late",
        )
        assert result == "caution"

    def test_missing_sugar_or_sodium_forces_at_least_caution(self):
        food = make_food(sugar_g=None)
        result = apply_safety_guard(
            "possible", food,
            today_intake=make_intake(), trimester="middle",
        )
        assert result == "caution"

    def test_missing_sodium_forces_at_least_caution(self):
        food = make_food(sodium_mg=None)
        result = apply_safety_guard(
            "possible", food,
            today_intake=make_intake(), trimester="middle",
        )
        assert result == "caution"

    @pytest.mark.parametrize("source", ["food_nutrition_api", "processed_food_db_download"])
    def test_caffeine_unsupported_sources_always_treated_as_missing(self, source):
        # food_nutrition_api / processed_food_db_download 는 caffeine_mg 값이
        # 있어도(예: 0으로 잘못 채워졌어도) 항상 missing 으로 처리되어야 한다.
        food = make_food(food_name="콜드브루", caffeine_mg=0, data_source=source)
        result = apply_safety_guard(
            "possible", food,
            today_intake=make_intake(), trimester="middle",
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
            today_intake=make_intake(), trimester="middle",
        )
        # avoid 가 아니라 caution 이어야 함 (missing + 키워드 규칙만 적용)
        assert result == "caution"

    def test_sensitivity_adjustment_loosens_limit(self):
        # user_adj가 양수(+)면 기준이 완화되어 동일 섭취량이 avoid가 안 될 수 있다
        limit = DAILY_LIMITS["sodium"]
        food = make_food(sodium_mg=limit * 1.05)  # 조정 없으면 avoid
        result_no_adj = apply_safety_guard(
            "possible", food,
            today_intake=make_intake(), trimester="middle",
        )
        result_with_adj = apply_safety_guard(
            "possible", food,
            today_intake=make_intake(), trimester="middle",
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
            today_intake=make_intake(), trimester="middle",
        )
        assert result == "caution"


# ── make_reason: 한국어 이유 + reason_nutrient 태그 ────────

class TestMakeReason:
    def test_avoid_picks_caffeine_when_caffeine_exceeds_limit(self):
        limit = DAILY_LIMITS["caffeine"]
        food = make_food(caffeine_mg=limit * 1.1)
        reason, reason_nutrient = make_reason(
            "avoid", food, today_intake=make_intake(),
            trimester="middle",
        )
        assert "카페인" in reason
        assert reason_nutrient == "caffeine"

    def test_avoid_picks_sugar_when_sugar_exceeds_limit(self):
        limit = DAILY_LIMITS["sugar"]
        food = make_food(sugar_g=limit * 1.1)
        reason, reason_nutrient = make_reason(
            "avoid", food, today_intake=make_intake(),
            trimester="middle",
        )
        assert "당류" in reason
        assert reason_nutrient == "sugar"

    def test_avoid_picks_sodium_when_sodium_exceeds_limit(self):
        limit = DAILY_LIMITS["sodium"]
        food = make_food(sodium_mg=limit * 1.1)
        reason, reason_nutrient = make_reason(
            "avoid", food, today_intake=make_intake(),
            trimester="middle",
        )
        assert "나트륨" in reason
        assert reason_nutrient == "sodium"

    def test_avoid_falls_back_to_generic_message_when_no_single_nutrient_exceeds(self):
        # avoid로 들어왔지만(예: 상위 로직에서 강제 승급) 개별 영양소 비율이
        # 100%를 넘지 않는 경우 일반 문구 + reason_nutrient=None 이어야 한다
        food = make_food()
        reason, reason_nutrient = make_reason(
            "avoid", food, today_intake=make_intake(),
            trimester="middle",
        )
        assert reason_nutrient is None
        assert "비추천" in reason

    def test_caution_picks_caffeine_when_caffeine_ratio_exceeds_0_7(self):
        limit = DAILY_LIMITS["caffeine"]
        food = make_food(caffeine_mg=limit * 0.75)
        reason, reason_nutrient = make_reason(
            "caution", food, today_intake=make_intake(),
            trimester="middle",
        )
        assert "카페인" in reason
        assert reason_nutrient == "caffeine"

    def test_caution_picks_sugar_when_sugar_ratio_exceeds_0_7(self):
        limit = DAILY_LIMITS["sugar"]
        food = make_food(sugar_g=limit * 0.75)
        reason, reason_nutrient = make_reason(
            "caution", food, today_intake=make_intake(),
            trimester="middle",
        )
        assert "당류" in reason
        assert reason_nutrient == "sugar"

    def test_caution_picks_sodium_when_sodium_ratio_exceeds_0_7(self):
        limit = DAILY_LIMITS["sodium"]
        food = make_food(sodium_mg=limit * 0.75)
        reason, reason_nutrient = make_reason(
            "caution", food, today_intake=make_intake(),
            trimester="middle",
        )
        assert "나트륨" in reason
        assert reason_nutrient == "sodium"

    def test_caution_caffeine_wins_over_sugar_when_both_ratios_exceed_0_7(self):
        caffeine_limit = DAILY_LIMITS["caffeine"]
        sugar_limit = DAILY_LIMITS["sugar"]
        food = make_food(caffeine_mg=caffeine_limit * 0.75, sugar_g=sugar_limit * 0.75)
        reason, reason_nutrient = make_reason(
            "caution", food, today_intake=make_intake(),
            trimester="middle",
        )
        assert reason_nutrient == "caffeine"

    def test_caution_missing_sugar_or_sodium_returns_missing_info_message(self):
        food = make_food(sugar_g=None)
        reason, reason_nutrient = make_reason(
            "caution", food, today_intake=make_intake(),
            trimester="middle",
        )
        assert "정보가 없어" in reason
        assert reason_nutrient is None

    def test_possible_with_real_caffeine_value_mentions_caffeine(self):
        # caffeine_mg가 missing이 아닌 실제 값으로 존재하면 possible이어도
        # 카페인 안내 문구를 우선 반환해야 한다
        food = make_food(caffeine_mg=30.0, data_source="dish_db_download")
        reason, reason_nutrient = make_reason(
            "possible", food, today_intake=make_intake(),
            trimester="middle",
        )
        assert "카페인" in reason
        assert reason_nutrient == "caffeine"

    def test_possible_without_caffeine_returns_generic_low_burden_message(self):
        food = make_food()  # caffeine_mg=0.0 (실제 값, missing 아님)
        reason, reason_nutrient = make_reason(
            "possible", food, today_intake=make_intake(),
            trimester="middle",
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
            today_intake=make_intake(), trimester="middle",
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
            today_intake=make_intake(), trimester="middle",
        )
        assert result == "possible"

    def test_bakery_category_is_free_regardless_of_subcategory(self):
        food = make_food(
            food_name="초코 케이크", caffeine_mg=None,
            category="빵 및 과자류", subcategory="케이크",
        )
        result = apply_safety_guard(
            "possible", food,
            today_intake=make_intake(), trimester="middle",
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
            today_intake=make_intake(), trimester="middle",
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
            today_intake=make_intake(), trimester="middle",
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
            today_intake=make_intake(), trimester="middle",
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
            today_intake=make_intake(), trimester="middle",
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
            today_intake=make_intake(), trimester="middle",
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
            today_intake=make_intake(), trimester="middle",
        )
        assert result == "avoid"

    def test_judge_food_rules_is_not_affected_by_tier(self):
        # 티어 검사는 apply_safety_guard/make_reason에만 있다 (당류·나트륨 missing
        # 규칙과 같은 위치). judge_food_rules는 건드리지 않았다.
        food = make_food(
            food_name="이름에 단서 없음", caffeine_mg=None,
            category="음료 및 차류", subcategory="스무디",
        )
        assert judge_food_rules(food, "middle", make_intake()) == "possible"

    def test_recommend_food_end_to_end_flags_missing_caffeine(self):
        result = recommend_food(
            food=make_food(
                food_name="딸기 스무디", caffeine_mg=None,
                category="음료 및 차류", subcategory="스무디",
            ),
            pregnancy_week=20,
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
            trimester="middle",
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
            trimester="middle",
        )
        assert reason_nutrient == "caffeine"
        assert "일부 영양성분" not in reason

    def test_free_tier_missing_caffeine_falls_through_to_generic_message(self):
        # FREE 식품군은 카페인을 지목하지 않는다. 당류가 없으면 기존 문구 그대로.
        food = make_food(
            food_name="유자차", caffeine_mg=None, sugar_g=None,
            category="음료 및 차류", subcategory="유자차",
        )
        reason, reason_nutrient = make_reason(
            "caution", food, today_intake=make_intake(),
            trimester="middle",
        )
        assert reason_nutrient is None
        assert "일부 영양성분" in reason


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
            today_intake=make_intake(), trimester="middle",
        )
        assert result == "possible"

    def test_keyword_rule_does_not_fire_for_not_measured_tier(self):
        food = make_food(
            food_name="이디야초콜릿디핑소스", caffeine_mg=None,
            category="장류, 양념류", subcategory="소스/드레싱",
        )
        result = apply_safety_guard(
            "possible", food,
            today_intake=make_intake(), trimester="middle",
        )
        assert result == "possible"

    def test_keyword_reason_does_not_fire_for_free_tier(self):
        food = make_food(
            food_name="모카빵", caffeine_mg=None, sugar_g=None,
            category="빵 및 과자류", subcategory="번",
        )
        reason, reason_nutrient = make_reason(
            "caution", food, today_intake=make_intake(),
            trimester="middle",
        )
        assert reason_nutrient is None
        assert "음식명에" not in reason

    def test_keyword_reason_still_fires_for_possible_tier(self):
        # POSSIBLE 식품군에서는 이름 단서가 더 구체적이므로 기존 문구를 유지한다.
        food = make_food(
            food_name="아이스 라떼", caffeine_mg=None,
            category="음료 및 차류", subcategory="라떼",
        )
        reason, reason_nutrient = make_reason(
            "caution", food, today_intake=make_intake(),
            trimester="middle",
        )
        assert "음식명에" in reason
        assert reason_nutrient == "caffeine"
