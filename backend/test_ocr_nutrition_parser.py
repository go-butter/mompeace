"""
backend/ocr_nutrition_parser.py 테스트.

핵심 검증 대상:
- '100g'/'355 ml' 같은 라벨 문자열에서 선행 숫자만 정확히 추출된다
- 기준량 대비 총 내용량 배율이 정확히 계산되며, 값 누락/기준량<=0이면 None이다
- 영양소 원본 값이 None이면 스케일이 있어도 결과는 항상 None이다 (정보 없음 ≠ 0)
- Gemini가 분류한 reference_amount_display_method의 3가지 케이스(total_content /
  per_basis_with_total / per_serving_with_count)에 맞는 스케일이 적용된다
- 분류된 방식에 필요한 값이 실제로는 빠져 있으면 "unknown"으로 강등되고
  needs_review=True가 된다
"""
import pytest

from backend.ocr_nutrition_parser import (
    compute_total_content_scale,
    parse_amount_value,
    resolve_ocr_nutrients,
    scale_value,
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

def test_compute_total_content_scale_basic_ratio():
    assert compute_total_content_scale(100.0, 355.0) == pytest.approx(3.55)


def test_compute_total_content_scale_missing_basis_returns_none():
    assert compute_total_content_scale(None, 355.0) is None


def test_compute_total_content_scale_missing_total_returns_none():
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

def test_resolve_per_basis_with_total_applies_ratio():
    extraction = {
        "product_name": "감자깡",
        "nutrition_table_found": True,
        "reference_amount_display_method": "per_basis_with_total",
        "basis_amount_value": 100.0,
        "total_content_value": 355.0,
        "servings_per_container": None,
        "sugar_g_per_basis": 12.0,
        "sodium_mg_per_basis": 50.0,
    }
    result = resolve_ocr_nutrients(extraction)
    assert result["scale_method"] == "per_basis_with_total"
    assert result["scale_factor_applied"] == pytest.approx(3.55)
    assert result["sugar_g"] == pytest.approx(42.6)
    assert result["sodium_mg"] == pytest.approx(177.5)
    assert result["needs_review"] is False


def test_resolve_per_basis_with_total_missing_total_downgrades_to_unknown():
    extraction = {
        "product_name": "테스트 과자",
        "nutrition_table_found": True,
        "reference_amount_display_method": "per_basis_with_total",
        "basis_amount_value": 100.0,
        "total_content_value": None,  # Gemini가 분류는 했지만 실제 값이 없음
        "servings_per_container": None,
        "sugar_g_per_basis": 12.0,
        "sodium_mg_per_basis": 50.0,
    }
    result = resolve_ocr_nutrients(extraction)
    assert result["scale_method"] == "unknown"
    assert result["scale_factor_applied"] is None
    assert result["needs_review"] is True
    # raw 값은 스케일 없이 그대로 유지
    assert result["sugar_g"] == 12.0
    assert result["sodium_mg"] == 50.0


# ── resolve_ocr_nutrients: case (c) per_serving_with_count ──────

def test_resolve_per_serving_with_count_multiplies_by_servings():
    extraction = {
        "product_name": "테스트 음료수",
        "nutrition_table_found": True,
        "reference_amount_display_method": "per_serving_with_count",
        "basis_amount_value": None,
        "total_content_value": None,
        "servings_per_container": 3.0,
        "sugar_g_per_basis": 10.0,
        "sodium_mg_per_basis": 100.0,
    }
    result = resolve_ocr_nutrients(extraction)
    assert result["scale_method"] == "per_serving_with_count"
    assert result["scale_factor_applied"] == 3.0
    assert result["sugar_g"] == pytest.approx(30.0)
    assert result["sodium_mg"] == pytest.approx(300.0)
    assert result["needs_review"] is False


def test_resolve_per_serving_with_count_missing_count_downgrades_to_unknown():
    extraction = {
        "product_name": "테스트 음료수",
        "nutrition_table_found": True,
        "reference_amount_display_method": "per_serving_with_count",
        "basis_amount_value": None,
        "total_content_value": None,
        "servings_per_container": None,
        "sugar_g_per_basis": 10.0,
        "sodium_mg_per_basis": 100.0,
    }
    result = resolve_ocr_nutrients(extraction)
    assert result["scale_method"] == "unknown"
    assert result["needs_review"] is True


# ── resolve_ocr_nutrients: 미분류/unknown ───────────────────────

def test_resolve_unknown_method_needs_review_and_raw_passthrough():
    extraction = {
        "product_name": None,
        "nutrition_table_found": True,
        "reference_amount_display_method": "unknown",
        "basis_amount_value": None,
        "total_content_value": None,
        "servings_per_container": None,
        "sugar_g_per_basis": 5.0,
        "sodium_mg_per_basis": None,
    }
    result = resolve_ocr_nutrients(extraction)
    assert result["scale_method"] == "unknown"
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
        "sugar_g_per_basis": None,  # 라벨에서 읽지 못함
        "sodium_mg_per_basis": 50.0,
    }
    result = resolve_ocr_nutrients(extraction)
    assert result["scale_method"] == "per_basis_with_total"
    assert result["sugar_g"] is None
    assert result["sodium_mg"] == pytest.approx(177.5)
