"""
backend/ocr_nutrition_parser.py 테스트.

핵심 검증 대상:
- '100g'/'355 ml' 같은 라벨 문자열에서 선행 숫자만 정확히 추출된다
- 기준량 대비 target_amount(총 내용량 또는 1회 제공량) 배율이 정확히 계산되며,
  값 누락/기준량<=0이면 None이다
- 영양소 원본 값이 None이면 스케일이 있어도 결과는 항상 None이다 (정보 없음 ≠ 0)
- resolve_ocr_nutrients()의 목표는 항상 "1회 제공량(1인분) 기준" 값이다:
  - total_content: 1회 제공량 = 총 내용량이므로 스케일 없음 (factor=1.0)
  - per_serving_with_count: 값이 이미 1회 제공량 기준이므로 스케일 없음
    (factor=1.0) — servings_per_container는 표시용일 뿐 계산에 쓰이지 않는다
  - per_basis_with_total: serving_size_value가 있어야 기준량 대비 1회 제공량 비율을
    계산할 수 있다. 없으면 scale_factor=None, needs_review=True이지만
    scale_method는 "per_basis_with_total"로 유지되고 basis_amount_value가 그대로
    반환되어, 호출 측이 "그램 직접 입력" 대체 흐름을 제공할 수 있다.
  - unknown (또는 분류 실패): scale_factor=None, needs_review=True,
    basis_amount_value도 보통 알 수 없음 → 완전 수동 입력으로 폴백
"""
import pytest

from backend.gemini_vision import GeminiLabelExtraction
from backend.ocr_nutrition_parser import (
    compute_total_content_scale,
    compute_total_content_value,
    parse_amount_value,
    resolve_ocr_nutrients,
    scale_value,
    truncate_to_places,
)


# ── 순수 함수 단위 테스트 (선행 숫자 파서) ──────────────────────

def test_parse_amount_value_grams():
    assert parse_amount_value("100g") == 100.0


def test_parse_amount_value_ml():
    assert parse_amount_value("355ml") == 355.0


def test_parse_amount_value_decimal():
    assert parse_amount_value("462.60g") == pytest.approx(462.60)


def test_parse_amount_value_with_space_before_unit():
    assert parse_amount_value("100 ml") == 100.0


def test_parse_amount_value_unparseable_returns_none():
    assert parse_amount_value("알수없음") is None


def test_parse_amount_value_none_returns_none():
    assert parse_amount_value(None) is None


def test_parse_amount_value_empty_string_returns_none():
    assert parse_amount_value("") is None


def test_parse_amount_value_pure_number_still_works():
    assert parse_amount_value("100") == 100.0


def test_parse_amount_value_already_numeric():
    assert parse_amount_value(100) == 100.0
    assert parse_amount_value(100.5) == 100.5


# ── 순수 함수 단위 테스트 (스케일 계산 / 적용) ──────────────────
# compute_total_content_scale은 "기준량 대비 target_amount 배율"이라는 동일한
# 개념을 총 내용량과 1회 제공량 양쪽에 재사용하는 순수 비율 함수다.

def test_compute_total_content_scale_basic_ratio():
    assert compute_total_content_scale(100.0, 355.0) == pytest.approx(3.55)


def test_compute_total_content_scale_missing_basis_returns_none():
    assert compute_total_content_scale(None, 355.0) is None


def test_compute_total_content_scale_missing_target_returns_none():
    assert compute_total_content_scale(100.0, None) is None


def test_compute_total_content_scale_zero_basis_returns_none():
    assert compute_total_content_scale(0.0, 355.0) is None


def test_compute_total_content_scale_negative_basis_returns_none():
    assert compute_total_content_scale(-10.0, 355.0) is None


def test_scale_value_applies_multiplication():
    assert scale_value(12.0, 3.55) == pytest.approx(42.6)


def test_scale_value_none_value_stays_none_even_with_scale():
    assert scale_value(None, 3.55) is None


def test_scale_value_none_scale_returns_raw_value():
    assert scale_value(12.0, None) == 12.0


# ── resolve_ocr_nutrients: case (a) total_content ───────────────

def test_resolve_total_content_no_scaling_applied():
    extraction = {
        "product_name": "테스트 음료",
        "nutrition_table_found": True,
        "reference_amount_display_method": "total_content",
        "basis_amount_value": None,
        "total_content_value": None,
        "servings_per_container": None,
        "serving_size_value": None,
        "sugar_g_per_basis": 8.0,
        "sodium_mg_per_basis": 200.0,
    }
    result = resolve_ocr_nutrients(extraction)
    assert result["scale_method"] == "total_content"
    assert result["scale_factor_applied"] == 1.0
    assert result["sugar_g"] == 8.0
    assert result["sodium_mg"] == 200.0
    assert result["needs_review"] is False


