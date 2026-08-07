"""
backend/intake_totals.py 의 get_trimester_limits() / resolve_user_nutrition_context() /
일일 투영 판정(fetch_daily_nutrient_totals, build_daily_projected_statuses,
select_headline_nutrient) 테스트.

핵심 검증 대상:
- age_bracket("19-29"/"30-49")에 따라 energy_kcal/protein_g baseline이 달라진다
- age_bracket 미지정 시 기본값("19-29")과 동일한 결과를 낸다
- resolve_user_nutrition_context()는 pregnancy_week/age_bracket 미설정 사용자를
  각각 20주/"19-29"로 대체한다
- 일일 투영: "오늘 누적 + 확인 중인 품목"으로 판정하므로, 같은 품목이라도 그날
  이미 먹은 양에 따라 판정이 달라진다 (양방향)
- floor형/band형 하한 미달은 tier="neutral" — 경고가 아니고 헤드라인 후보도 아니다
- 헤드라인 선택은 완전히 결정론적이다 (무작위 없음)
"""
from datetime import date

import pytest

from backend.intake_totals import (
    _headline_ratio,
    build_daily_projected_statuses,
    fetch_daily_nutrient_totals,
    get_trimester_limits,
    resolve_user_nutrition_context,
    select_headline_nutrient,
    tier_of_status,
)
from backend.nutrition_constants import DEFAULT_AGE_BRACKET

from .conftest import make_food_log, make_user

# 임신 20주(middle) + 기본 나이대 기준 limits:
# caffeine 200mg / sugar 50g / sodium 1500mg / carbohydrate 175g /
# protein 55+15=70g / energy 2000+340=2340kcal / fat 15~30% / iron 24~45mg
_, LIMITS = get_trimester_limits(20, DEFAULT_AGE_BRACKET)

_EMPTY_DAY = {
    "total_caffeine": 0, "known_caffeine_count": 0,
    "total_sugar": 0, "known_sugar_count": 0,
    "total_sodium": 0, "known_sodium_count": 0,
    "total_calories": 0, "known_energy_count": 0,
    "total_carbohydrate": 0, "known_carbohydrate_count": 0,
    "total_protein": 0, "known_protein_count": 0,
    "total_fat": 0, "known_fat_count": 0,
    "total_iron": 0, "known_iron_count": 0,
    "logged_count": 0,
}


def _day(**overrides) -> dict:
    """_EMPTY_DAY를 베이스로 한 하루치 누적값. total만 넘기면 known_count/logged_count를
    자동으로 1 이상으로 맞춰준다 — known_count가 0이면 무조건 unknown이 되어버려서
    대부분의 테스트가 의도한 경로를 타지 못한다."""
    totals = dict(_EMPTY_DAY)
    totals.update(overrides)
    if overrides:
        totals.setdefault("logged_count", 1)
        totals["logged_count"] = max(totals["logged_count"], 1)
    return totals


def _by_key(items: list[dict]) -> dict:
    return {item["key"]: item for item in items}


def _status_item(key, tier, value=None, limit=None, label="라벨") -> dict:
    """select_headline_nutrient() 단위 테스트용 최소 상태 항목."""
    return {"key": key, "label": label, "tier": tier, "value": value, "limit": limit}


class TestGetTrimesterLimitsAgeBracket:
    def test_defaults_to_19_29_baseline_when_age_bracket_omitted(self):
        _, limits = get_trimester_limits(8)  # early: +0/+0

        assert limits["energy_kcal"] == 2000.0
        assert limits["protein_g"] == 55.0

    def test_19_29_bracket_matches_default(self):
        _, limits = get_trimester_limits(8, "19-29")

        assert limits["energy_kcal"] == 2000.0
        assert limits["protein_g"] == 55.0

    def test_30_49_bracket_uses_lower_baseline(self):
        _, limits = get_trimester_limits(8, "30-49")

        assert limits["energy_kcal"] == 1900.0
        assert limits["protein_g"] == 50.0

    def test_30_49_bracket_still_applies_trimester_additions(self):
        # late(28주 이상): energy +450, protein +30
        _, limits = get_trimester_limits(30, "30-49")

        assert limits["energy_kcal"] == 1900.0 + 450.0
        assert limits["protein_g"] == 50.0 + 30.0


