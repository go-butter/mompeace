"""build_panel_nutrients(): 추천 화면 상단 패널의 영양소 항목.

핵심은 "방향이 항목 안에 들어 있다"는 것이다 — 화면은 어떤 영양소가 상한형이고 어떤
것이 하한형인지 알 필요가 없어야 한다. 그래서 검증 대상도 세 가지다:
1. 카페인이 항상 첫 번째이고, 사용자가 고른 영양소가 저장된 순서로 뒤따르는가
2. 방향별로 올바른 경계 키를 쓰는가 (ceiling=limit / floor=target / band=lower+upper)
3. "정보 없음"을 0으로도, 결핍으로도 바꾸지 않는가
"""
import pytest

from backend.intake_totals import build_panel_nutrients, get_trimester_limits
from backend.nutrition_constants import (
    DEFAULT_AGE_BRACKET,
    IRON_RECOMMENDED_MG,
    IRON_UPPER_LIMIT_MG,
)

# 임신 20주(middle) + 기본 나이대: 카페인 200mg / 당류 50g / 나트륨 2300mg /
# 탄수화물 175g / 단백질 70g / 에너지 2340kcal / 지방 39~78g / 철분 24~45mg
_, LIMITS = get_trimester_limits(20, DEFAULT_AGE_BRACKET)

_ALL_NUTRIENT_KEYS = ("caffeine", "sugar", "sodium", "carbohydrate", "protein", "energy", "fat", "iron")

_TOTAL_KEYS = {
    "caffeine": "total_caffeine", "sugar": "total_sugar", "sodium": "total_sodium",
    "carbohydrate": "total_carbohydrate", "protein": "total_protein",
    "energy": "total_calories", "fat": "total_fat", "iron": "total_iron",
}
_KNOWN_KEYS = {
    "caffeine": "known_caffeine_count", "sugar": "known_sugar_count",
    "sodium": "known_sodium_count", "carbohydrate": "known_carbohydrate_count",
    "protein": "known_protein_count", "energy": "known_energy_count",
    "fat": "known_fat_count", "iron": "known_iron_count",
}


def _day(logged_count=1, **values):
    """하루 집계 딕셔너리. values로 넘긴 영양소만 "확인된 값"이 되고(known_count=1),
    나머지는 합계 0 / known 0으로 남는다 — fetch_daily_nutrient_totals의 실제 형태와 같다."""
    totals = {"logged_count": logged_count}
    for key in _ALL_NUTRIENT_KEYS:
        totals[_TOTAL_KEYS[key]] = values.get(key, 0)
        totals[_KNOWN_KEYS[key]] = 1 if key in values else 0
    return totals


_EMPTY_DAY = _day(logged_count=0)


def _by_key(items):
    return {item["key"]: item for item in items}


# ── 구성과 순서 ────────────────────────────────────────────

class TestPanelComposition:
    def test_caffeine_is_always_first_even_with_three_selected(self):
        items = build_panel_nutrients(["protein", "iron", "fat"], _day(), LIMITS)

        assert [i["key"] for i in items] == ["caffeine", "protein", "iron", "fat"]

    def test_selected_order_is_preserved(self):
        items = build_panel_nutrients(["sodium", "carbohydrate", "sugar"], _day(), LIMITS)

        assert [i["key"] for i in items] == ["caffeine", "sodium", "carbohydrate", "sugar"]

    def test_caffeine_alone_when_user_selected_nothing(self):
        # selected_nutrients=""(사용자가 명시적으로 전부 해제)는 빈 리스트로 들어온다.
        items = build_panel_nutrients([], _day(), LIMITS)

        assert [i["key"] for i in items] == ["caffeine"]

    def test_caffeine_is_not_duplicated_if_it_somehow_arrives_in_selected(self):
        # validate_selected_nutrients가 카페인을 거르지만, 방어적으로 중복을 만들지 않는다.
        items = build_panel_nutrients(["caffeine", "sugar"], _day(), LIMITS)

        assert [i["key"] for i in items] == ["caffeine", "sugar"]

    def test_every_item_carries_its_own_direction(self):
        items = build_panel_nutrients(["protein", "fat", "sugar"], _day(), LIMITS)
        by_key = _by_key(items)

        assert by_key["caffeine"]["type"] == "ceiling"
        assert by_key["sugar"]["type"] == "ceiling"
        assert by_key["protein"]["type"] == "floor"
        assert by_key["fat"]["type"] == "band"


# ── 방향별 경계 키 ─────────────────────────────────────────