# ── resolve_ocr_nutrients: case (b) per_basis_with_total ────────

def test_resolve_per_basis_with_total_scales_to_serving_size():
    extraction = {
        "product_name": "감자깡",
        "nutrition_table_found": True,
        "reference_amount_display_method": "per_basis_with_total",
        "basis_amount_value": 100.0,
        "total_content_value": 355.0,
        "servings_per_container": None,
        "serving_size_value": 30.0,
        "sugar_g_per_basis": 12.0,
        "sodium_mg_per_basis": 50.0,
    }
    result = resolve_ocr_nutrients(extraction)
    assert result["scale_method"] == "per_basis_with_total"
    assert result["scale_factor_applied"] == pytest.approx(0.3)
    assert result["sugar_g"] == pytest.approx(3.6)
    assert result["sodium_mg"] == pytest.approx(15.0)
    assert result["needs_review"] is False


def test_resolve_per_basis_with_total_missing_serving_size_needs_review_but_keeps_basis():
    extraction = {
        "product_name": "테스트 과자",
        "nutrition_table_found": True,
        "reference_amount_display_method": "per_basis_with_total",
        "basis_amount_value": 100.0,
        "total_content_value": 355.0,  # 총 내용량은 있어도 1회 제공량이 없으면 계산 불가
        "servings_per_container": None,
        "serving_size_value": None,
        "sugar_g_per_basis": 12.0,
        "sodium_mg_per_basis": 50.0,
    }
    result = resolve_ocr_nutrients(extraction)
    # method는 "unknown"으로 강등되지 않는다 — 기준량은 알고 있으므로, 호출 측이
    # "그램 직접 입력" 대체 흐름을 제공할 수 있도록 method/basis_amount_value를 유지.
    assert result["scale_method"] == "per_basis_with_total"
    assert result["scale_factor_applied"] is None
    assert result["basis_amount_value"] == 100.0
    assert result["needs_review"] is True
    # raw 값은 스케일 없이 그대로 유지
    assert result["sugar_g"] == 12.0
    assert result["sodium_mg"] == 50.0


def test_resolve_per_basis_with_total_missing_basis_amount_needs_review():
    extraction = {
        "product_name": "테스트 과자",
        "nutrition_table_found": True,
        "reference_amount_display_method": "per_basis_with_total",
        "basis_amount_value": None,  # 기준량 자체가 없음
        "total_content_value": None,
        "servings_per_container": None,
        "serving_size_value": 30.0,
        "sugar_g_per_basis": 12.0,
        "sodium_mg_per_basis": 50.0,
    }
    result = resolve_ocr_nutrients(extraction)
    assert result["scale_factor_applied"] is None
    assert result["basis_amount_value"] is None
    assert result["needs_review"] is True


# ── resolve_ocr_nutrients: case (c) per_serving_with_count ──────

def test_resolve_per_serving_with_count_values_already_per_serving():
    extraction = {
        "product_name": "테스트 음료수",
        "nutrition_table_found": True,
        "reference_amount_display_method": "per_serving_with_count",
        "basis_amount_value": 30.0,
        "total_content_value": None,
        "servings_per_container": 3.0,
        "serving_size_value": 30.0,
        "sugar_g_per_basis": 10.0,
        "sodium_mg_per_basis": 100.0,
    }
    result = resolve_ocr_nutrients(extraction)
    assert result["scale_method"] == "per_serving_with_count"
    # 값이 이미 1회 제공량 기준이므로 스케일은 항상 1.0 (servings_per_container로
    # 곱하지 않는다 — 그건 "총 3회 제공" 표시용일 뿐, 스케일 계산 대상이 아니다)
    assert result["scale_factor_applied"] == 1.0
    assert result["sugar_g"] == pytest.approx(10.0)
    assert result["sodium_mg"] == pytest.approx(100.0)
    assert result["needs_review"] is False