class TestResolveUserNutritionContext:
    def test_falls_back_to_week_20_and_bracket_19_29_when_unset(self):
        week, age_bracket = resolve_user_nutrition_context({})

        assert week == 20
        assert age_bracket == "19-29"

    def test_reads_age_bracket_from_user_row(self):
        week, age_bracket = resolve_user_nutrition_context({"age_bracket": "30-49"})

        assert age_bracket == "30-49"

    def test_reads_pregnancy_week_from_user_row(self):
        week, _ = resolve_user_nutrition_context({"pregnancy_week": 25})

        assert week == 25


# ── fetch_daily_nutrient_totals ──────────────────────────────────

class TestFetchDailyNutrientTotals:
    def test_empty_day_returns_zero_totals_and_zero_counts(self, db):
        user_id = make_user(db)

        totals = fetch_daily_nutrient_totals(user_id, date.today().isoformat(), db)

        assert totals["total_sodium"] == 0
        assert totals["known_sodium_count"] == 0
        assert totals["logged_count"] == 0

    def test_sums_values_and_counts_known_across_rows(self, db):
        user_id = make_user(db)
        make_food_log(db, user_id, sodium_mg=400, caffeine_mg=80)
        make_food_log(db, user_id, sodium_mg=1000, caffeine_mg=70)

        totals = fetch_daily_nutrient_totals(user_id, date.today().isoformat(), db)

        assert totals["total_sodium"] == 1400
        assert totals["known_sodium_count"] == 2
        assert totals["total_caffeine"] == 150
        assert totals["logged_count"] == 2

    def test_null_values_are_summed_as_zero_but_not_counted_as_known(self, db):
        # 정보 없음 ≠ 0: SUM은 COALESCE로 0이 되지만 known_count는 올라가지 않아야
        # 상위에서 unknown으로 판정할 수 있다.
        user_id = make_user(db)
        make_food_log(db, user_id, sodium_mg=None, sugar_g=10)

        totals = fetch_daily_nutrient_totals(user_id, date.today().isoformat(), db)

        assert totals["total_sodium"] == 0
        assert totals["known_sodium_count"] == 0
        assert totals["known_sugar_count"] == 1
        assert totals["logged_count"] == 1

    def test_other_users_rows_are_excluded(self, db):
        user_id = make_user(db)
        other_id = make_user(db, nickname="다른유저")  # users.nickname은 UNIQUE
        make_food_log(db, other_id, sodium_mg=900)

        totals = fetch_daily_nutrient_totals(user_id, date.today().isoformat(), db)

        assert totals["total_sodium"] == 0

    def test_other_dates_are_excluded(self, db):
        user_id = make_user(db)
        make_food_log(db, user_id, sodium_mg=900, eaten_at="2020-01-01 09:00:00")

        totals = fetch_daily_nutrient_totals(user_id, date.today().isoformat(), db)

        assert totals["total_sodium"] == 0
        assert totals["logged_count"] == 0


# ── build_daily_projected_statuses: 상한형(cap-type) ──────────────

