"""
backend/intake_totals.py::get_item_nutrient_status() / build_item_nutrient_statuses() 테스트.

단일 품목(예: OCR 스캔 결과 한 건) 단위 영양소 상태 판정 — 누적 하루 판정
(_build_nutrient_summary_item 등)과는 별개의 함수다.

핵심 검증 대상:
- 당류/나트륨(ceiling)은 get_status()와 동일한 여유/안전/위험 경계를 따른다
- 철분(band)은 get_iron_status()의 하한(부족)/상한(안전/주의/위험) 판정을 따른다
- 지방(band)은 "이 품목 자신의 에너지"를 분모로 쓴다 — 분자/분모가 같은 배율로
  스케일되면(=같은 음식의 다른 인분 크기) 비율이 그대로라 상태가 바뀌지 않는다
  (작은 인분이라고 부당하게 "위험"이 되지 않는다는 설계 근거를 검증)
- 지방 판정 시 이 품목의 에너지 값이 None이면 크래시 없이 "unknown"
- 탄수화물/에너지/단백질(floor)은 값과 무관하게 항상 "unknown" — 누적 하루 최소치
  개념이라 단일 품목에는 적용하지 않기로 한 제품 결정 사항
- 어떤 영양소든 값이 None이면 "unknown"
- build_item_nutrient_statuses()는 값이 여러 개 없어도 항상 7개 항목을 반환한다
"""
import pytest

from backend.intake_totals import build_item_nutrient_statuses, get_item_nutrient_status, get_trimester_limits
from backend.nutrition_constants import DEFAULT_AGE_BRACKET

# 임신 20주차, 기본 나이대 기준 limits — DAILY_SUGAR_LIMIT_G=50.0, DAILY_SODIUM_LIMIT_MG=1500.0,
# FAT_ENERGY_RATIO_MIN=0.15, FAT_ENERGY_RATIO_MAX=0.30 (nutrition_constants.py 참고).
_, LIMITS = get_trimester_limits(20, DEFAULT_AGE_BRACKET)


# ── ceiling: 당류/나트륨 ──────────────────────────────────────────

def test_sugar_safe_below_seventy_percent():
    assert get_item_nutrient_status("sugar", 30.0, LIMITS, item_energy_kcal=None) == "safe"


def test_sugar_caution_between_seventy_and_hundred_percent():
    assert get_item_nutrient_status("sugar", 40.0, LIMITS, item_energy_kcal=None) == "caution"


def test_sugar_avoid_above_limit():
    assert get_item_nutrient_status("sugar", 60.0, LIMITS, item_energy_kcal=None) == "avoid"


def test_sodium_safe_below_seventy_percent():
    assert get_item_nutrient_status("sodium", 1000.0, LIMITS, item_energy_kcal=None) == "safe"


def test_sodium_caution_between_seventy_and_hundred_percent():
    assert get_item_nutrient_status("sodium", 1200.0, LIMITS, item_energy_kcal=None) == "caution"


def test_sodium_avoid_above_limit():
    assert get_item_nutrient_status("sodium", 1800.0, LIMITS, item_energy_kcal=None) == "avoid"


# ── band: 철분 (에너지 분모 불필요, 절대 mg 기준) ────────────────

def test_iron_low_below_recommended():
    assert get_item_nutrient_status("iron", 10.0, LIMITS, item_energy_kcal=None) == "low"


def test_iron_safe_between_recommended_and_seventy_percent_of_upper():
    assert get_item_nutrient_status("iron", 30.0, LIMITS, item_energy_kcal=None) == "safe"


def test_iron_caution_between_seventy_percent_and_upper():
    assert get_item_nutrient_status("iron", 35.0, LIMITS, item_energy_kcal=None) == "caution"


def test_iron_avoid_above_upper_limit():
    assert get_item_nutrient_status("iron", 50.0, LIMITS, item_energy_kcal=None) == "avoid"


def test_iron_none_value_is_unknown():
    assert get_item_nutrient_status("iron", None, LIMITS, item_energy_kcal=None) == "unknown"


# ── band: 지방 (이 품목 자신의 에너지가 분모) ────────────────────

def test_fat_safe_case():
    # upper=1000*0.30/9=33.33, ratio=20/33.33=0.6<=0.7 -> safe; lower=1000*0.15/9=16.67, 20>=16.67
    assert get_item_nutrient_status("fat", 20.0, LIMITS, item_energy_kcal=1000.0) == "safe"


def test_fat_low_case():
    # upper=10, ratio=2/10=0.2 -> not caution/avoid; lower=5, 2<5 -> low
    assert get_item_nutrient_status("fat", 2.0, LIMITS, item_energy_kcal=300.0) == "low"


