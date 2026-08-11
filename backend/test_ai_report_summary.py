"""
backend/ai_report_summary.py 테스트 — 네트워크 호출 없이 get_ai_report_analysis()의
오케스트레이션(캐시/지문/실패 처리/mock)만 검증한다. 실제 Gemini SDK 호출은
_call_gemini()를 monkeypatch로 갈아끼워 절대 나가지 않는다.

핵심 검증 대상:
- 캐시: 같은 (user, period, date, nutrient_items, pregnancy_week, trimester)면
  두 번째 호출은 Gemini를 다시 부르지 않는다
- 지문: nutrient_items 값이 바뀌거나(예: 음식을 더 기록해 총량이 바뀜), trimester가
  바뀌거나, trimester는 그대로여도 pregnancy_week만 바뀌면 캐시 키가 달라져 다시
  호출한다
- 실패 경로(API 키 없음/쿼터 초과/호출 자체 예외)는 전부 예외를 올리지 않고
  rule_based로 내려간다 — 쿼터 초과가 "에러"가 아니라는 점을 명시적으로 확인한다
- 실패는 캐시하지 않는다(다음 호출에서 다시 시도할 수 있어야 한다)
- mock 모드는 실제 호출 없이 고정 문구를 반환하고, 그 결과도 캐시된다
- 이 모듈의 쿼터 초과 예외는 gemini_vision.py의 것을 재사용하지 않는다(설계 결정 회귀 가드)
- _call_gemini()의 1회 재시도: 503(ServerError)/타임아웃 같은 일시적 오류에서만
  재시도하고, 404/401/403/429 같은 ClientError에서는 재시도하지 않는다. 재시도는
  정확히 한 번뿐이고(둘 다 실패하면 그대로 위로 올라간다), 네트워크 시도가 두 번
  나가도 하루 호출 쿼터는 한 번만 차감된다.
"""
import httpx
import pytest
from google.genai import errors as genai_errors

from backend import ai_report_summary as ai_summary_module
from backend.ai_report_summary import (
    AiReportSummaryDailyLimitExceededError,
    fingerprint_analysis_inputs,
    get_ai_report_analysis,
)


def _item(key, label, total, unit, limit, percent, status_label):
    return {
        "key": key, "label": label, "total": total, "unit": unit,
        "limit": limit, "percent": percent, "status": "safe", "status_label": status_label,
    }


def _nutrient_items(carb_total=150.0):
    return {
        "caffeine": _item("caffeine", "카페인", 50.0, "mg", 200.0, 25.0, "여유"),
        "nutrients": [
            _item(
                "carbohydrate", "탄수화물", carb_total, "g", 175.0,
                round(carb_total / 175 * 100, 1), "충분",
            ),
        ],
    }


@pytest.fixture(autouse=True)
def clear_module_state():
    """모듈 전역 캐시/쿼터 카운터는 테스트 간에 새로 시작해야 한다 — 순서에 따라
    캐시 히트가 우연히 성립하거나 쿼터가 이전 테스트 값을 물려받으면 안 된다."""
    ai_summary_module._analysis_cache.clear()
    ai_summary_module._call_count_by_day.clear()
    yield
    ai_summary_module._analysis_cache.clear()
    ai_summary_module._call_count_by_day.clear()


class TestFingerprint:
    def test_same_inputs_produce_same_fingerprint(self):
        a = fingerprint_analysis_inputs(_nutrient_items(150.0), 20, "middle")
        b = fingerprint_analysis_inputs(_nutrient_items(150.0), 20, "middle")
        assert a == b

    def test_different_totals_produce_different_fingerprint(self):
        a = fingerprint_analysis_inputs(_nutrient_items(150.0), 20, "middle")
        b = fingerprint_analysis_inputs(_nutrient_items(200.0), 20, "middle")
        assert a != b

    def test_different_trimester_produces_different_fingerprint(self):
        a = fingerprint_analysis_inputs(_nutrient_items(150.0), 20, "middle")
        b = fingerprint_analysis_inputs(_nutrient_items(150.0), 20, "late")
        assert a != b

    def test_different_pregnancy_week_produces_different_fingerprint_even_within_same_trimester(self):
        # 회귀 가드: trimester가 "middle"로 그대로여도(임신 15주 -> 16주 모두 중기)
        # 모델이 "임신 O주차인 지금은..."처럼 주차를 직접 언급할 수 있으므로, 주차가
        # 바뀌면 캐시도 새로 타야 한다.
        a = fingerprint_analysis_inputs(_nutrient_items(150.0), 15, "middle")
        b = fingerprint_analysis_inputs(_nutrient_items(150.0), 16, "middle")
        assert a != b