class TestProjectedCapTypeStatuses:
    def test_always_returns_all_eight_nutrients(self):
        items = build_daily_projected_statuses({}, _EMPTY_DAY, LIMITS)

        assert len(items) == 8
        assert set(_by_key(items)) == {
            "carbohydrate", "sugar", "energy", "fat", "iron", "protein", "sodium", "caffeine",
        }

    def test_item_alone_would_be_safe_but_days_total_pushes_it_to_avoid(self):
        # 브리프의 사례: 이미 1400mg 먹은 날에 1710mg 나트륨 품목 -> 3110mg.
        # 품목만 보면 1710/1500 = 114%지만, 실제로는 207%다.
        items = build_daily_projected_statuses(
            {"sodium": 1710.0}, _day(total_sodium=1400, known_sodium_count=1), LIMITS
        )

        sodium = _by_key(items)["sodium"]
        assert sodium["value"] == 3110
        assert sodium["status"] == "avoid"
        assert sodium["tier"] == "avoid"

    def test_small_item_on_an_already_over_limit_day_is_still_avoid(self):
        # 반대 방향: 800mg짜리 품목은 단독으로는 안전(53%)이지만 이미 한도를 넘긴
        # 날에는 안전하다고 말하면 안 된다.
        items = build_daily_projected_statuses(
            {"sodium": 800.0}, _day(total_sodium=1600, known_sodium_count=1), LIMITS
        )

        assert _by_key(items)["sodium"]["status"] == "avoid"

    def test_same_item_on_an_empty_day_is_safe(self):
        items = build_daily_projected_statuses({"sodium": 800.0}, _EMPTY_DAY, LIMITS)

        sodium = _by_key(items)["sodium"]
        assert sodium["value"] == 800
        assert sodium["status"] == "safe"
        assert sodium["tier"] == "safe"

    def test_percent_is_relative_to_the_daily_limit(self):
        items = build_daily_projected_statuses({"sodium": 750.0}, _EMPTY_DAY, LIMITS)

        assert _by_key(items)["sodium"]["percent"] == 50.0
        assert _by_key(items)["sodium"]["limit"] == 1500.0

    def test_missing_value_on_an_empty_day_is_unknown_with_null_value(self):
        # 정보 없음 ≠ 0 — 값이 0으로 노출되면 "0mg 확정"과 구분할 수 없다.
        items = build_daily_projected_statuses({"sodium": None}, _EMPTY_DAY, LIMITS)

        sodium = _by_key(items)["sodium"]
        assert sodium["status"] == "unknown"
        assert sodium["tier"] == "unknown"
        assert sodium["value"] is None
        assert sodium["status_label"] == "정보없음"

    def test_all_unknown_when_nothing_logged_and_nothing_pending(self):
        items = build_daily_projected_statuses({}, _EMPTY_DAY, LIMITS)

        assert all(item["tier"] == "unknown" for item in items)
        assert all(item["value"] is None for item in items)


# ── build_daily_projected_statuses: 카페인(여덟 번째 영양소) ───────

class TestProjectedCaffeine:
    def test_caffeine_is_included_even_though_ocr_can_never_extract_it(self):
        items = build_daily_projected_statuses({}, _EMPTY_DAY, LIMITS)

        assert "caffeine" in _by_key(items)

    def test_caffeine_from_todays_logs_shows_accumulated_state_without_any_typed_value(self):
        # 사용자가 아직 아무것도 입력하지 않았어도(pending=None), 오늘 이미 마신
        # 커피가 있으면 그 누적 상태가 보여야 한다 — unknown이 아니다.
        items = build_daily_projected_statuses(
            {"caffeine": None}, _day(total_caffeine=150, known_caffeine_count=1), LIMITS
        )

        caffeine = _by_key(items)["caffeine"]
        assert caffeine["value"] == 150
        assert caffeine["status"] == "caution"  # 150/200 = 75%
        assert caffeine["tier"] == "caution"

    def test_typed_caffeine_is_judged_like_any_other_value(self):
        items = build_daily_projected_statuses(
            {"caffeine": 120.0}, _day(total_caffeine=150, known_caffeine_count=1), LIMITS
        )

        caffeine = _by_key(items)["caffeine"]
        assert caffeine["value"] == 270  # 135% of 200mg
        assert caffeine["status"] == "avoid"

    def test_caffeine_unknown_when_neither_logged_nor_typed(self):
        items = build_daily_projected_statuses({"caffeine": None}, _EMPTY_DAY, LIMITS)

        assert _by_key(items)["caffeine"]["tier"] == "unknown"


# ── build_daily_projected_statuses: 하한형(floor-type) ────────────

