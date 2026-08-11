"""
backend/pregnancy_nutrition_kb.py 테스트.

핵심 검증 대상:
- 이 파일의 모든 문자열 상수에 숫자가 전혀 없다 — 기준치는 nutrition_constants.py의
  유일한 소유물이어야 한다는 요구사항의 회귀 가드. 특히 카페인: 임신_관련_정보.md의
  "300mg"(식약처 2011) 값이 이 파일에 절대 들어가면 안 된다(이 앱은 ACOG/WHO 200mg을
  쓰기로 이미 결정했다, nutrition_constants.py 참고).
- build_kb_excerpts()는 넘겨받은 nutrient_keys에 실제로 있는 영양소의 문단만 고른다
  (없는 영양소의 조언을 끼워 넣지 않는다)
- iron이 있을 때만 철분 흡수 문단이, caffeine이 있을 때만 카페인 문단이, sodium이
  있을 때만 나트륨 문단이 붙는다
- trimester 문단은 항상 요청한 시기의 것만 붙는다
- calcium 항목은 KB 데이터에는 남아 있지만(요청에 따른 의도적 보존) build_kb_excerpts는
  절대 고르지 않는다 — NUTRIENT_SUMMARY_FIELDS에 없는 미판정 영양소이기 때문이다
"""
import re

from backend.pregnancy_nutrition_kb import (
    CAFFEINE_ABSORPTION_NOTE,
    IRON_ABSORPTION_NOTE,
    NUTRIENT_FOOD_SOURCES,
    SODIUM_REDUCTION_TIPS,
    TRIMESTER_NOTES,
    build_kb_excerpts,
)

_DIGIT_RE = re.compile(r"\d")


class TestNoNumbersAnywhereInKb:
    def test_no_digit_in_any_food_source_string(self):
        for key, text in NUTRIENT_FOOD_SOURCES.items():
            assert not _DIGIT_RE.search(text), f"{key} 급원식품 문구에 숫자가 있으면 안 된다: {text}"

    def test_no_digit_in_absorption_or_sodium_notes(self):
        for text in (IRON_ABSORPTION_NOTE, CAFFEINE_ABSORPTION_NOTE, SODIUM_REDUCTION_TIPS):
            assert not _DIGIT_RE.search(text), f"숫자가 있으면 안 된다: {text}"

    def test_no_digit_in_any_trimester_note(self):
        for trimester, text in TRIMESTER_NOTES.items():
            assert not _DIGIT_RE.search(text), f"{trimester} 시기 문구에 숫자가 있으면 안 된다: {text}"

    def test_caffeine_note_never_mentions_the_300mg_figure(self):
        # 가장 직접적인 회귀 가드 — 식약처 2011 자료의 300이라는 숫자 자체가
        # 문자열에 등장하지 않아야 한다(단위 없이 "300"이 섞여 들어가는 것도 방지).
        assert "300" not in CAFFEINE_ABSORPTION_NOTE
        assert "200" not in CAFFEINE_ABSORPTION_NOTE


class TestBuildKbExcerptsSelection:
    def test_only_present_nutrients_get_food_source_excerpts(self):
        excerpts = build_kb_excerpts(["caffeine", "iron"], "middle")
        joined = " ".join(excerpts)
        assert "[iron 급원식품]" in joined
        assert "[protein 급원식품]" not in joined
        assert "[carbohydrate 급원식품]" not in joined

    def test_iron_absorption_note_only_when_iron_present(self):
        with_iron = " ".join(build_kb_excerpts(["caffeine", "iron"], "middle"))
        without_iron = " ".join(build_kb_excerpts(["caffeine", "protein"], "middle"))
        assert "[철분 흡수]" in with_iron
        assert "[철분 흡수]" not in without_iron

    def test_caffeine_note_only_when_caffeine_present(self):
        # nutrient_items는 항상 caffeine을 포함하지만(chart_keys 설계), 함수 자체의
        # 선택 로직만 독립적으로 검증한다.
        with_caffeine = " ".join(build_kb_excerpts(["caffeine"], "middle"))
        without_caffeine = " ".join(build_kb_excerpts(["protein"], "middle"))
        assert "[카페인 주의]" in with_caffeine
        assert "[카페인 주의]" not in without_caffeine

    def test_sodium_tips_only_when_sodium_present(self):
        with_sodium = " ".join(build_kb_excerpts(["caffeine", "sodium"], "middle"))
        without_sodium = " ".join(build_kb_excerpts(["caffeine", "protein"], "middle"))
        assert "[나트륨 줄이기]" in with_sodium
        assert "[나트륨 줄이기]" not in without_sodium

    def test_trimester_note_matches_requested_stage_only(self):
        early = " ".join(build_kb_excerpts(["caffeine"], "early"))
        middle = " ".join(build_kb_excerpts(["caffeine"], "middle"))
        late = " ".join(build_kb_excerpts(["caffeine"], "late"))

        assert "입덧" in early and "빈혈" not in early and "변비" not in early
        assert "빈혈" in middle and "입덧" not in middle and "변비" not in middle
        assert "변비" in late and "입덧" not in late and "빈혈" not in late

    def test_calcium_entry_is_kept_in_kb_data_though_unreachable_in_practice(self):
        # 요청에 따라 calcium 항목은 KB 데이터에 남겨둔다(NUTRIENT_FOOD_SOURCES에 존재).
        # build_kb_excerpts() 자체는 범용 딕셔너리 조회라 "calcium"을 넘기면 선택은
        # 되지만, 실제로는 이 함수가 nutrient_items에서 뽑은 키로만 호출되고
        # nutrient_items는 NUTRIENT_SUMMARY_FIELDS가 정의한 8개 판정 대상 영양소
        # 밖으로 나가지 않으므로("calcium"이 그 안에 없다) 실전에서는 절대 선택될 수
        # 없다 — 이 죽은 코드 여부는 test_ai_report_summary.py의
        # test_reference_notes_exclude_sodium_tips_when_sodium_not_present류 테스트가
        # nutrient_items 기반 호출 경로로 간접 보장한다.
        assert "calcium" in NUTRIENT_FOOD_SOURCES
        excerpts = build_kb_excerpts(["calcium"], "middle")
        assert any("calcium" in e for e in excerpts)
