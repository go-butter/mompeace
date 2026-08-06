"""
backend/gemini_vision.py 테스트.

핵심 검증 대상:
- Gemini 응답(JSON 문자열)이 GeminiLabelExtraction 스키마로 정상 검증/변환된다
- 필수 필드(nutrition_table_found)가 없거나 reference_amount_display_method가
  허용되지 않은 값이면 검증에 실패한다
- 잘못된 형식의 JSON 문자열은 검증 실패로 처리된다 (네트워크 호출 없이 확인 가능)
- GEMINI_API_KEY가 설정되어 있지 않으면 call_gemini_vision()은 실제 API를
  호출하기 전에 즉시 실패한다 (네트워크 호출 없음), 그것도 다른 실패와 구분되는
  GeminiNotConfiguredError로 실패한다
- OCR_RAW_LOG_PATH가 설정된 경우 Gemini 응답 원문이 파싱 "전에" 기록되므로,
  스키마 검증 실패(ValidationError)로 502가 되는 응답도 원문이 파일에 남는다
"""
import json
from datetime import date
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from backend import gemini_vision
from backend.gemini_vision import (
    GeminiDailyLimitExceededError,
    GeminiNotConfiguredError,
    _parse_response,
    call_gemini_vision,
)


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
      "carbohydrate_g_per_basis": 70.0,
      "sugar_g_per_basis": 12.0,
      "energy_kcal_per_basis": 450.0,
      "fat_g_per_basis": 18.0,
      "iron_mg_per_basis": 1.2,
      "protein_g_per_basis": 6.0,
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
    assert result["carbohydrate_g_per_basis"] == 70.0
    assert result["sugar_g_per_basis"] == 12.0
    assert result["energy_kcal_per_basis"] == 450.0
    assert result["fat_g_per_basis"] == 18.0
    assert result["iron_mg_per_basis"] == 1.2
    assert result["protein_g_per_basis"] == 6.0
    assert result["sodium_mg_per_basis"] == 50.0


def test_parse_response_missing_optional_fields_default_to_none_or_unknown():
    raw = '{"nutrition_table_found": true}'
    result = _parse_response(raw)
    assert result["product_name"] is None
    assert result["reference_amount_display_method"] == "unknown"
    assert result["serving_size_g"] is None
    assert result["carbohydrate_g_per_basis"] is None
    assert result["sugar_g_per_basis"] is None
    assert result["energy_kcal_per_basis"] is None
    assert result["fat_g_per_basis"] is None
    assert result["iron_mg_per_basis"] is None
    assert result["protein_g_per_basis"] is None
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

def test_call_gemini_vision_without_api_key_raises_not_configured(monkeypatch):
    # ValueError가 아니라 전용 예외여야 한다 — routers/ocr.py가 "설정이 안 됨"(503)과
    # "호출이 실패함"(502)을 구분해 응답하려면 타입으로 구분 가능해야 한다.
    monkeypatch.setattr(gemini_vision, "GEMINI_API_KEY", None)
    with pytest.raises(GeminiNotConfiguredError):
        call_gemini_vision("ZmFrZS1iYXNlNjQ=")


# ── call_gemini_vision: 하루 호출 상한 초과 시 네트워크 호출 없이 즉시 실패 ──
# _call_count_by_day는 모듈 전역 상태이므로, monkeypatch.setattr로 세팅해 테스트가
# 끝나면 자동으로 원복되게 한다 (다른 테스트로 카운트가 새어나가지 않도록).

def test_call_gemini_vision_over_daily_limit_raises_before_network_call(monkeypatch):
    monkeypatch.setattr(gemini_vision, "GEMINI_API_KEY", "fake-key-for-test")
    today = date.today().isoformat()
    monkeypatch.setattr(
        gemini_vision, "_call_count_by_day", {today: gemini_vision.GEMINI_DAILY_CALL_LIMIT}
    )
    with pytest.raises(GeminiDailyLimitExceededError):
        call_gemini_vision("ZmFrZS1iYXNlNjQ=")


def test_under_daily_limit_true_when_no_calls_recorded_today(monkeypatch):
    monkeypatch.setattr(gemini_vision, "_call_count_by_day", {})
    assert gemini_vision._under_daily_limit() is True


def test_under_daily_limit_true_one_below_limit(monkeypatch):
    today = date.today().isoformat()
    monkeypatch.setattr(
        gemini_vision, "_call_count_by_day", {today: gemini_vision.GEMINI_DAILY_CALL_LIMIT - 1}
    )
    assert gemini_vision._under_daily_limit() is True


def test_under_daily_limit_false_at_limit(monkeypatch):
    today = date.today().isoformat()
    monkeypatch.setattr(
        gemini_vision, "_call_count_by_day", {today: gemini_vision.GEMINI_DAILY_CALL_LIMIT}
    )
    assert gemini_vision._under_daily_limit() is False