class TestGetAiReportAnalysisCaching:
    def test_second_call_with_same_data_hits_cache_no_gemini_call(self, monkeypatch):
        call_count = {"n": 0}

        def fake_call_gemini(period, nutrient_items, rule_messages, trimester, weekday_pattern=None):
            call_count["n"] += 1
            return "분석 결과입니다."

        monkeypatch.setattr(ai_summary_module, "_call_gemini", fake_call_gemini)

        items = _nutrient_items(150.0)
        result1 = get_ai_report_analysis(1, "daily", "2030-01-01", items, ["메시지"], 20, "middle")
        result2 = get_ai_report_analysis(1, "daily", "2030-01-01", items, ["메시지"], 20, "middle")

        assert call_count["n"] == 1
        assert result1 == result2 == {"source": "gemini", "text": "분석 결과입니다."}

    def test_changed_nutrient_items_bypasses_cache_and_calls_again(self, monkeypatch):
        # 회귀 가드: 하루 안에 음식을 더 기록해 판정 데이터가 바뀌면, (user, period,
        # date)만으로 캐시 키를 잡던 예전 설계는 새 총량을 무시하고 오래된 분석을
        # 계속 보여줬다. fingerprint가 키에 들어가면서 이 문제가 사라져야 한다.
        call_count = {"n": 0}

        def fake_call_gemini(period, nutrient_items, rule_messages, trimester, weekday_pattern=None):
            call_count["n"] += 1
            return f"호출 {call_count['n']}회차"

        monkeypatch.setattr(ai_summary_module, "_call_gemini", fake_call_gemini)

        get_ai_report_analysis(1, "daily", "2030-01-01", _nutrient_items(150.0), ["메시지"], 20, "middle")
        result2 = get_ai_report_analysis(1, "daily", "2030-01-01", _nutrient_items(200.0), ["메시지"], 20, "middle")

        assert call_count["n"] == 2
        assert result2 == {"source": "gemini", "text": "호출 2회차"}

    def test_pregnancy_week_advancing_bypasses_cache(self, monkeypatch):
        call_count = {"n": 0}

        def fake_call_gemini(period, nutrient_items, rule_messages, trimester, weekday_pattern=None):
            call_count["n"] += 1
            return f"호출 {call_count['n']}회차"

        monkeypatch.setattr(ai_summary_module, "_call_gemini", fake_call_gemini)

        items = _nutrient_items(150.0)
        get_ai_report_analysis(1, "daily", "2030-01-01", items, ["m"], 15, "middle")
        get_ai_report_analysis(1, "daily", "2030-01-01", items, ["m"], 16, "middle")

        assert call_count["n"] == 2

    def test_different_user_or_period_is_a_separate_cache_key(self, monkeypatch):
        call_count = {"n": 0}

        def fake_call_gemini(period, nutrient_items, rule_messages, trimester, weekday_pattern=None):
            call_count["n"] += 1
            return "x"

        monkeypatch.setattr(ai_summary_module, "_call_gemini", fake_call_gemini)

        items = _nutrient_items(150.0)
        get_ai_report_analysis(1, "daily", "2030-01-01", items, ["m"], 20, "middle")
        get_ai_report_analysis(2, "daily", "2030-01-01", items, ["m"], 20, "middle")
        get_ai_report_analysis(1, "weekly", "2030-01-01", items, ["m"], 20, "middle")

        assert call_count["n"] == 3