class TestBoundKeysByDirection:
    def test_ceiling_has_limit_and_remaining_headroom(self):
        items = build_panel_nutrients(["sugar"], _day(sugar=20), LIMITS)
        sugar = _by_key(items)["sugar"]

        assert sugar["limit"] == 50.0
        assert sugar["remaining"] == 30.0
        assert sugar["total"] == 20
        assert sugar["unit"] == "g"
        assert "target" not in sugar and "lower" not in sugar and "upper" not in sugar

    def test_floor_has_target_not_limit(self):
        # 방향이 반대인 값에 limit이라는 이름을 재사용하지 않는다.
        items = build_panel_nutrients(["protein"], _day(protein=26), LIMITS)
        protein = _by_key(items)["protein"]

        assert protein["target"] == 70.0
        assert protein["remaining"] == 44.0  # 목표까지 더 필요한 양
        assert protein["status"] == "insufficient"
        assert "limit" not in protein

    def test_band_has_lower_and_upper_but_no_single_remaining(self):
        items = build_panel_nutrients(["iron", "fat"], _day(iron=10, fat=50), LIMITS)
        by_key = _by_key(items)

        iron = by_key["iron"]
        assert iron["remaining"] is None
        assert iron["lower"] == IRON_RECOMMENDED_MG
        assert iron["upper"] == IRON_UPPER_LIMIT_MG
        assert "limit" not in iron and "target" not in iron

        fat = by_key["fat"]
        # 하루 에너지 목표(2340) * 15~30% / 9kcal
        assert fat["lower"] == pytest.approx(39.0, abs=0.01)
        assert fat["upper"] == pytest.approx(78.0, abs=0.01)
        assert fat["remaining"] is None


# ── exceeded는 상한형만 ────────────────────────────────────

class TestExceededIsCeilingOnly:
    def test_ceiling_at_zero_remaining_is_exceeded(self):
        items = build_panel_nutrients(["sodium"], _day(sodium=3000), LIMITS)
        sodium = _by_key(items)["sodium"]

        assert sodium["remaining"] == 0.0
        assert sodium["exceeded"] is True

    def test_ceiling_with_headroom_is_not_exceeded(self):
        items = build_panel_nutrients(["sodium"], _day(sodium=100), LIMITS)

        assert _by_key(items)["sodium"]["exceeded"] is False

    def test_floor_far_below_target_is_never_exceeded(self):
        # 미달은 "초과"가 아니다. 방향이 다른 두 사실을 한 필드로 합치지 않는다.
        items = build_panel_nutrients(["protein"], _day(protein=1), LIMITS)
        protein = _by_key(items)["protein"]

        assert protein["exceeded"] is False
        assert protein["status"] == "insufficient"

    def test_band_above_upper_bound_is_not_flagged_exceeded(self):
        items = build_panel_nutrients(["iron"], _day(iron=60), LIMITS)
        iron = _by_key(items)["iron"]

        assert iron["exceeded"] is False
        assert iron["status"] == "avoid"  # 상한 초과는 status로 드러난다


# ── 정보 없음 ≠ 0 ─────────────────────────────────────────

class TestNoDataIsNotZero:
    def test_floor_with_no_data_is_not_reported_as_deficient(self):
        # 오늘 기록은 있는데(logged_count=1) 단백질 값은 한 번도 확인되지 않은 경우.
        # "부족"은 데이터가 있어야 할 수 있는 주장이다.
        items = build_panel_nutrients(["protein"], _day(logged_count=1, sugar=10), LIMITS)
        protein = _by_key(items)["protein"]

        assert protein["status"] == "unknown"
        assert protein["remaining"] is None
        assert protein["total"] is None
        assert protein["status"] != "insufficient"

    def test_floor_on_an_empty_day_is_not_reported_as_deficient(self):
        # 아무것도 기록하지 않은 날. 빈 하루는 부족의 증거가 아니라 데이터의 부재다.
        items = build_panel_nutrients(["protein", "carbohydrate", "energy"], _EMPTY_DAY, LIMITS)
        by_key = _by_key(items)

        for key in ("protein", "carbohydrate", "energy"):
            assert by_key[key]["status"] == "unknown", key
            assert by_key[key]["remaining"] is None, key

    def test_band_on_an_empty_day_is_also_unknown(self):
        items = build_panel_nutrients(["fat", "iron"], _EMPTY_DAY, LIMITS)
        by_key = _by_key(items)

        assert by_key["fat"]["status"] == "unknown"
        assert by_key["iron"]["status"] == "unknown"

    def test_ceiling_on_an_empty_day_keeps_full_headroom(self):
        # 상한형은 다르다 — 아무것도 안 먹었으면 허용량은 정말로 통째로 남아 있다.
        items = build_panel_nutrients(["sugar"], _EMPTY_DAY, LIMITS)
        sugar = _by_key(items)["sugar"]

        assert sugar["remaining"] == 50.0
        assert sugar["status"] == "safe"
        assert sugar["total"] == 0

    def test_ceiling_with_no_data_is_not_reported_as_full_headroom(self):
        # 기록은 있는데 나트륨만 전부 NULL. 허용량이 그대로 남았다고 말할 근거가 없다.
        items = build_panel_nutrients(["sodium"], _day(logged_count=1, sugar=10), LIMITS)
        sodium = _by_key(items)["sodium"]

        assert sodium["status"] == "unknown"
        assert sodium["remaining"] is None
        assert sodium["total"] is None
        assert sodium["exceeded"] is False

    def test_zero_consumed_is_distinguishable_from_no_data(self):
        # 같은 0이라도 "확인된 0"과 "정보 없음"은 다른 응답이어야 한다.
        confirmed_zero = _by_key(build_panel_nutrients(["sugar"], _day(sugar=0), LIMITS))["sugar"]
        no_data = _by_key(build_panel_nutrients(["sugar"], _day(sodium=5), LIMITS))["sugar"]

        assert confirmed_zero["total"] == 0
        assert confirmed_zero["status"] == "safe"
        assert no_data["total"] is None
        assert no_data["status"] == "unknown"
