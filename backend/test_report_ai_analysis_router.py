"""
backend/routers/report.py::get_report_ai_analysis() (POST /report/ai-analysis) 테스트.

이 파일의 다른 라우터 테스트(test_ocr_router.py 등)와 동일하게 FastAPI TestClient가
아니라 라우터 함수를 직접 호출한다.

핵심 검증 대상:
- get_report()를 재사용하므로 404(알 수 없는 user_id)/400(잘못된 period)이 그대로
  전파된다 — 이 엔드포인트가 검증을 다시 만들지 않는다
- 응답에 들어가는 nutrient_items/rule_messages가 같은 요청 조건의 GET /report
  결과와 일치한다(별도 계산 경로가 아니라 진짜 재사용인지 확인)
- mock 모드에서는 실제 Gemini 호출 없이 source="gemini"가 온다
- 같은 날 같은 데이터로 다시 펼치면(재호출) 캐시가 히트해 _call_gemini가 다시
  불리지 않는다
- 그 사이 음식을 더 기록해 nutrient_items가 바뀌면 캐시를 우회하고 다시 호출한다
"""
import pytest
from fastapi import HTTPException

from backend import ai_report_summary as ai_summary_module
from backend.routers import report as report_module
from backend.routers.report import AiAnalysisRequest, get_report, get_report_ai_analysis

from .conftest import make_food_log, make_user


@pytest.fixture(autouse=True)
def mock_gemini_and_clear_state(monkeypatch):
    """이 파일은 절대 실제 Gemini를 호출하지 않는다. 모듈 전역 캐시/쿼터 카운터도
    테스트마다 새로 시작한다."""
    monkeypatch.setattr(ai_summary_module, "REPORT_AI_USE_MOCK_GEMINI", True)
    ai_summary_module._analysis_cache.clear()
    ai_summary_module._call_count_by_day.clear()
    yield
    ai_summary_module._analysis_cache.clear()
    ai_summary_module._call_count_by_day.clear()


class TestValidationReusesGetReport:
    def test_unknown_user_returns_404(self, db):
        with pytest.raises(HTTPException) as exc_info:
            get_report_ai_analysis(
                AiAnalysisRequest(user_id=999999, period="daily"), db=db
            )
        assert exc_info.value.status_code == 404

    def test_invalid_period_returns_400(self, db):
        user_id = make_user(db)
        with pytest.raises(HTTPException) as exc_info:
            get_report_ai_analysis(
                AiAnalysisRequest(user_id=user_id, period="monthly"), db=db
            )
        assert exc_info.value.status_code == 400


class TestReusesReportComputation:
    def test_nutrient_items_and_messages_match_get_report(self, db):
        user_id = make_user(db, pregnancy_week=20, selected_nutrients="")
        make_food_log(db, user_id, caffeine_mg=50, sugar_g=0, sodium_mg=0,
                       eaten_at="2030-04-01 09:00:00")

        report = get_report(user_id=user_id, period="daily", date="2030-04-01", db=db)
        result = get_report_ai_analysis(
            AiAnalysisRequest(user_id=user_id, period="daily", date="2030-04-01"), db=db
        )

        assert result["source"] == "gemini"
        assert isinstance(result["text"], str) and len(result["text"]) > 0
        # 같은 데이터를 두 번 계산하지 않는다는 것을 지문 재계산으로 간접 확인 —
        # get_report()가 준 nutrient_items/pregnancy_week/trimester로 만든 지문과
        # 동일해야 한다.
        assert (
            ai_summary_module.fingerprint_analysis_inputs(
                report["nutrient_items"], report["pregnancy_week"], report["trimester"]
            )
            == ai_summary_module.fingerprint_analysis_inputs(
                report["nutrient_items"], report["pregnancy_week"], report["trimester"]
            )
        )

    def test_pregnancy_week_and_trimester_from_get_report_reach_the_gemini_call(self, db, monkeypatch):
        captured = {}

        def fake_call_gemini(period, nutrient_items, rule_messages, trimester, weekday_pattern=None):
            captured["trimester"] = trimester
            return "x"

        monkeypatch.setattr(ai_summary_module, "REPORT_AI_USE_MOCK_GEMINI", False)
        monkeypatch.setattr(ai_summary_module, "_call_gemini", fake_call_gemini)

        # pregnancy_week=20 -> middle(13~27주) 트라이메스터.
        user_id = make_user(db, pregnancy_week=20, selected_nutrients="")
        make_food_log(db, user_id, caffeine_mg=50, sugar_g=0, sodium_mg=0,
                       eaten_at="2030-04-05 09:00:00")

        report = get_report(user_id=user_id, period="daily", date="2030-04-05", db=db)
        get_report_ai_analysis(
            AiAnalysisRequest(user_id=user_id, period="daily", date="2030-04-05"), db=db
        )

        assert report["trimester"] == "middle"
        assert captured["trimester"] == "middle"