class TestGetAiReportAnalysisFallback:
    def test_any_gemini_exception_falls_back_to_rule_based_without_raising(self, monkeypatch):
        def raise_error(period, nutrient_items, rule_messages, trimester, weekday_pattern=None):
            raise RuntimeError("네트워크 오류")

        monkeypatch.setattr(ai_summary_module, "_call_gemini", raise_error)

        result = get_ai_report_analysis(1, "daily", "2030-01-01", _nutrient_items(), ["규칙 메시지"], 20, "middle")

        assert result == {"source": "rule_based", "messages": ["규칙 메시지"]}

    def test_daily_quota_exceeded_degrades_to_rule_based_not_an_error(self, monkeypatch):
        # 명시적으로 확인: 쿼터 초과는 예외로 올라가지 않고 rule_based로 내려간다.
        monkeypatch.setattr(ai_summary_module, "GEMINI_API_KEY", "dummy-key")
        monkeypatch.setattr(ai_summary_module, "_under_daily_limit", lambda: False)

        result = get_ai_report_analysis(1, "daily", "2030-01-01", _nutrient_items(), ["규칙 메시지"], 20, "middle")

        assert result == {"source": "rule_based", "messages": ["규칙 메시지"]}

    def test_missing_api_key_degrades_to_rule_based_not_an_error(self, monkeypatch):
        monkeypatch.setattr(ai_summary_module, "GEMINI_API_KEY", None)

        result = get_ai_report_analysis(1, "daily", "2030-01-01", _nutrient_items(), ["규칙 메시지"], 20, "middle")

        assert result == {"source": "rule_based", "messages": ["규칙 메시지"]}

    def test_failed_call_is_not_cached_so_next_call_retries_gemini(self, monkeypatch):
        attempts = {"n": 0}

        def flaky_call(period, nutrient_items, rule_messages, trimester, weekday_pattern=None):
            attempts["n"] += 1
            if attempts["n"] == 1:
                raise RuntimeError("일시적 오류")
            return "복구됨"

        monkeypatch.setattr(ai_summary_module, "_call_gemini", flaky_call)

        items = _nutrient_items()
        result1 = get_ai_report_analysis(1, "daily", "2030-01-01", items, ["m"], 20, "middle")
        result2 = get_ai_report_analysis(1, "daily", "2030-01-01", items, ["m"], 20, "middle")

        assert result1 == {"source": "rule_based", "messages": ["m"]}
        assert result2 == {"source": "gemini", "text": "복구됨"}
        assert attempts["n"] == 2


class TestMockMode:
    def test_mock_mode_returns_fixed_text_without_calling_gemini(self, monkeypatch):
        monkeypatch.setattr(ai_summary_module, "REPORT_AI_USE_MOCK_GEMINI", True)

        def fail_if_called(*args, **kwargs):
            raise AssertionError("mock 모드에서는 _call_gemini가 호출되면 안 된다")

        monkeypatch.setattr(ai_summary_module, "_call_gemini", fail_if_called)

        result = get_ai_report_analysis(1, "daily", "2030-01-01", _nutrient_items(), ["m"], 20, "middle")

        assert result["source"] == "gemini"
        assert isinstance(result["text"], str) and len(result["text"]) > 0

    def test_mock_mode_result_is_still_cached(self, monkeypatch):
        monkeypatch.setattr(ai_summary_module, "REPORT_AI_USE_MOCK_GEMINI", True)
        items = _nutrient_items()

        result1 = get_ai_report_analysis(1, "daily", "2030-01-01", items, ["m"], 20, "middle")
        result2 = get_ai_report_analysis(1, "daily", "2030-01-01", items, ["m"], 20, "middle")

        assert result1 == result2


class TestExceptionIdentity:
    def test_daily_limit_exceeded_error_is_not_reused_from_ocr_module(self):
        # gemini_vision.GeminiDailyLimitExceededError를 재사용하지 않는다는 설계
        # 결정을 회귀 가드로 남긴다 — 그 예외의 메시지는 "OCR 인식"에 고정되어 있다.
        from backend.gemini_vision import GeminiDailyLimitExceededError

        assert not issubclass(AiReportSummaryDailyLimitExceededError, GeminiDailyLimitExceededError)
        assert AiReportSummaryDailyLimitExceededError is not GeminiDailyLimitExceededError


class TestPromptPayloadIncludesKbNotesOnly:
    """_build_prompt_payload()가 실제로 KB 문단을 얹는지, 그리고 nutrient_items에
    없는 영양소(예: 나트륨 미선택)에 대한 조언은 섞이지 않는지 확인한다."""

    def test_reference_notes_include_iron_absorption_when_iron_present(self):
        items = {
            "caffeine": _item("caffeine", "카페인", 50.0, "mg", 200.0, 25.0, "여유"),
            "nutrients": [
                _item("iron", "철분", 10.0, "mg", None, None, "부족"),
            ],
        }
        payload = ai_summary_module._build_prompt_payload("daily", items, ["m"], "middle")

        notes = " ".join(payload["reference_notes"])
        assert "철분 흡수" in notes
        assert "비타민 C" in notes
        assert "탄닌" in notes

    def test_reference_notes_exclude_sodium_tips_when_sodium_not_present(self):
        items = _nutrient_items()  # caffeine + carbohydrate만, 나트륨 없음
        payload = ai_summary_module._build_prompt_payload("daily", items, ["m"], "middle")

        notes = " ".join(payload["reference_notes"])
        assert "찌개" not in notes and "젓갈" not in notes

    def test_reference_notes_include_trimester_note(self):
        items = _nutrient_items()
        payload = ai_summary_module._build_prompt_payload("daily", items, ["m"], "late")

        notes = " ".join(payload["reference_notes"])
        assert "변비" in notes