def test_resolve_per_serving_with_count_missing_servings_count_still_resolved():
    # servings_per_container가 없어도 스케일 계산에는 필요 없으므로 여전히 resolved.
    extraction = {
        "product_name": "테스트 음료수",
        "nutrition_table_found": True,
        "reference_amount_display_method": "per_serving_with_count",
        "basis_amount_value": 30.0,
        "total_content_value": None,
        "servings_per_container": None,
        "serving_size_value": 30.0,
        "sugar_g_per_basis": 10.0,
        "sodium_mg_per_basis": 100.0,
    }
    result = resolve_ocr_nutrients(extraction)
    assert result["scale_method"] == "per_serving_with_count"
    assert result["scale_factor_applied"] == 1.0
    assert result["needs_review"] is False


# ── resolve_ocr_nutrients: 미분류/unknown ───────────────────────

def test_resolve_unknown_method_needs_review_and_raw_passthrough():
    extraction = {
        "product_name": None,
        "nutrition_table_found": True,
        "reference_amount_display_method": "unknown",
        "basis_amount_value": None,
        "total_content_value": None,
        "servings_per_container": None,
        "serving_size_value": None,
        "sugar_g_per_basis": 5.0,
        "sodium_mg_per_basis": None,
    }
    result = resolve_ocr_nutrients(extraction)
    assert result["scale_method"] == "unknown"
    assert result["basis_amount_value"] is None
    assert result["needs_review"] is True
    assert result["sugar_g"] == 5.0
    assert result["sodium_mg"] is None


def test_resolve_missing_method_field_defaults_to_unknown():
    extraction = {
        "nutrition_table_found": True,
        "sugar_g_per_basis": 5.0,
        "sodium_mg_per_basis": 10.0,
    }
    result = resolve_ocr_nutrients(extraction)
    assert result["scale_method"] == "unknown"
    assert result["needs_review"] is True


# ── None-preservation 회귀 테스트 ────────────────────────────────

def test_resolve_none_nutrient_stays_none_even_with_valid_scale():
    extraction = {
        "product_name": "테스트",
        "nutrition_table_found": True,
        "reference_amount_display_method": "per_basis_with_total",
        "basis_amount_value": 100.0,
        "total_content_value": 355.0,
        "servings_per_container": None,
        "serving_size_value": 30.0,
        "sugar_g_per_basis": None,  # 라벨에서 읽지 못함
        "sodium_mg_per_basis": 50.0,
    }
    result = resolve_ocr_nutrients(extraction)
    assert result["scale_method"] == "per_basis_with_total"
    assert result["sugar_g"] is None
    assert result["sodium_mg"] == pytest.approx(15.0)


# ── truncate_to_places ───────────────────────────────────────────

def test_truncate_to_places_none_returns_none():
    assert truncate_to_places(None) is None


def test_truncate_to_places_default_two_places():
    assert truncate_to_places(12.3456) == pytest.approx(12.34)


def test_truncate_to_places_does_not_round_up():
    # 118.357을 반올림하면 118.36이 되지만, 절사(truncate)는 118.35여야 한다 —
    # round()가 아니라 math.trunc를 쓰는지 확인하는 핵심 회귀 테스트. 두 결과가
    # 0.01 차이로 뚜렷이 갈리는 값을 골라 부동소수점 오차로 흔들리지 않게 했다.
    assert truncate_to_places(118.357, 2) == pytest.approx(118.35)
    assert truncate_to_places(118.357, 2) != pytest.approx(118.36)


def test_truncate_to_places_exact_value_unchanged():
    assert truncate_to_places(12.3, 2) == pytest.approx(12.3)


# ── compute_total_content_value ──────────────────────────────────

def test_compute_total_content_value_basic():
    # 100g당 33.34g -> 총 내용량 355g 기준: 33.34 * 3.55 = 118.357 -> 절사 118.35
    assert compute_total_content_value(33.34, 100.0, 355.0) == pytest.approx(118.35)


def test_compute_total_content_value_missing_basis_amount_returns_none():
    assert compute_total_content_value(12.0, None, 355.0) is None


def test_compute_total_content_value_missing_total_content_returns_none():
    assert compute_total_content_value(12.0, 100.0, None) is None


def test_compute_total_content_value_none_basis_value_stays_none():
    assert compute_total_content_value(None, 100.0, 355.0) is None


# ── resolve_ocr_nutrients: 7개 영양소 nutrients dict ─────────────

def _full_extraction(**overrides):
    base = {
        "product_name": "테스트 과자",
        "nutrition_table_found": True,
        "reference_amount_display_method": "per_basis_with_total",
        "basis_amount_value": 100.0,
        "total_content_value": 355.0,
        "servings_per_container": None,
        "serving_size_value": 30.0,
        "carbohydrate_g_per_basis": 70.0,
        "sugar_g_per_basis": 12.0,
        "energy_kcal_per_basis": 450.0,
        "fat_g_per_basis": 18.0,
        "iron_mg_per_basis": 1.2,
        "protein_g_per_basis": 6.0,
        "sodium_mg_per_basis": 178.0,
    }
    base.update(overrides)
    return base