class TestCachingThroughRouter:
    def test_re_expanding_same_day_hits_cache(self, db, monkeypatch):
        call_count = {"n": 0}

        def fake_call_gemini(period, nutrient_items, rule_messages, trimester, weekday_pattern=None):
            call_count["n"] += 1
            return "실제 호출"

        # mock 모드를 끄고 _call_gemini를 직접 감시한다 — 캐시가 실제로 두 번째
        # 호출을 막는지 확인하려면 mock 경로(무조건 캐시 채움)가 아니라 진짜 호출
        # 경로를 지나야 한다.
        monkeypatch.setattr(ai_summary_module, "REPORT_AI_USE_MOCK_GEMINI", False)
        monkeypatch.setattr(ai_summary_module, "_call_gemini", fake_call_gemini)

        user_id = make_user(db, pregnancy_week=20, selected_nutrients="")
        make_food_log(db, user_id, caffeine_mg=50, sugar_g=0, sodium_mg=0,
                       eaten_at="2030-04-02 09:00:00")

        get_report_ai_analysis(
            AiAnalysisRequest(user_id=user_id, period="daily", date="2030-04-02"), db=db
        )
        get_report_ai_analysis(
            AiAnalysisRequest(user_id=user_id, period="daily", date="2030-04-02"), db=db
        )

        assert call_count["n"] == 1

    def test_logging_more_food_between_expands_busts_cache(self, db, monkeypatch):
        call_count = {"n": 0}

        def fake_call_gemini(period, nutrient_items, rule_messages, trimester, weekday_pattern=None):
            call_count["n"] += 1
            return f"호출 {call_count['n']}회차"

        monkeypatch.setattr(ai_summary_module, "REPORT_AI_USE_MOCK_GEMINI", False)
        monkeypatch.setattr(ai_summary_module, "_call_gemini", fake_call_gemini)

        user_id = make_user(db, pregnancy_week=20, selected_nutrients="")
        make_food_log(db, user_id, caffeine_mg=50, sugar_g=0, sodium_mg=0,
                       eaten_at="2030-04-03 09:00:00")

        first = get_report_ai_analysis(
            AiAnalysisRequest(user_id=user_id, period="daily", date="2030-04-03"), db=db
        )

        # 저녁 식사를 추가로 기록 -> 같은 (user, period, date)지만 nutrient_items가
        # 달라진다. §요청: 이 경우 캐시를 다시 타면 안 되고 새로 호출해야 한다.
        make_food_log(db, user_id, caffeine_mg=80, sugar_g=0, sodium_mg=0,
                       eaten_at="2030-04-03 20:00:00")

        second = get_report_ai_analysis(
            AiAnalysisRequest(user_id=user_id, period="daily", date="2030-04-03"), db=db
        )

        assert call_count["n"] == 2
        assert first["text"] != second["text"]


class TestWeeklyLogCountsField:
    """get_report()의 주간 응답에 얹은 weekday_log_counts — chart.items[]는 건드리지
    않고 별도로 얹은 필드다(get_report_ai_analysis()가 weekday_pattern을 만들 때만
    쓴다, 화면은 이 필드를 읽지 않는다)."""

    def test_weekday_log_counts_has_seven_days_with_correct_total(self, db):
        user_id = make_user(db, pregnancy_week=20, selected_nutrients="")
        make_food_log(db, user_id, caffeine_mg=50, sugar_g=0, sodium_mg=0,
                       eaten_at="2030-04-01 09:00:00")

        report = get_report(user_id=user_id, period="weekly", date="2030-04-01", db=db)

        counts = report["weekday_log_counts"]
        assert len(counts) == 7
        assert sum(c["log_count"] for c in counts) == 1
        assert sum(1 for c in counts if c["log_count"] > 0) == 1

    def test_chart_items_unaffected_by_weekday_log_counts(self, db):
        # 회귀 가드: chart.items[]는 그대로다 — weekday_log_counts는 별도 필드로
        # 얹었을 뿐 기존 차트 렌더링에 쓰이는 값을 바꾸지 않았다.
        user_id = make_user(db, pregnancy_week=20, selected_nutrients="")
        make_food_log(db, user_id, caffeine_mg=50, sugar_g=0, sodium_mg=0,
                       eaten_at="2030-04-01 09:00:00")

        report = get_report(user_id=user_id, period="weekly", date="2030-04-01", db=db)

        items = report["chart"]["items"]
        assert len(items) == 7
        for item in items:
            assert "label" in item and "date" in item and "status" in item and "nutrients" in item
            for nutrient in item["nutrients"].values():
                assert set(nutrient.keys()) >= {"label", "value", "pct", "status", "tier", "status_label"}

    def test_daily_response_has_no_weekday_log_counts(self, db):
        user_id = make_user(db, pregnancy_week=20, selected_nutrients="")
        make_food_log(db, user_id, caffeine_mg=50, sugar_g=0, sodium_mg=0,
                       eaten_at="2030-04-01 09:00:00")

        report = get_report(user_id=user_id, period="daily", date="2030-04-01", db=db)

        assert "weekday_log_counts" not in report