class TestCallGeminiRetriesOnceOnTransientErrors:
    """_call_gemini()의 1회 재시도 정책. _generate_analysis_text()(실제 네트워크
    요청을 보내는 가장 안쪽 함수)만 monkeypatch해 시도 횟수를 직접 센다 — genai
    클라이언트 자체는 만들어지지만(GEMINI_API_KEY만 있으면 되고 네트워크로 나가지
    않는다) 실제 호출은 발생하지 않는다."""

    def _server_error(self):
        return genai_errors.ServerError(503, {"message": "high demand", "status": "UNAVAILABLE"})

    def _client_error(self, code=404):
        return genai_errors.ClientError(code, {"message": "not found", "status": "NOT_FOUND"})

    def test_retries_once_on_server_error_and_succeeds(self, monkeypatch):
        monkeypatch.setattr(ai_summary_module, "GEMINI_API_KEY", "dummy-key")
        monkeypatch.setattr(ai_summary_module, "_TRANSIENT_RETRY_BACKOFF_SECONDS", 0)
        attempts = {"n": 0}

        def fake_generate(client, payload):
            attempts["n"] += 1
            if attempts["n"] == 1:
                raise self._server_error()
            return "복구된 응답"

        monkeypatch.setattr(ai_summary_module, "_generate_analysis_text", fake_generate)

        text = ai_summary_module._call_gemini("daily", _nutrient_items(), ["m"], "middle")

        assert text == "복구된 응답"
        assert attempts["n"] == 2

    def test_retries_once_on_timeout_and_succeeds(self, monkeypatch):
        monkeypatch.setattr(ai_summary_module, "GEMINI_API_KEY", "dummy-key")
        monkeypatch.setattr(ai_summary_module, "_TRANSIENT_RETRY_BACKOFF_SECONDS", 0)
        attempts = {"n": 0}

        def fake_generate(client, payload):
            attempts["n"] += 1
            if attempts["n"] == 1:
                raise httpx.ReadTimeout("timed out")
            return "복구됨"

        monkeypatch.setattr(ai_summary_module, "_generate_analysis_text", fake_generate)

        text = ai_summary_module._call_gemini("daily", _nutrient_items(), ["m"], "middle")

        assert text == "복구됨"
        assert attempts["n"] == 2

    def test_does_not_retry_more_than_once_when_both_attempts_fail(self, monkeypatch):
        monkeypatch.setattr(ai_summary_module, "GEMINI_API_KEY", "dummy-key")
        monkeypatch.setattr(ai_summary_module, "_TRANSIENT_RETRY_BACKOFF_SECONDS", 0)
        attempts = {"n": 0}

        def fake_generate(client, payload):
            attempts["n"] += 1
            raise self._server_error()

        monkeypatch.setattr(ai_summary_module, "_generate_analysis_text", fake_generate)

        with pytest.raises(genai_errors.ServerError):
            ai_summary_module._call_gemini("daily", _nutrient_items(), ["m"], "middle")

        assert attempts["n"] == 2  # 최초 시도 + 재시도 1회, 그 이상은 없다

    @pytest.mark.parametrize("code", [404, 401, 403, 429])
    def test_does_not_retry_on_client_errors(self, monkeypatch, code):
        # 404(모델 없음)/401·403(인증)/429(쿼터) — 재시도해도 똑같이 실패할 뿐이라
        # 재시도하지 않아야 한다.
        monkeypatch.setattr(ai_summary_module, "GEMINI_API_KEY", "dummy-key")
        attempts = {"n": 0}

        def fake_generate(client, payload):
            attempts["n"] += 1
            raise self._client_error(code)

        monkeypatch.setattr(ai_summary_module, "_generate_analysis_text", fake_generate)

        with pytest.raises(genai_errors.ClientError):
            ai_summary_module._call_gemini("daily", _nutrient_items(), ["m"], "middle")

        assert attempts["n"] == 1

    def test_retry_still_charges_only_one_daily_quota_call(self, monkeypatch):
        # 네트워크 시도가 두 번(최초 + 재시도) 나가도, _record_call()은 _call_gemini
        # 진입 시 한 번만 불린다 — 쿼터는 "요청이 몇 번 나갔는가"가 아니라 "이 함수가
        # 몇 번 불렸는가"를 센다.
        monkeypatch.setattr(ai_summary_module, "GEMINI_API_KEY", "dummy-key")
        monkeypatch.setattr(ai_summary_module, "_TRANSIENT_RETRY_BACKOFF_SECONDS", 0)
        ai_summary_module._call_count_by_day.clear()
        attempts = {"n": 0}

        def fake_generate(client, payload):
            attempts["n"] += 1
            if attempts["n"] == 1:
                raise self._server_error()
            return "ok"

        monkeypatch.setattr(ai_summary_module, "_generate_analysis_text", fake_generate)

        ai_summary_module._call_gemini("daily", _nutrient_items(), ["m"], "middle")

        today = ai_summary_module.date.today().isoformat()
        assert attempts["n"] == 2
        assert ai_summary_module._call_count_by_day[today] == 1

    def test_failure_after_exhausted_retry_still_degrades_to_rule_based(self, monkeypatch):
        # 상위 오케스트레이션까지 통합 확인 — 재시도까지 실패해도 카드는 여전히
        # rule_based를 받는다(에러 상태 없음 원칙은 재시도 추가로 깨지지 않는다).
        monkeypatch.setattr(ai_summary_module, "GEMINI_API_KEY", "dummy-key")
        monkeypatch.setattr(ai_summary_module, "_TRANSIENT_RETRY_BACKOFF_SECONDS", 0)

        def fake_generate(client, payload):
            raise self._server_error()

        monkeypatch.setattr(ai_summary_module, "_generate_analysis_text", fake_generate)

        result = get_ai_report_analysis(
            1, "daily", "2030-01-01", _nutrient_items(), ["규칙 메시지"], 20, "middle"
        )

        assert result == {"source": "rule_based", "messages": ["규칙 메시지"]}


