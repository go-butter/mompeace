"""
backend/intake_totals.py::build_nutrient_summary_item() 테스트.

NULL ≠ 0 회귀 테스트 — 무언가는 기록됐는데 이 영양소만 하나도 확인되지 않은 경우
(known_count==0, logged_count>0)에는 total/percent가 0이 아니라 None이어야 한다.
기록 자체가 없는 날(logged_count==0)은 여전히 0을 노출해야 한다(그렇지 않으면
아무것도 기록하지 않은 날조차 "정보없음"으로 보이게 된다).
"""
from backend.intake_totals import build_nutrient_summary_item, get_trimester_limits
from backend.nutrition_constants import DEFAULT_AGE_BRACKET

_, LIMITS = get_trimester_limits(20, DEFAULT_AGE_BRACKET)


def test_ceiling_total_is_none_when_logged_but_unresolved():
    # 오늘 음식은 기록됐지만(logged_count=3) 나트륨 값은 한 번도 확인되지 않음(known_count=0).
    item = build_nutrient_summary_item("sodium", 0.0, LIMITS, known_count=0, logged_count=3)
    assert item["total"] is None
    assert item["percent"] is None
    assert item["status"] == "unknown"


def test_ceiling_total_is_zero_when_nothing_logged():
    item = build_nutrient_summary_item("sodium", 0.0, LIMITS, known_count=0, logged_count=0)
    assert item["total"] == 0.0
    assert item["percent"] == 0


def test_ceiling_total_is_numeric_when_resolved():
    item = build_nutrient_summary_item("sodium", 300.0, LIMITS, known_count=2, logged_count=3)
    assert item["total"] == 300.0
    assert item["percent"] is not None


def test_floor_total_is_none_when_logged_but_unresolved():
    item = build_nutrient_summary_item("protein", 0.0, LIMITS, known_count=0, logged_count=2)
    assert item["total"] is None
    assert item["percent"] is None
    assert item["status"] == "unknown"


def test_band_total_is_none_when_logged_but_unresolved():
    # band형(지방/철분)은 limit/percent가 원래도 항상 None이지만, total까지 함께 확인한다.
    item = build_nutrient_summary_item("iron", 0.0, LIMITS, known_count=0, logged_count=1)
    assert item["total"] is None
    assert item["limit"] is None
    assert item["percent"] is None