def test_record_call_increments_todays_count(monkeypatch):
    monkeypatch.setattr(gemini_vision, "_call_count_by_day", {})
    gemini_vision._record_call()
    gemini_vision._record_call()
    today = date.today().isoformat()
    assert gemini_vision._call_count_by_day[today] == 2


# ── Gemini 응답 원문 기록(_append_raw_log) ───────────────────────

def _use_fake_gemini(monkeypatch, raw_text: str) -> None:
    """genai.Client를 "정해진 텍스트만 돌려주는" 가짜로 바꾼다.

    새 의존성 없이 monkeypatch만 쓴다. 이 가짜 덕분에 call_gemini_vision()의
    응답 처리 경로(기록 -> 파싱)를 네트워크 없이 그대로 통과시켜 볼 수 있다.
    """
    class _FakeModels:
        def generate_content(self, **kwargs):
            return SimpleNamespace(text=raw_text)

    class _FakeClient:
        def __init__(self, api_key=None):
            self.models = _FakeModels()

    monkeypatch.setattr(gemini_vision, "GEMINI_API_KEY", "fake-key-for-test")
    monkeypatch.setattr(gemini_vision, "_call_count_by_day", {})
    monkeypatch.setattr(gemini_vision.genai, "Client", _FakeClient)


def _use_raw_log(monkeypatch, path, max_lines: int = 10) -> None:
    monkeypatch.setattr(gemini_vision, "OCR_RAW_LOG_PATH", str(path))
    monkeypatch.setattr(gemini_vision, "OCR_RAW_LOG_MAX", max_lines)
    monkeypatch.setattr(gemini_vision, "_raw_log_count", 0)


def test_append_raw_log_noop_when_path_unset(monkeypatch, tmp_path):
    target = tmp_path / "raw.jsonl"
    monkeypatch.setattr(gemini_vision, "OCR_RAW_LOG_PATH", None)
    monkeypatch.setattr(gemini_vision, "_raw_log_count", 0)

    gemini_vision._append_raw_log('{"a": 1}')

    assert not target.exists()
    assert gemini_vision._raw_log_count == 0


def test_append_raw_log_writes_one_jsonl_line(monkeypatch, tmp_path):
    target = tmp_path / "raw.jsonl"
    _use_raw_log(monkeypatch, target)
    raw = '{"product_name": "테스트 과자"}'

    gemini_vision._append_raw_log(raw)

    lines = target.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1
    record = json.loads(lines[0])
    # 원문을 파싱하지 않고 문자열 그대로 담는다 — 파싱할 수 없는 응답이야말로
    # 남겨야 하는 대상이라, 여기서 구조를 강제하면 목적이 어긋난다.
    assert record["raw_text"] == raw
    assert record["model"] == gemini_vision.MODEL_NAME
    assert "ts" in record


def test_append_raw_log_stops_at_max(monkeypatch, tmp_path):
    target = tmp_path / "raw.jsonl"
    _use_raw_log(monkeypatch, target, max_lines=2)

    for i in range(5):
        gemini_vision._append_raw_log(f'{{"n": {i}}}')

    lines = target.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 2


def test_append_raw_log_swallows_write_failure(monkeypatch, tmp_path):
    # 존재하지 않는 디렉터리 아래 경로 — 기록은 실패하지만 예외가 올라오면 안 된다
    # (관찰용 부가 기능이 스캔 자체를 막아서는 안 된다).
    _use_raw_log(monkeypatch, tmp_path / "nonexistent-dir" / "raw.jsonl")

    gemini_vision._append_raw_log('{"a": 1}')

    assert gemini_vision._raw_log_count == 0


def test_call_gemini_vision_logs_raw_text_on_success(monkeypatch, tmp_path):
    target = tmp_path / "raw.jsonl"
    raw = '{"nutrition_table_found": true, "sugar_g_per_basis": 12.0}'
    _use_fake_gemini(monkeypatch, raw)
    _use_raw_log(monkeypatch, target)

    result = call_gemini_vision("ZmFrZQ==")

    assert result["sugar_g_per_basis"] == 12.0
    record = json.loads(target.read_text(encoding="utf-8").strip())
    assert record["raw_text"] == raw


def test_call_gemini_vision_logs_raw_text_even_when_parse_fails(monkeypatch, tmp_path):
    # 이 테스트가 T1의 핵심이다: 스키마 검증에 실패하면 지금까지는 응답 본문이
    # 그대로 사라졌는데(라우터에서 502로 바뀌며), 실제 오독 패턴을 보려면 바로 그
    # 응답이 필요하다. 기록은 _parse_response 호출 "전에" 일어나야 한다.
    target = tmp_path / "raw.jsonl"
    malformed = '{"nutrition_table_found": true, "sugar_g_per_basis": "많음"}'
    _use_fake_gemini(monkeypatch, malformed)
    _use_raw_log(monkeypatch, target)

    with pytest.raises(ValidationError):
        call_gemini_vision("ZmFrZQ==")

    record = json.loads(target.read_text(encoding="utf-8").strip())
    assert record["raw_text"] == malformed