class _FakeGeminiResponse:
    def __init__(self, text):
        self.text = text


class _FakeGeminiModels:
    def __init__(self, text):
        self._text = text

    def generate_content(self, **kwargs):
        return _FakeGeminiResponse(self._text)


class _FakeGeminiClient:
    """genai.Client(...)가 돌려주는 것과 같은 모양(.models.generate_content(...))의
    가짜 클라이언트 — 실제 네트워크 호출 없이 _generate_analysis_text()/_call_gemini()의
    "응답 파싱 이후" 로직만 검증한다."""

    def __init__(self, text):
        self.models = _FakeGeminiModels(text)


class TestGenerateAnalysisTextRejectsBlankText:
    """빈 회귀 가드 — backend/ai_report_summary.py:242 부근에서 발견된 버그:
    Gemini가 스키마상 유효하지만 내용이 비어 있는 text를 돌려주면(""든 공백뿐이든)
    성공으로 취급돼 카드가 빈 문단을 그대로 보여줬다. points 배열로 바뀐 뒤에도 같은
    가드가 유지되어야 한다 — 배열 자체가 비어 있거나, 원소가 전부 공백뿐이면 예외를
    올려야 한다."""

    def test_schema_rejects_empty_points_array(self):
        from pydantic import ValidationError

        client = _FakeGeminiClient('{"points": []}')
        with pytest.raises(ValidationError):
            ai_summary_module._generate_analysis_text(client, {"period": "daily"})

    def test_schema_rejects_more_than_three_points(self):
        # max_length=3 회귀 가드 — 카드가 무한정 길어지지 않도록 스키마 자체가 막는다.
        from pydantic import ValidationError

        client = _FakeGeminiClient(
            '{"points": ["하나.", "둘.", "셋.", "넷."]}'
        )
        with pytest.raises(ValidationError):
            ai_summary_module._generate_analysis_text(client, {"period": "daily"})

    def test_strip_check_rejects_whitespace_only_single_point(self):
        # 스키마의 min_length=1(배열)은 배열이 비어있지 않으면 통과시킨다 — 원소
        # 하나가 " "뿐이어도 배열 길이는 1이라 스키마를 통과하지만, strip() 필터가
        # 이걸 잡아야 한다.
        client = _FakeGeminiClient('{"points": ["   "]}')
        with pytest.raises(ValueError):
            ai_summary_module._generate_analysis_text(client, {"period": "daily"})

    def test_strip_check_rejects_all_blank_points(self):
        client = _FakeGeminiClient('{"points": ["", "  ", "\\n\\t\\n"]}')
        with pytest.raises(ValueError):
            ai_summary_module._generate_analysis_text(client, {"period": "daily"})

    def test_strip_check_filters_blank_points_and_keeps_valid_ones(self):
        # 일부만 공백인 경우 — 공백 원소만 걸러내고 나머지는 살려서 조인한다.
        client = _FakeGeminiClient('{"points": ["첫 문장.", "   ", "둘째 문장."]}')
        result = ai_summary_module._generate_analysis_text(client, {"period": "daily"})
        assert result == "첫 문장.\n둘째 문장."

    def test_valid_single_point_passes_through_unchanged(self):
        client = _FakeGeminiClient('{"points": ["정상적인 응답입니다."]}')
        result = ai_summary_module._generate_analysis_text(client, {"period": "daily"})
        assert result == "정상적인 응답입니다."

    def test_valid_multi_point_response_joins_with_newline(self):
        # 계약 회귀 가드: 이 "\n" 조인은 app/app/report.tsx의
        # AiSummaryCard.renderResolvedContent()가 text.split("\n")으로 다시 나누는
        # 것과 짝을 이룬다(_generate_analysis_text() 주석 참고) — 이 테스트가 실패하면
        # 조인 문자가 바뀌었다는 뜻이고, 프론트도 같이 바꾸지 않으면 화면이 다시 포인트
        # 구분 없는 한 덩어리로 보인다.
        client = _FakeGeminiClient(
            '{"points": ["첫 문장.", "둘째 문장.", "셋째 문장."]}'
        )
        result = ai_summary_module._generate_analysis_text(client, {"period": "daily"})
        assert "\n" in result
        assert result == "첫 문장.\n둘째 문장.\n셋째 문장."


