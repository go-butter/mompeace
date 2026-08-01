"""
backend/gemini_vision.py 테스트.

핵심 검증 대상:
- Gemini 응답(JSON 문자열)이 GeminiLabelExtraction 스키마로 정상 검증/변환된다
- 필수 필드(nutrition_table_found)가 없거나 reference_amount_display_method가
  허용되지 않은 값이면 검증에 실패한다
- 잘못된 형식의 JSON 문자열은 검증 실패로 처리된다 (네트워크 호출 없이 확인 가능)
- GEMINI_API_KEY가 설정되어 있지 않으면 call_gemini_vision()은 실제 API를
  호출하기 전에 즉시 실패한다 (네트워크 호출 없음)
"""
import pytest
from pydantic import ValidationError

from backend import gemini_vision
from backend.gemini_vision import _parse_response, call_gemini_vision


# ── _parse_response: 정상 케이스 ─────────────────────────────────

def test_parse_response_well_formed_json_all_fields():
    raw = """
    {
      "product_name": "감자깡",
      "nutrition_table_found": true,
      "reference_amount_display_method": "per_basis_with_total",
      "basis_amount_value": 100.0,
      "total_content_value": 355.0,
      "servings_per_container": null,
      "serving_size_g": 30.0,
      "sugar_g_per_basis": 12.0,
      "sodium_mg_per_basis": 50.0
    }
    """
    result = _parse_response(raw)
    assert result["product_name"] == "감자깡"
    assert result["nutrition_table_found"] is True
    assert result["reference_amount_display_method"] == "per_basis_with_total"
    assert result["basis_amount_value"] == 100.0
    assert result["total_content_value"] == 355.0
    assert result["serving_size_g"] == 30.0
    assert result["sugar_g_per_basis"] == 12.0
    assert result["sodium_mg_per_basis"] == 50.0


def test_parse_response_missing_optional_fields_default_to_none_or_unknown():
    raw = '{"nutrition_table_found": true}'
    result = _parse_response(raw)
    assert result["product_name"] is None
    assert result["reference_amount_display_method"] == "unknown"
    assert result["serving_size_g"] is None
    assert result["sugar_g_per_basis"] is None
    assert result["sodium_mg_per_basis"] is None


def test_parse_response_label_not_found():
    raw = '{"nutrition_table_found": false}'
    result = _parse_response(raw)
    assert result["nutrition_table_found"] is False


# ── _parse_response: 검증 실패 케이스 ────────────────────────────

def test_parse_response_missing_required_field_raises():
    raw = '{"product_name": "테스트"}'  # nutrition_table_found 없음 (필수)
    with pytest.raises(ValidationError):
        _parse_response(raw)


def test_parse_response_invalid_display_method_raises():
    raw = """
    {
      "nutrition_table_found": true,
      "reference_amount_display_method": "존재하지_않는_방식"
    }
    """
    with pytest.raises(ValidationError):
        _parse_response(raw)


def test_parse_response_malformed_json_raises():
    raw = "{이것은 JSON이 아님"
    with pytest.raises(ValidationError):
        _parse_response(raw)


# ── call_gemini_vision: API 키 미설정 시 네트워크 호출 없이 즉시 실패 ──

def test_call_gemini_vision_without_api_key_raises_before_network_call(monkeypatch):
    monkeypatch.setattr(gemini_vision, "GEMINI_API_KEY", None)
    with pytest.raises(ValueError):
        call_gemini_vision("ZmFrZS1iYXNlNjQ=")