class TestProjectedFloorTypeStatuses:
    def test_breakfast_shortfall_is_neutral_not_a_warning(self):
        # Part 3의 핵심: 아침에 스캔하면 하루 최소 섭취량은 당연히 미달이다.
        # "부족"이라고 표시하되 경고 등급으로 올리지 않는다.
        items = build_daily_projected_statuses({"protein": 10.0}, _EMPTY_DAY, LIMITS)

        protein = _by_key(items)["protein"]
        assert protein["status"] == "insufficient"
        assert protein["tier"] == "neutral"
        assert protein["status_label"] == "부족"

    def test_floor_type_never_produces_caution_or_avoid(self):
        items = build_daily_projected_statuses(
            {"carbohydrate": 1.0, "protein": 1.0, "energy": 1.0}, _EMPTY_DAY, LIMITS
        )
        by_key = _by_key(items)

        for key in ("carbohydrate", "protein", "energy"):
            assert by_key[key]["tier"] not in ("caution", "avoid")

    def test_floor_type_meeting_the_target_is_safe(self):
        items = build_daily_projected_statuses(
            {"protein": 20.0}, _day(total_protein=60, known_protein_count=1), LIMITS
        )

        protein = _by_key(items)["protein"]
        assert protein["value"] == 80  # target 70g
        assert protein["status"] == "sufficient"
        assert protein["tier"] == "safe"

    def test_floor_type_is_still_judged_not_hardcoded_unknown(self):
        # 기존 get_item_nutrient_status()는 floor형을 값과 무관하게 unknown으로
        # 돌려줬다. 일일 투영에서는 실제로 판정한다.
        items = build_daily_projected_statuses({"carbohydrate": 200.0}, _EMPTY_DAY, LIMITS)

        assert _by_key(items)["carbohydrate"]["status"] != "unknown"


# ── build_daily_projected_statuses: 밴드형(band-type) ─────────────

class TestProjectedBandTypeStatuses:
    def test_iron_below_lower_bound_is_neutral(self):
        # ADDITION B: 철분은 band형이지만 하한 미달은 floor형과 동일하게 중립이다.
        items = build_daily_projected_statuses({"iron": 5.0}, _EMPTY_DAY, LIMITS)

        iron = _by_key(items)["iron"]
        assert iron["status"] == "low"
        assert iron["tier"] == "neutral"

    def test_iron_above_upper_limit_is_avoid(self):
        items = build_daily_projected_statuses({"iron": 50.0}, _EMPTY_DAY, LIMITS)

        iron = _by_key(items)["iron"]
        assert iron["status"] == "avoid"  # 50 > 45mg 상한
        assert iron["tier"] == "avoid"

    def test_iron_limit_exposed_is_the_upper_limit(self):
        items = build_daily_projected_statuses({"iron": 30.0}, _EMPTY_DAY, LIMITS)

        assert _by_key(items)["iron"]["limit"] == 45.0

    def test_fat_bound_comes_from_the_daily_energy_target_not_accumulated_intake(self):
        # 상한 = 하루 에너지 목표(2340) * 30% / 9kcal = 78.0g. 오늘 얼마나 먹었는지와
        # 무관하게 그날 내내 같은 숫자다 — 나트륨 1500mg과 같은 성격의 고정 기준.
        low_energy_day = build_daily_projected_statuses({"fat": 10.0}, _EMPTY_DAY, LIMITS)
        high_energy_day = build_daily_projected_statuses(
            {"energy": 1800.0, "fat": 10.0}, _day(total_calories=500, known_energy_count=1), LIMITS
        )

        assert _by_key(low_energy_day)["fat"]["limit"] == pytest.approx(78.0, abs=0.01)
        assert _by_key(high_energy_day)["fat"]["limit"] == pytest.approx(78.0, abs=0.01)

    def test_fat_dense_breakfast_on_an_empty_day_is_not_a_warning(self):
        # 회귀 방지(T7의 핵심): 누적 에너지를 분모로 쓰던 시절에는 아침에 스캔한
        # 지방 20g/에너지 135kcal짜리 품목이 상한(135*0.3/9=4.5g)을 훌쩍 넘겨
        # "위험"으로 판정됐다. 목표(2340kcal -> 78g)를 분모로 쓰면 정상이다.
        items = build_daily_projected_statuses({"energy": 135.0, "fat": 20.0}, _EMPTY_DAY, LIMITS)

        fat = _by_key(items)["fat"]
        assert fat["tier"] not in ("caution", "avoid")
        assert fat["status"] == "low"  # 78g 목표 대비로는 아직 하한 미달일 뿐

    def test_fat_below_lower_bound_is_neutral(self):
        # 하한 = 2340 * 15% / 9 = 39.0g. 20g은 미달이지만 경고가 아니다.
        items = build_daily_projected_statuses({"energy": 2000.0, "fat": 20.0}, _EMPTY_DAY, LIMITS)

        fat = _by_key(items)["fat"]
        assert fat["status"] == "low"
        assert fat["tier"] == "neutral"

    def test_fat_is_judged_even_when_no_energy_is_known(self):
        # 이전에는 에너지가 없으면 지방도 unknown이었다(분모를 만들 수 없어서).
        # 이제 분모가 하루 목표라 에너지 유무와 무관하게 판정된다 — 지방이 unknown인
        # 것은 지방 값 자체가 없을 때뿐이다.
        items = build_daily_projected_statuses({"fat": 90.0}, _EMPTY_DAY, LIMITS)

        fat = _by_key(items)["fat"]
        assert fat["status"] == "avoid"  # 90g > 78g 상한
        assert fat["limit"] == pytest.approx(78.0, abs=0.01)
        assert fat["percent"] is not None

    def test_fat_is_unknown_only_when_the_fat_value_itself_is_unknown(self):
        items = build_daily_projected_statuses({"energy": 2000.0}, _EMPTY_DAY, LIMITS)

        fat = _by_key(items)["fat"]
        assert fat["status"] == "unknown"
        assert fat["value"] is None