class TestBlankTextEndToEndDegradesToRuleBasedAndIsNotCached:
    """오케스트레이션 전체(get_ai_report_analysis -> _call_gemini ->
    _generate_analysis_text)를 가짜 genai.Client로 실제로 통과시켜, 빈/공백 응답이
    끝까지 rule_based로 내려가고 캐시에 남지 않는지 확인한다 — _call_gemini나
    _generate_analysis_text를 monkeypatch로 건너뛰지 않고 진짜 코드 경로를 탄다."""

    def test_whitespace_only_response_degrades_to_rule_based_end_to_end(self, monkeypatch):
        monkeypatch.setattr(ai_summary_module, "GEMINI_API_KEY", "dummy-key")
        monkeypatch.setattr(
            ai_summary_module.genai, "Client", lambda api_key: _FakeGeminiClient('{"points": ["   "]}')
        )

        result = get_ai_report_analysis(
            1, "daily", "2030-01-01", _nutrient_items(), ["규칙 메시지"], 20, "middle"
        )

        assert result == {"source": "rule_based", "messages": ["규칙 메시지"]}

    def test_empty_points_array_response_degrades_to_rule_based_end_to_end(self, monkeypatch):
        monkeypatch.setattr(ai_summary_module, "GEMINI_API_KEY", "dummy-key")
        monkeypatch.setattr(
            ai_summary_module.genai, "Client", lambda api_key: _FakeGeminiClient('{"points": []}')
        )

        result = get_ai_report_analysis(
            1, "daily", "2030-01-01", _nutrient_items(), ["규칙 메시지"], 20, "middle"
        )

        assert result == {"source": "rule_based", "messages": ["규칙 메시지"]}

    def test_blank_response_is_not_cached_so_next_call_tries_gemini_again(self, monkeypatch):
        monkeypatch.setattr(ai_summary_module, "GEMINI_API_KEY", "dummy-key")
        call_count = {"n": 0}

        def make_client(api_key):
            call_count["n"] += 1
            return _FakeGeminiClient('{"points": ["   "]}')

        monkeypatch.setattr(ai_summary_module.genai, "Client", make_client)

        items = _nutrient_items()
        result1 = get_ai_report_analysis(1, "daily", "2030-01-01", items, ["m"], 20, "middle")
        result2 = get_ai_report_analysis(1, "daily", "2030-01-01", items, ["m"], 20, "middle")

        assert result1 == result2 == {"source": "rule_based", "messages": ["m"]}
        # 캐시에 빈 응답이 남았다면 두 번째 호출은 genai.Client를 아예 만들지 않았을
        # 것이다 — 두 번 다 실제로 시도했는지로 "캐시되지 않았다"를 확인한다.
        assert call_count["n"] == 2