def test_resolve_ocr_nutrients_returns_all_seven_nutrient_keys():
    result = resolve_ocr_nutrients(_full_extraction())
    assert set(result["nutrients"].keys()) == {
        "carbohydrate", "sugar", "energy", "fat", "iron", "protein", "sodium",
    }


def test_resolve_ocr_nutrients_basis_value_passthrough():
    result = resolve_ocr_nutrients(_full_extraction())
    assert result["nutrients"]["carbohydrate"]["basis_value"] == 70.0
    assert result["nutrients"]["protein"]["basis_value"] == 6.0


def test_resolve_ocr_nutrients_serving_value_uses_scale_factor():
    # scale_factor = serving_size_value(30) / basis_amount(100) = 0.3
    result = resolve_ocr_nutrients(_full_extraction())
    assert result["nutrients"]["carbohydrate"]["serving_value"] == pytest.approx(21.0)
    assert result["nutrients"]["energy"]["serving_value"] == pytest.approx(135.0)
    assert result["nutrients"]["fat"]["serving_value"] == pytest.approx(5.4)
    assert result["nutrients"]["iron"]["serving_value"] == pytest.approx(0.36)
    assert result["nutrients"]["protein"]["serving_value"] == pytest.approx(1.8)
    # 기존 top-level sugar_g/sodium_mg와도 정확히 일치해야 한다 (하위 호환, 기존 소비자 보호)
    assert result["sugar_g"] == result["nutrients"]["sugar"]["serving_value"]
    assert result["sodium_mg"] == result["nutrients"]["sodium"]["serving_value"]


def test_resolve_ocr_nutrients_total_value_uses_total_content_scale_and_truncates():
    # total scale = total_content_value(355) / basis_amount(100) = 3.55.
    # sugar/protein은 부동소수점 특성상 정확히 x.x0이 아니라 x.x99...로 계산되어
    # 절사 시 반올림했다면 나올 값(42.6/21.3)보다 0.01 작은 값이 된다 — 이 테스트가
    # 실제로 truncate(반올림 아님)를 검증하는 지점이다.
    result = resolve_ocr_nutrients(_full_extraction())
    assert result["nutrients"]["carbohydrate"]["total_value"] == pytest.approx(248.5)
    assert result["nutrients"]["sugar"]["total_value"] == pytest.approx(42.59)
    assert result["nutrients"]["energy"]["total_value"] == pytest.approx(1597.5)
    assert result["nutrients"]["fat"]["total_value"] == pytest.approx(63.9)
    assert result["nutrients"]["iron"]["total_value"] == pytest.approx(4.26)
    assert result["nutrients"]["protein"]["total_value"] == pytest.approx(21.29)
    assert result["nutrients"]["sodium"]["total_value"] == pytest.approx(631.9)
    assert result["total_content_value"] == 355.0


def test_resolve_ocr_nutrients_needs_review_total_value_still_computed():
    # serving_size_value 없음 -> needs_review=True, scale_factor=None -> serving_value는
    # 스케일 없이 raw 그대로(기존 동작). total_value는 basis_amount/total_content_value
    # 만 있으면 계산되므로 needs_review와 무관하게 채워져야 한다 (1회 제공량 스케일과
    # 완전히 독립적인 계산이라는 설계를 검증).
    extraction = _full_extraction(serving_size_value=None)
    result = resolve_ocr_nutrients(extraction)
    assert result["needs_review"] is True
    assert result["nutrients"]["carbohydrate"]["serving_value"] == 70.0  # raw passthrough
    assert result["nutrients"]["carbohydrate"]["total_value"] == pytest.approx(248.5)


def test_resolve_ocr_nutrients_missing_nutrient_field_is_none_throughout():
    extraction = _full_extraction()
    del extraction["iron_mg_per_basis"]
    result = resolve_ocr_nutrients(extraction)
    assert result["nutrients"]["iron"]["basis_value"] is None
    assert result["nutrients"]["iron"]["serving_value"] is None
    assert result["nutrients"]["iron"]["total_value"] is None


# ── 단위 필드 통과 (basis_amount_unit/total_content_unit/serving_size_unit) ──

