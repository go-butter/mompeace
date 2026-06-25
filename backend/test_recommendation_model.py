"""
backend/recommendation_model.py 의 핵심 안전 판정 로직 테스트.

대상:
- judge_food_rules(): 누적 섭취 비율 기반 1차 판정 (possible/caution/avoid)
- apply_safety_guard(): 알레르기/임계 초과 등 안전 방향 보정 (절대 하향 금지)

DAILY_LIMITS (트라이메스터별 1일 허용 기준)을 직접 import해서 사용하므로,
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
)


def make_food(**overrides):
    """안전한 기본값을 가진 food dict. 필요한 필드만 덮어써서 사용."""
    defaults = {
        "food_name": "테스트 음식",
        "caffeine_mg": 0.0,
        "sugar_g": 0.0,
        "sodium_mg": 0.0,
        "data_source": "dish_db_download",
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
        status = judge_food_rules(food, trimester, make_intake(), allergy_match=0)
        assert status == "possible"

    @pytest.mark.parametrize("trimester", ["early", "middle", "late"])
    @pytest.mark.parametrize("nutrient,key", [
        ("caffeine", "caffeine_mg"),
        ("sugar", "sugar_g"),
        ("sodium", "sodium_mg"),
    ])
    def test_just_under_70_percent_is_possible(self, trimester, nutrient, key):
        limit = DAILY_LIMITS[trimester][nutrient]
        food = make_food(**{key: limit * 0.69})
        status = judge_food_rules(food, trimester, make_intake(), allergy_match=0)
        assert status == "possible"

    @pytest.mark.parametrize("trimester", ["early", "middle", "late"])
    @pytest.mark.parametrize("nutrient,key", [
        ("caffeine", "caffeine_mg"),
        ("sugar", "sugar_g"),
        ("sodium", "sodium_mg"),
    ])
    def test_just_over_70_percent_is_caution(self, trimester, nutrient, key):
        limit = DAILY_LIMITS[trimester][nutrient]
        food = make_food(**{key: limit * 0.71})
        status = judge_food_rules(food, trimester, make_intake(), allergy_match=0)
        assert status == "caution"

    @pytest.mark.parametrize("trimester", ["early", "middle", "late"])
    @pytest.mark.parametrize("nutrient,key", [
        ("caffeine", "caffeine_mg"),
        ("sugar", "sugar_g"),
        ("sodium", "sodium_mg"),
    ])
    def test_just_over_100_percent_is_avoid(self, trimester, nutrient, key):
        limit = DAILY_LIMITS[trimester][nutrient]
        food = make_food(**{key: limit * 1.01})
        status = judge_food_rules(food, trimester, make_intake(), allergy_match=0)
        assert status == "avoid"

    def test_cumulative_intake_plus_food_can_tip_over(self):
        # 오늘 이미 60% 섭취한 상태에서 50%를 더 먹으면 110% → avoid
        limit = DAILY_LIMITS["middle"]["sugar"]
        food = make_food(sugar_g=limit * 0.5)
        intake = make_intake(sugar_g=limit * 0.6)
        status = judge_food_rules(food, "middle", intake, allergy_match=0)
        assert status == "avoid"

    def test_caffeine_missing_with_keyword_is_caution(self):
        # 카페인 정보가 없는 음식인데 이름에 카페인 키워드가 있으면 caution
        food = make_food(food_name="아이스 라떼", caffeine_mg=None, data_source="dish_db_download")
        status = judge_food_rules(food, "middle", make_intake(), allergy_match=0)
        assert status == "caution"

    def test_caffeine_missing_without_keyword_is_possible(self):
        food = make_food(food_name="흰쌀밥", caffeine_mg=None, data_source="dish_db_download")
        status = judge_food_rules(food, "middle", make_intake(), allergy_match=0)
        assert status == "possible"


# ── apply_safety_guard: 안전장치 ──────────────────────────

class TestApplySafetyGuard:
    def test_allergy_match_always_avoid_regardless_of_input_status(self):
        food = make_food()
        for incoming_status in ("possible", "caution", "avoid"):
            result = apply_safety_guard(
                incoming_status, food, allergy_match=1,
                today_intake=make_intake(), trimester="middle",
            )
            assert result == "avoid"

    def test_allergy_overrides_even_when_nutrients_are_all_zero(self):
        # 알레르기는 영양소 수치와 무관하게 무조건 최우선
        food = make_food(caffeine_mg=0, sugar_g=0, sodium_mg=0)
        result = apply_safety_guard(
            "possible", food, allergy_match=1,
            today_intake=make_intake(), trimester="early",
        )
        assert result == "avoid"

    @pytest.mark.parametrize("trimester", ["early", "middle", "late"])
    @pytest.mark.parametrize("key,limit_key", [
        ("caffeine_mg", "caffeine"),
        ("sugar_g", "sugar"),
        ("sodium_mg", "sodium"),
    ])
    def test_absolute_excess_forces_avoid(self, trimester, key, limit_key):
        limit = DAILY_LIMITS[trimester][limit_key]
        food = make_food(**{key: limit * 1.5})
        result = apply_safety_guard(
            "possible", food, allergy_match=0,
            today_intake=make_intake(), trimester=trimester,
        )
        assert result == "avoid"

    def test_never_downgrades_below_input_status(self):
        # 안전장치는 always upgrade-only: avoid로 들어온 건 절대 내려가지 않는다
        food = make_food()  # 모든 영양소 0, 안전한 음식
        result = apply_safety_guard(
            "avoid", food, allergy_match=0,
            today_intake=make_intake(), trimester="middle",
        )
        assert result == "avoid"

    def test_never_downgrades_caution_to_possible(self):
        food = make_food()
        result = apply_safety_guard(
            "caution", food, allergy_match=0,
            today_intake=make_intake(), trimester="middle",
        )
        assert STATUS_RANK[result] >= STATUS_RANK["caution"]

    def test_early_trimester_caffeine_60_percent_triggers_caution(self):
        limit = DAILY_LIMITS["early"]["caffeine"]
        food = make_food(caffeine_mg=limit * 0.61)
        result = apply_safety_guard(
            "possible", food, allergy_match=0,
            today_intake=make_intake(), trimester="early",
        )
        assert result == "caution"

    def test_early_trimester_caffeine_under_60_percent_stays_possible(self):
        limit = DAILY_LIMITS["early"]["caffeine"]
        food = make_food(caffeine_mg=limit * 0.5)
        result = apply_safety_guard(
            "possible", food, allergy_match=0,
            today_intake=make_intake(), trimester="early",
        )
        assert result == "possible"

    def test_middle_trimester_does_not_apply_early_caffeine_rule(self):
        # early 전용 60% 카페인 규칙이 다른 트라이메스터에 새지 않는지 확인
        limit = DAILY_LIMITS["middle"]["caffeine"]
        food = make_food(caffeine_mg=limit * 0.61)
        result = apply_safety_guard(
            "possible", food, allergy_match=0,
            today_intake=make_intake(), trimester="middle",
        )
        assert result == "possible"

    def test_late_trimester_sodium_80_percent_triggers_caution(self):
        limit = DAILY_LIMITS["late"]["sodium"]
        food = make_food(sodium_mg=limit * 0.81)
        result = apply_safety_guard(
            "possible", food, allergy_match=0,
            today_intake=make_intake(), trimester="late",
        )
        assert result == "caution"

    def test_missing_sugar_or_sodium_forces_at_least_caution(self):
        food = make_food(sugar_g=None)
        result = apply_safety_guard(
            "possible", food, allergy_match=0,
            today_intake=make_intake(), trimester="middle",
        )
        assert result == "caution"

    def test_missing_sodium_forces_at_least_caution(self):
        food = make_food(sodium_mg=None)
        result = apply_safety_guard(
            "possible", food, allergy_match=0,
            today_intake=make_intake(), trimester="middle",
        )
        assert result == "caution"

    @pytest.mark.parametrize("source", ["food_nutrition_api", "processed_food_db_download"])
    def test_caffeine_unsupported_sources_always_treated_as_missing(self, source):
        # food_nutrition_api / processed_food_db_download 는 caffeine_mg 값이
        # 있어도(예: 0으로 잘못 채워졌어도) 항상 missing 으로 처리되어야 한다.
        food = make_food(food_name="콜드브루", caffeine_mg=0, data_source=source)
        result = apply_safety_guard(
            "possible", food, allergy_match=0,
            today_intake=make_intake(), trimester="middle",
        )
        # 카페인 키워드("콜드브루")가 있고 missing 처리되므로 최소 caution
        assert result == "caution"

    def test_caffeine_missing_real_value_not_counted_toward_ratio(self):
        # data_source가 missing-소스인 경우, 실제 caffeine_mg 값이 커도
        # 절대 초과(avoid) 트리거에 반영되면 안 된다 (missing 처리 정의상).
        limit = DAILY_LIMITS["middle"]["caffeine"]
        food = make_food(
            food_name="커피",  # CAFFEINE_KEYWORDS에 포함된 단어
            caffeine_mg=limit * 5,  # 명백히 과한 값이지만 missing 소스
            data_source="food_nutrition_api",
        )
        result = apply_safety_guard(
            "possible", food, allergy_match=0,
            today_intake=make_intake(), trimester="middle",
        )
        # avoid 가 아니라 caution 이어야 함 (missing + 키워드 규칙만 적용)
        assert result == "caution"

    def test_sensitivity_adjustment_loosens_limit(self):
        # user_adj가 양수(+)면 기준이 완화되어 동일 섭취량이 avoid가 안 될 수 있다
        limit = DAILY_LIMITS["middle"]["sodium"]
        food = make_food(sodium_mg=limit * 1.05)  # 조정 없으면 avoid
        result_no_adj = apply_safety_guard(
            "possible", food, allergy_match=0,
            today_intake=make_intake(), trimester="middle",
        )
        result_with_adj = apply_safety_guard(
            "possible", food, allergy_match=0,
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
            "possible", food, allergy_match=0,
            today_intake=make_intake(), trimester="middle",
        )
        assert result == "caution"

    def test_sensitivity_adjustment_does_not_bypass_allergy(self):
        # 민감도 조정이 알레르기 안전장치를 무력화시키면 안 된다
        food = make_food()
        result = apply_safety_guard(
            "possible", food, allergy_match=1,
            today_intake=make_intake(), trimester="middle",
            user_adj={"caffeine": 0.15, "sugar": 0.15, "sodium": 0.15},
        )
        assert result == "avoid"


# ── make_reason: 한국어 이유 + reason_nutrient 태그 ────────

class TestMakeReason:
    def test_allergy_returns_allergy_message_and_tag_regardless_of_status(self):
        # 알레르기는 status 값과 무관하게 항상 같은 메시지/태그를 반환해야 한다
        food = make_food()
        for status in ("possible", "caution", "avoid"):
            reason, reason_nutrient = make_reason(
                status, food, today_intake=make_intake(),
                trimester="middle", allergy_match=1,
            )
            assert "알레르기" in reason
            assert reason_nutrient == "allergy"

    def test_avoid_picks_caffeine_when_caffeine_exceeds_limit(self):
        limit = DAILY_LIMITS["middle"]["caffeine"]
        food = make_food(caffeine_mg=limit * 1.1)
        reason, reason_nutrient = make_reason(
            "avoid", food, today_intake=make_intake(),
            trimester="middle", allergy_match=0,
        )
        assert "카페인" in reason
        assert reason_nutrient == "caffeine"

    def test_avoid_picks_sugar_when_sugar_exceeds_limit(self):
        limit = DAILY_LIMITS["middle"]["sugar"]
        food = make_food(sugar_g=limit * 1.1)
        reason, reason_nutrient = make_reason(
            "avoid", food, today_intake=make_intake(),
            trimester="middle", allergy_match=0,
        )
        assert "당류" in reason
        assert reason_nutrient == "sugar"

    def test_avoid_picks_sodium_when_sodium_exceeds_limit(self):
        limit = DAILY_LIMITS["middle"]["sodium"]
        food = make_food(sodium_mg=limit * 1.1)
        reason, reason_nutrient = make_reason(
            "avoid", food, today_intake=make_intake(),
            trimester="middle", allergy_match=0,
        )
        assert "나트륨" in reason
        assert reason_nutrient == "sodium"

    def test_avoid_falls_back_to_generic_message_when_no_single_nutrient_exceeds(self):
        # avoid로 들어왔지만(예: 상위 로직에서 강제 승급) 개별 영양소 비율이
        # 100%를 넘지 않는 경우 일반 문구 + reason_nutrient=None 이어야 한다
        food = make_food()
        reason, reason_nutrient = make_reason(
            "avoid", food, today_intake=make_intake(),
            trimester="middle", allergy_match=0,
        )
        assert reason_nutrient is None
        assert "비추천" in reason

    def test_caution_missing_sugar_or_sodium_returns_missing_info_message(self):
        food = make_food(sugar_g=None)
        reason, reason_nutrient = make_reason(
            "caution", food, today_intake=make_intake(),
            trimester="middle", allergy_match=0,
        )
        assert "정보가 없어" in reason
        assert reason_nutrient is None

    def test_possible_with_real_caffeine_value_mentions_caffeine(self):
        # caffeine_mg가 missing이 아닌 실제 값으로 존재하면 possible이어도
        # 카페인 안내 문구를 우선 반환해야 한다
        food = make_food(caffeine_mg=30.0, data_source="dish_db_download")
        reason, reason_nutrient = make_reason(
            "possible", food, today_intake=make_intake(),
            trimester="middle", allergy_match=0,
        )
        assert "카페인" in reason
        assert reason_nutrient == "caffeine"

    def test_possible_without_caffeine_returns_generic_low_burden_message(self):
        food = make_food()  # caffeine_mg=0.0 (실제 값, missing 아님)
        reason, reason_nutrient = make_reason(
            "possible", food, today_intake=make_intake(),
            trimester="middle", allergy_match=0,
        )
        assert reason_nutrient is None
        assert "부담이 낮은" in reason