class TestSuccessLogsLengthAndPreview:
    """성공 경로에만 로그가 없던 것이 이번 버그를 안 보이게 만든 원인이었다 —
    길이만 있었어도 바로 알아챘을 것이다."""

    def test_success_log_includes_length_and_preview(self, monkeypatch, capsys):
        text = "카페인 섭취량이 안전한 수준이에요. 철분은 육류와 녹색 채소로 조금 더 챙겨보세요."
        monkeypatch.setattr(ai_summary_module, "_call_gemini", lambda *a, **k: text)

        get_ai_report_analysis(1, "daily", "2030-01-01", _nutrient_items(), ["m"], 20, "middle")

        out = capsys.readouterr().out
        assert "Gemini 응답 성공" in out
        assert f"length={len(text)}" in out
        assert text[:40] in out

    def test_success_log_does_not_fire_on_cache_hit_or_failure(self, monkeypatch, capsys):
        # 캐시 히트/실패 경로는 이미 자기만의 로그 문구가 있다 — 성공 로그
        # ("Gemini 응답 성공")가 그 경로들에 잘못 섞이지 않는지 확인한다.
        monkeypatch.setattr(ai_summary_module, "GEMINI_API_KEY", "dummy-key")

        def raise_error(*a, **k):
            raise ValueError("blank")

        monkeypatch.setattr(ai_summary_module, "_call_gemini", raise_error)
        get_ai_report_analysis(1, "daily", "2030-01-01", _nutrient_items(), ["m"], 20, "middle")

        out = capsys.readouterr().out
        assert "Gemini 응답 성공" not in out
        assert "Gemini 호출 실패" in out


class TestRemainingAndGapFields:
    """_serialize_nutrient_items()가 계산하는 remaining(상한형)/gap(하한형) — 음식 제안
    기능이 추가되며 새로 생긴 필드. Gemini가 limit - total을 직접 계산하지 않도록
    파이썬에서 미리 뺄셈해 넣는다(원칙 ①: 숫자는 규칙 엔진에서 온다)."""

    def test_ceiling_nutrient_gets_remaining_not_gap(self):
        items = {
            "caffeine": _item("caffeine", "카페인", 50.0, "mg", 200.0, 25.0, "여유"),
            "nutrients": [],
        }
        serialized = ai_summary_module._serialize_nutrient_items(items)

        assert serialized[0]["remaining"] == 150.0
        assert serialized[0]["gap"] is None

    def test_ceiling_nutrient_over_limit_has_negative_remaining(self):
        # 회귀 가드: 초과분을 음수 그대로 넘긴다 — 어조 규칙(시스템 지시문)이 이걸
        # "-1300mg 남았어요"로 읽지 않게 막는 건 프롬프트 쪽 책임이지, 여기서 0으로
        # 자르거나 부호를 지우면 안 된다(그러면 "실제로 초과했다"는 사실 자체가 사라진다).
        items = {
            "caffeine": _item("caffeine", "카페인", 1400.0, "mg", 200.0, 700.0, "위험"),
            "nutrients": [],
        }
        serialized = ai_summary_module._serialize_nutrient_items(items)

        assert serialized[0]["remaining"] == -1200.0

    def test_floor_nutrient_gets_gap_not_remaining(self):
        items = _nutrient_items(carb_total=100.0)  # limit=175
        serialized = ai_summary_module._serialize_nutrient_items(items)

        carb = serialized[1]
        assert carb["gap"] == 75.0
        assert carb["remaining"] is None

    def test_floor_nutrient_met_has_zero_gap_not_negative(self):
        items = _nutrient_items(carb_total=200.0)  # limit=175, 이미 충분
        serialized = ai_summary_module._serialize_nutrient_items(items)

        assert serialized[1]["gap"] == 0

    def test_band_nutrient_has_no_remaining_or_gap(self):
        # band형(지방/철분)은 limit 자체가 항상 None이라(단일 상한 개념이 없음)
        # remaining/gap 계산 대상이 아니다.
        items = {
            "caffeine": _item("caffeine", "카페인", 50.0, "mg", 200.0, 25.0, "여유"),
            "nutrients": [_item("iron", "철분", 10.0, "mg", None, None, "부족")],
        }
        serialized = ai_summary_module._serialize_nutrient_items(items)

        iron = serialized[1]
        assert iron["remaining"] is None
        assert iron["gap"] is None

    def test_unresolved_total_has_no_remaining_or_gap(self):
        # total이 None(정보 없음)이면 NULL≠0 원칙에 따라 remaining/gap도 None이어야
        # 한다 — 0으로 계산해버리면 "정보 없음"을 "0"으로 둔갑시키는 것과 같은 문제다.
        items = {
            "caffeine": _item("caffeine", "카페인", None, "mg", 200.0, None, "정보없음"),
            "nutrients": [],
        }
        serialized = ai_summary_module._serialize_nutrient_items(items)

        assert serialized[0]["remaining"] is None
        assert serialized[0]["gap"] is None