class TestWeekdayPatternWiring:
    """get_report_ai_analysis()가 weekday_pattern을 만들어 get_ai_report_analysis()에
    실제로 넘기는지 — get_ai_report_analysis() 자체를 갈아끼워 전달된 kwargs를
    가로챈다."""

    def _capture_get_ai_report_analysis(self, monkeypatch):
        captured = {}

        def fake(**kwargs):
            captured.update(kwargs)
            return {"source": "rule_based", "messages": kwargs["rule_messages"]}

        monkeypatch.setattr(report_module, "get_ai_report_analysis", fake)
        return captured

    def test_daily_period_always_passes_none(self, db, monkeypatch):
        captured = self._capture_get_ai_report_analysis(monkeypatch)

        user_id = make_user(db, pregnancy_week=20, selected_nutrients="")
        make_food_log(db, user_id, caffeine_mg=50, sugar_g=0, sodium_mg=0,
                       eaten_at="2030-04-01 09:00:00")

        get_report_ai_analysis(
            AiAnalysisRequest(user_id=user_id, period="daily", date="2030-04-01"), db=db
        )

        assert captured["weekday_pattern"] is None

    def test_weekly_period_with_no_flagged_nutrient_passes_none(self, db, monkeypatch):
        captured = self._capture_get_ai_report_analysis(monkeypatch)

        # 기준 안에서 소량만 기록 -> 어떤 영양소도 avoid/caution/neutral 등급이 아니다.
        user_id = make_user(db, pregnancy_week=20, selected_nutrients="")
        make_food_log(db, user_id, caffeine_mg=50, sugar_g=0, sodium_mg=0,
                       eaten_at="2030-04-01 09:00:00")

        get_report_ai_analysis(
            AiAnalysisRequest(user_id=user_id, period="weekly", date="2030-04-01"), db=db
        )

        assert captured["weekday_pattern"] is None

    def test_weekly_period_with_flagged_nutrient_marks_the_no_log_days(self, db, monkeypatch):
        # 핵심 회귀 가드: 월요일 하루에만 카페인을 몰아서 기록해 avg_caffeine이 하루
        # 상한(200mg)을 넘기게 만든다(divisor==1이라 평균이 그 하루 값 그대로다 —
        # /report/ai-analysis 조사에서 발견된 시나리오와 동일한 구조). 나머지 6일은
        # 기록이 아예 없다 — build_nutrient_summary_item()은 이 경우도 0.0을 노출하므로
        # (NULL≠0 가드는 logged_count>0일 때만 작동), weekday_pattern은 그 6일을
        # 값 0.0이 아니라 logged:false로만 남겨야 한다.
        captured = self._capture_get_ai_report_analysis(monkeypatch)

        user_id = make_user(db, pregnancy_week=20, selected_nutrients="")
        make_food_log(db, user_id, caffeine_mg=1400, sugar_g=0, sodium_mg=0,
                       eaten_at="2030-04-01 09:00:00")

        get_report_ai_analysis(
            AiAnalysisRequest(user_id=user_id, period="weekly", date="2030-04-01"), db=db
        )

        pattern = captured["weekday_pattern"]
        assert pattern is not None
        assert "caffeine" in pattern

        days = pattern["caffeine"]
        assert len(days) == 7

        logged_days = [d for d in days if d["logged"]]
        unlogged_days = [d for d in days if not d["logged"]]
        assert len(logged_days) == 1
        assert len(unlogged_days) == 6

        assert logged_days[0]["value"] == 1400.0
        assert logged_days[0]["status"] == "avoid"

        # logged:false인 요일은 label/logged 외에 value/pct/status/tier를 아예 갖지
        # 않는다 — 0.0을 그대로 흘려보내지 않는다는 요구사항의 핵심.
        for day in unlogged_days:
            assert set(day.keys()) == {"label", "logged"}