# ── tier_of_status ───────────────────────────────────────────────

class TestTierOfStatus:
    @pytest.mark.parametrize("status,expected", [
        ("safe", "safe"), ("caution", "caution"), ("avoid", "avoid"), ("unknown", "unknown"),
    ])
    def test_ceiling_tiers_pass_through(self, status, expected):
        assert tier_of_status("ceiling", status) == expected

    @pytest.mark.parametrize("status,expected", [
        ("sufficient", "safe"), ("insufficient", "neutral"), ("unknown", "unknown"),
    ])
    def test_floor_shortfall_is_neutral(self, status, expected):
        assert tier_of_status("floor", status) == expected

    @pytest.mark.parametrize("status,expected", [
        ("safe", "safe"), ("low", "neutral"), ("caution", "caution"),
        ("avoid", "avoid"), ("unknown", "unknown"),
    ])
    def test_band_low_is_neutral_but_upper_breaches_are_warnings(self, status, expected):
        assert tier_of_status("band", status) == expected


# ── _headline_ratio: 0으로 나누기 방어 ────────────────────────────

class TestHeadlineRatio:
    def test_normal_ratio(self):
        assert _headline_ratio(_status_item("sodium", "avoid", value=3110, limit=1500)) == pytest.approx(2.073, abs=0.001)

    def test_zero_limit_returns_zero_instead_of_dividing(self):
        # 도달 가능한 경로다: 투영 에너지가 0이면 지방 상한이 0으로 계산될 수 있다.
        assert _headline_ratio(_status_item("fat", "avoid", value=10, limit=0)) == 0.0

    def test_none_limit_returns_zero(self):
        assert _headline_ratio(_status_item("fat", "avoid", value=10, limit=None)) == 0.0

    def test_none_value_returns_zero(self):
        assert _headline_ratio(_status_item("sodium", "unknown", value=None, limit=1500)) == 0.0


# ── select_headline_nutrient ─────────────────────────────────────