class TestSystemInstructionFoodSuggestionRules:
    """새로 추가된 음식 제안 규칙이 시스템 지시문에 실제로 들어 있는지 확인한다 —
    프롬프트 문자열 회귀 가드."""

    def test_unsafe_food_exclusion_list_present(self):
        instruction = ai_summary_module._SYSTEM_INSTRUCTION
        for banned in ("내장육", "육회", "대형 어류", "건강기능식품", "카페인이 든 음료"):
            assert banned in instruction

    def test_no_supplement_dosage_or_brand_rule_present(self):
        instruction = ai_summary_module._SYSTEM_INSTRUCTION
        assert "보충제" in instruction
        assert "브랜드명" in instruction

    def test_never_declares_food_safe_or_unsafe(self):
        instruction = ai_summary_module._SYSTEM_INSTRUCTION
        assert '"안전해요"' in instruction or "안전 여부를 판단하는 말을 쓰지" in instruction

    def test_negative_remaining_tone_rule_present(self):
        instruction = ai_summary_module._SYSTEM_INSTRUCTION
        assert "남았어요" in instruction  # 금지 예시 문구가 실제로 들어 있는지

    def test_weekday_pattern_skip_rule_present(self):
        instruction = ai_summary_module._SYSTEM_INSTRUCTION
        assert "logged" in instruction and "건너뛰" in instruction


class TestWeekdayPatternInPayload:
    def test_omitted_from_payload_when_none(self):
        payload = ai_summary_module._build_prompt_payload(
            "daily", _nutrient_items(), ["m"], "middle", weekday_pattern=None
        )
        assert "weekday_pattern" not in payload

    def test_omitted_from_payload_when_empty(self):
        payload = ai_summary_module._build_prompt_payload(
            "weekly", _nutrient_items(), ["m"], "middle", weekday_pattern={}
        )
        assert "weekday_pattern" not in payload

    def test_included_in_payload_when_present(self):
        pattern = {"caffeine": [{"label": "월", "logged": True, "value": 1400.0,
                                  "pct": 700.0, "status": "avoid", "tier": "avoid"}]}
        payload = ai_summary_module._build_prompt_payload(
            "weekly", _nutrient_items(), ["m"], "middle", weekday_pattern=pattern
        )
        assert payload["weekday_pattern"] == pattern


class TestFingerprintSensitiveToWeekdayPattern:
    def test_same_weekday_pattern_same_fingerprint(self):
        pattern = {"caffeine": [{"label": "월", "logged": True, "value": 1400.0}]}
        a = fingerprint_analysis_inputs(_nutrient_items(), 20, "middle", pattern)
        b = fingerprint_analysis_inputs(_nutrient_items(), 20, "middle", dict(pattern))
        assert a == b

    def test_different_weekday_pattern_different_fingerprint(self):
        # 회귀 가드: nutrient_items(주간 하루 평균)가 그대로여도, 그 평균을 구성하는
        # 요일별 분포가 바뀌면(예: 기록을 다른 요일로 옮김) 캐시가 새로 타야 한다 —
        # 그렇지 않으면 이제는 틀린 요일을 언급하는 문장이 캐시에 남는다.
        pattern_a = {"caffeine": [{"label": "월", "logged": True, "value": 1400.0}]}
        pattern_b = {"caffeine": [{"label": "화", "logged": True, "value": 1400.0}]}
        a = fingerprint_analysis_inputs(_nutrient_items(), 20, "middle", pattern_a)
        b = fingerprint_analysis_inputs(_nutrient_items(), 20, "middle", pattern_b)
        assert a != b

    def test_weekday_pattern_none_differs_from_present(self):
        pattern = {"caffeine": [{"label": "월", "logged": True, "value": 1400.0}]}
        a = fingerprint_analysis_inputs(_nutrient_items(), 20, "middle", None)
        b = fingerprint_analysis_inputs(_nutrient_items(), 20, "middle", pattern)
        assert a != b
