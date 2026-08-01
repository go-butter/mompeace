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
  - per_basis_with_total: serving_size_g가 있어야 기준량 대비 1회 제공량 비율을
    계산할 수 있다. 없으면 scale_factor=None, needs_review=True이지만
    scale_method는 "per_basis_with_total"로 유지되고 basis_amount_value가 그대로
    반환되어, 호출 측이 "그램 직접 입력" 대체 흐름을 제공할 수 있다.
  - unknown (또는 분류 실패): scale_factor=None, needs_review=True,
    basis_amount_value도 보통 알 수 없음 → 완전 수동 입력으로 폴백
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
        "serving_size_g": None,
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
        "serving_size_g": 30.0,
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
        "serving_size_g": None,
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
        "serving_size_g": 30.0,
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
        "serving_size_g": 30.0,
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
        "serving_size_g": 30.0,
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
        "serving_size_g": None,
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
        "serving_size_g": 30.0,
        "sugar_g_per_basis": None,  # 라벨에서 읽지 못함
        "sodium_mg_per_basis": 50.0,
    }
    result = resolve_ocr_nutrients(extraction)
    assert result["scale_method"] == "per_basis_with_total"
    assert result["sugar_g"] is None
    assert result["sodium_mg"] == pytest.approx(15.0)