class TestSelectHeadlineNutrient:
    def test_returns_none_when_nothing_is_judgeable(self):
        statuses = [_status_item(key, "unknown") for key in ("sodium", "sugar", "caffeine")]

        assert select_headline_nutrient(statuses, []) is None

    def test_worst_severity_wins_over_preference(self):
        statuses = [
            _status_item("sodium", "avoid", value=3000, limit=1500),
            _status_item("sugar", "caution", value=45, limit=50),
        ]

        assert select_headline_nutrient(statuses, ["sugar"])["key"] == "sodium"

    def test_preference_breaks_ties_within_the_same_severity(self):
        # 같은 avoid 등급이면 비율(207% vs 102%)보다 관심성분이 먼저다.
        statuses = [
            _status_item("sodium", "avoid", value=3105, limit=1500),
            _status_item("sugar", "avoid", value=51, limit=50),
        ]

        assert select_headline_nutrient(statuses, ["sugar"])["key"] == "sugar"

    def test_higher_ratio_wins_when_preference_does_not_separate(self):
        # 둘 다 비관심성분. 고정 순서로는 sodium이 앞서지만 비율은 sugar가 높다 —
        # 비율(4단계)이 고정 순서(5단계)보다 우선이므로 sugar가 이겨야 한다.
        statuses = [
            _status_item("sodium", "avoid", value=1530, limit=1500),   # 102%
            _status_item("sugar", "avoid", value=103.5, limit=50),     # 207%
        ]

        assert select_headline_nutrient(statuses, [])["key"] == "sugar"

    def test_fixed_order_breaks_a_complete_tie(self):
        statuses = [
            _status_item("sugar", "avoid", value=75, limit=50),        # 150%
            _status_item("sodium", "avoid", value=2250, limit=1500),   # 150%
        ]

        # HEADLINE_TIEBREAK_ORDER: caffeine, sodium, sugar, fat, iron
        assert select_headline_nutrient(statuses, [])["key"] == "sodium"

    def test_caffeine_outranks_everything_on_a_complete_tie(self):
        statuses = [
            _status_item("sodium", "avoid", value=2250, limit=1500),
            _status_item("caffeine", "avoid", value=300, limit=200),
        ]

        assert select_headline_nutrient(statuses, [])["key"] == "caffeine"

    def test_safe_is_selected_when_nothing_worse_exists(self):
        statuses = [
            _status_item("sodium", "safe", value=500, limit=1500),
            _status_item("carbohydrate", "neutral", value=10, limit=175),
        ]

        result = select_headline_nutrient(statuses, [])
        assert result["key"] == "sodium"
        assert result["tier"] == "safe"

    def test_floor_type_nutrients_are_never_selected(self):
        # 하한형만 판정 가능한 상태여도 헤드라인은 없다 — 경고할 것이 없기 때문.
        statuses = [
            _status_item("carbohydrate", "safe", value=200, limit=175),
            _status_item("protein", "neutral", value=10, limit=70),
            _status_item("energy", "safe", value=2400, limit=2340),
        ]

        assert select_headline_nutrient(statuses, ["carbohydrate", "protein"]) is None

    def test_iron_below_lower_bound_is_not_selected(self):
        # ADDITION B: 하한 미달(neutral)인 철분은 유일한 후보여도 뽑히지 않는다.
        statuses = [_status_item("iron", "neutral", value=5, limit=45)]

        assert select_headline_nutrient(statuses, ["iron"]) is None

    def test_iron_above_upper_limit_is_eligible(self):
        statuses = [_status_item("iron", "avoid", value=50, limit=45)]

        result = select_headline_nutrient(statuses, [])
        assert result is not None
        assert result["key"] == "iron"

    def test_selection_is_deterministic_across_repeated_calls(self):
        # recompute는 타이핑마다 디바운스로 재호출된다 — 무작위 타이브레이크가 있으면
        # 글자를 칠 때마다 헤드라인이 튄다.
        statuses = [
            _status_item("sodium", "avoid", value=2250, limit=1500),
            _status_item("sugar", "avoid", value=75, limit=50),
            _status_item("caffeine", "avoid", value=300, limit=200),
        ]

        results = {select_headline_nutrient(statuses, [])["key"] for _ in range(50)}
        assert results == {"caffeine"}

    def test_end_to_end_headline_from_a_real_projection(self):
        items = build_daily_projected_statuses(
            {"sodium": 1710.0, "protein": 5.0}, _day(total_sodium=1400, known_sodium_count=1), LIMITS
        )

        result = select_headline_nutrient(items, [])
        assert result["key"] == "sodium"
        assert result["tier"] == "avoid"
        assert result["label"] == "나트륨"