def test_resolve_ocr_nutrients_passes_through_provided_units():
    extraction = _full_extraction(
        basis_amount_unit="ml", total_content_unit="ml", serving_size_unit="ml"
    )
    result = resolve_ocr_nutrients(extraction)
    assert result["basis_amount_unit"] == "ml"
    assert result["total_content_unit"] == "ml"
    assert result["serving_size_unit"] == "ml"


def test_resolve_ocr_nutrients_defaults_units_to_g_when_absent():
    extraction = _full_extraction()
    result = resolve_ocr_nutrients(extraction)
    assert result["basis_amount_unit"] == "g"
    assert result["total_content_unit"] == "g"
    assert result["serving_size_unit"] == "g"


# ── REGRESSION FIXTURES: backend/ocr_raw_log.jsonl의 실제 캡처 5건 ──────
# 이 5건은 실제 Gemini가 돌려준 원문(raw_text)을 그대로 옮긴 것이다 — 손으로
# 고쳐 쓴 값이 아니라, GeminiLabelExtraction.model_validate_json()으로 파싱한 뒤
# .model_dump()를 resolve_ocr_nutrients()에 그대로 넘긴다. 이렇게 해야 이번
# 변경(단위 필드 추가/이름 변경)이 실제 스캔 경로 전체를 깨뜨리지 않는지 검증된다.
#
# 원본은 이름 변경 이전 필드명(serving_size_g)을 쓰고 단위 필드가 아예 없다 —
# AliasChoices와 단위 기본값("g")이 없었다면 이 중 두 건(per_basis_with_total,
# per_serving_with_count)은 조용히 needs_review=True로 강등되었을 것이다.

def _parse_and_resolve(raw_text: str) -> dict:
    extraction = GeminiLabelExtraction.model_validate_json(raw_text)
    return resolve_ocr_nutrients(extraction.model_dump())


_RAW_CAPTURE_TOTAL_CONTENT_1 = (
    '{\n  "product_name": null,\n  "nutrition_table_found": true,\n  '
    '"reference_amount_display_method": "total_content",\n  "basis_amount_value": 20.0,\n  '
    '"total_content_value": 20.0,\n  "servings_per_container": null,\n  "serving_size_g": null,\n  '
    '"carbohydrate_g_per_basis": 3.0,\n  "sugar_g_per_basis": 0.0,\n  "energy_kcal_per_basis": 140.0,\n  '
    '"fat_g_per_basis": 13.0,\n  "iron_mg_per_basis": null,\n  "protein_g_per_basis": 3.0,\n  '
    '"sodium_mg_per_basis": 420.0\n}'
)

_RAW_CAPTURE_TOTAL_CONTENT_2 = (
    '{\n  "product_name": "EAT THE FIT",\n  "nutrition_table_found": true,\n  '
    '"reference_amount_display_method": "total_content",\n  "basis_amount_value": 40.0,\n  '
    '"total_content_value": 40.0,\n  "servings_per_container": null,\n  "serving_size_g": null,\n  '
    '"carbohydrate_g_per_basis": 12.9,\n  "sugar_g_per_basis": 2.5,\n  "energy_kcal_per_basis": 139.0,\n  '
    '"fat_g_per_basis": 1.6,\n  "iron_mg_per_basis": null,\n  "protein_g_per_basis": 21.3,\n  '
    '"sodium_mg_per_basis": 248.8\n}'
)

_RAW_CAPTURE_TOTAL_CONTENT_3 = (
    '{\n  "product_name": null,\n  "nutrition_table_found": true,\n  '
    '"reference_amount_display_method": "total_content",\n  "basis_amount_value": 200,\n  '
    '"total_content_value": 200,\n  "servings_per_container": null,\n  "serving_size_g": null,\n  '
    '"carbohydrate_g_per_basis": 20,\n  "sugar_g_per_basis": 19,\n  "energy_kcal_per_basis": 130,\n  '
    '"fat_g_per_basis": 3.2,\n  "iron_mg_per_basis": null,\n  "protein_g_per_basis": 5,\n  '
    '"sodium_mg_per_basis": 100\n}'
)

# per_basis_with_total: 유일한 실제 샘플. basis=30, serving_size_g=30 -> scale=1.0.
_RAW_CAPTURE_PER_BASIS_WITH_TOTAL = (
    '{"product_name":null,"nutrition_table_found":true,'
    '"reference_amount_display_method":"per_basis_with_total","basis_amount_value":30,'
    '"total_content_value":364,"servings_per_container":null,"serving_size_g":30,'
    '"carbohydrate_g_per_basis":19,"sugar_g_per_basis":3,"energy_kcal_per_basis":165,'
    '"fat_g_per_basis":9,"iron_mg_per_basis":null,"protein_g_per_basis":2,"sodium_mg_per_basis":150}'
)