def test_fat_caution_case():
    # upper=300*0.30/9=10, ratio=9/10=0.9 -> caution
    assert get_item_nutrient_status("fat", 9.0, LIMITS, item_energy_kcal=300.0) == "caution"


def test_fat_avoid_case():
    # upper=450*0.30/9=15, ratio=18/15=1.2 -> avoid
    assert get_item_nutrient_status("fat", 18.0, LIMITS, item_energy_kcal=450.0) == "avoid"


def test_fat_status_is_scale_invariant_for_same_ratio():
    """분자(지방)와 분모(에너지)가 같은 배율로 스케일되면(=같은 음식의 다른 인분
    크기) 비율이 그대로이므로 상태도 동일해야 한다 — 작은 인분이라고 부당하게
    "위험"이 되지 않는다는 Q5 설계 근거를 직접 검증하는 테스트."""
    small_portion = get_item_nutrient_status("fat", 9.0, LIMITS, item_energy_kcal=225.0)  # 절반 인분
    large_portion = get_item_nutrient_status("fat", 18.0, LIMITS, item_energy_kcal=450.0)  # 원래 인분
    huge_portion = get_item_nutrient_status("fat", 36.0, LIMITS, item_energy_kcal=900.0)  # 두 배 인분
    assert small_portion == large_portion == huge_portion == "avoid"


def test_fat_status_unknown_when_item_energy_is_none():
    # get_fat_status()는 energy_total<=0만 방어하고 None은 방어하지 않는다(TypeError
    # 위험) — get_item_nutrient_status()가 호출 전에 직접 막아야 하는 지점.
    assert get_item_nutrient_status("fat", 18.0, LIMITS, item_energy_kcal=None) == "unknown"


def test_fat_status_unknown_when_fat_value_is_none():
    assert get_item_nutrient_status("fat", None, LIMITS, item_energy_kcal=450.0) == "unknown"


# ── floor: 탄수화물/에너지/단백질은 단일 품목에서 항상 unknown ──

@pytest.mark.parametrize("key", ["carbohydrate", "energy", "protein"])
def test_floor_type_always_unknown_regardless_of_value(key):
    assert get_item_nutrient_status(key, 5.0, LIMITS, item_energy_kcal=None) == "unknown"


@pytest.mark.parametrize("key", ["carbohydrate", "energy", "protein"])
def test_floor_type_always_unknown_even_for_excessive_value(key):
    # 값이 아무리 커도(명백히 "많이 섭취") floor 타입은 단일 품목에서 실제
    # 판정으로 새지 않고 항상 unknown이어야 한다 — 우연히 다른 분기로 빠지지
    # 않는지 확인.
    assert get_item_nutrient_status(key, 100000.0, LIMITS, item_energy_kcal=None) == "unknown"


@pytest.mark.parametrize("key", ["carbohydrate", "energy", "protein"])
def test_floor_type_always_unknown_even_when_value_is_none(key):
    assert get_item_nutrient_status(key, None, LIMITS, item_energy_kcal=None) == "unknown"


# ── build_item_nutrient_statuses: 전체 7개 항목 조립 ─────────────

def test_build_item_nutrient_statuses_returns_seven_entries():
    result = build_item_nutrient_statuses(
        {"carbohydrate": None, "sugar": None, "energy": None, "fat": None, "iron": None, "protein": None, "sodium": None},
        LIMITS,
    )
    assert len(result) == 7
    assert {item["key"] for item in result} == {
        "carbohydrate", "sugar", "energy", "fat", "iron", "protein", "sodium",
    }


def test_build_item_nutrient_statuses_all_none_yields_all_unknown_labels():
    result = build_item_nutrient_statuses(
        {"carbohydrate": None, "sugar": None, "energy": None, "fat": None, "iron": None, "protein": None, "sodium": None},
        LIMITS,
    )
    for item in result:
        assert item["status"] == "unknown"
        assert item["status_label"] == "정보없음"


def test_build_item_nutrient_statuses_uses_energy_for_fat_denominator():
    nutrients = {
        "carbohydrate": 70.0, "sugar": 12.0, "energy": 450.0, "fat": 18.0,
        "iron": 1.2, "protein": 6.0, "sodium": 178.0,
    }
    result = {item["key"]: item for item in build_item_nutrient_statuses(nutrients, LIMITS)}
    assert result["fat"]["status"] == "avoid"  # 위 test_fat_avoid_case와 동일한 값
    assert result["fat"]["status_label"] == "위험"
    assert result["carbohydrate"]["status"] == "unknown"  # floor 타입은 값이 있어도 unknown
    assert result["carbohydrate"]["status_label"] == "정보없음"
    assert result["sugar"]["label"] == "당류"
    assert result["sugar"]["unit"] == "g"
    assert result["sodium"]["unit"] == "mg"
    assert result["iron"]["unit"] == "mg"