# per_serving_with_count: 유일한 실제 샘플. basis=108, servings_per_container=5,
# serving_size_g=108 (옛 키 이름 그대로 — 이 값이 AliasChoices로 살아남는지가 핵심).
_RAW_CAPTURE_PER_SERVING_WITH_COUNT = (
    '{"product_name":null,"nutrition_table_found":true,'
    '"reference_amount_display_method":"per_serving_with_count","basis_amount_value":108,'
    '"total_content_value":540,"servings_per_container":5,"serving_size_g":108,'
    '"carbohydrate_g_per_basis":69,"sugar_g_per_basis":4,"energy_kcal_per_basis":460,'
    '"fat_g_per_basis":16,"iron_mg_per_basis":null,"protein_g_per_basis":10,"sodium_mg_per_basis":1710}'
)


class TestRealCaptureRegressionFixtures:
    """backend/ocr_raw_log.jsonl의 실제 캡처 5건이 이름 변경 이후에도 그대로 동작하는지."""

    def test_total_content_capture_1_resolves_without_review(self):
        result = _parse_and_resolve(_RAW_CAPTURE_TOTAL_CONTENT_1)
        assert result["needs_review"] is False
        assert result["scale_method"] == "total_content"
        assert result["nutrients"]["sodium"]["serving_value"] == pytest.approx(420.0)

    def test_total_content_capture_2_resolves_without_review(self):
        result = _parse_and_resolve(_RAW_CAPTURE_TOTAL_CONTENT_2)
        assert result["needs_review"] is False
        assert result["nutrients"]["protein"]["serving_value"] == pytest.approx(21.3)

    def test_total_content_capture_3_resolves_without_review(self):
        result = _parse_and_resolve(_RAW_CAPTURE_TOTAL_CONTENT_3)
        assert result["needs_review"] is False
        assert result["nutrients"]["carbohydrate"]["serving_value"] == pytest.approx(20.0)

    def test_per_basis_with_total_capture_resolves_serving_size_via_alias(self):
        # 옛 키 serving_size_g=30이 AliasChoices를 통해 serving_size_value로 살아남아야
        # scale_factor(30/30=1.0)가 계산되고 needs_review=False가 된다. 이 alias가
        # 없었다면 serving_size_value가 None이 되어 needs_review=True로 강등됐을 것이다.
        result = _parse_and_resolve(_RAW_CAPTURE_PER_BASIS_WITH_TOTAL)
        assert result["needs_review"] is False
        assert result["scale_factor_applied"] == pytest.approx(1.0)
        assert result["nutrients"]["carbohydrate"]["serving_value"] == pytest.approx(19.0)
        assert result["nutrients"]["sodium"]["serving_value"] == pytest.approx(150.0)

    def test_per_serving_with_count_capture_resolves_serving_size_via_alias(self):
        result = _parse_and_resolve(_RAW_CAPTURE_PER_SERVING_WITH_COUNT)
        assert result["needs_review"] is False
        assert result["scale_factor_applied"] == pytest.approx(1.0)
        assert result["nutrients"]["carbohydrate"]["serving_value"] == pytest.approx(69.0)
        assert result["nutrients"]["sodium"]["serving_value"] == pytest.approx(1710.0)

    def test_all_captures_default_unit_fields_to_g(self):
        # 원본 캡처에는 단위 필드가 아예 없다 — 전부 "g"로 기본값이 채워져야 한다.
        for raw in (
            _RAW_CAPTURE_TOTAL_CONTENT_1,
            _RAW_CAPTURE_PER_BASIS_WITH_TOTAL,
            _RAW_CAPTURE_PER_SERVING_WITH_COUNT,
        ):
            result = _parse_and_resolve(raw)
            assert result["basis_amount_unit"] == "g"
            assert result["total_content_unit"] == "g"
            assert result["serving_size_unit"] == "g"

    def test_old_key_name_does_not_force_needs_review(self):
        # AMENDMENT 2가 요구하는 명시적 회귀 테스트: 옛 키 이름(serving_size_g)을 쓰는
        # 페이로드가 needs_review를 True로 만들면 안 된다.
        result = _parse_and_resolve(_RAW_CAPTURE_PER_SERVING_WITH_COUNT)
        assert result["needs_review"] is False
