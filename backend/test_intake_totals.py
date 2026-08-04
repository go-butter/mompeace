"""
backend/intake_totals.py 의 get_trimester_limits() / resolve_user_nutrition_context() 테스트.

핵심 검증 대상:
- age_bracket("19-29"/"30-49")에 따라 energy_kcal/protein_g baseline이 달라진다
- age_bracket 미지정 시 기본값("19-29")과 동일한 결과를 낸다
- resolve_user_nutrition_context()는 pregnancy_week/age_bracket 미설정 사용자를
  각각 20주/"19-29"로 대체한다
"""
from backend.intake_totals import get_trimester_limits, resolve_user_nutrition_context


class TestGetTrimesterLimitsAgeBracket:
    def test_defaults_to_19_29_baseline_when_age_bracket_omitted(self):
        _, limits = get_trimester_limits(8)  # early: +0/+0

        assert limits["energy_kcal"] == 2000.0
        assert limits["protein_g"] == 55.0

    def test_19_29_bracket_matches_default(self):
        _, limits = get_trimester_limits(8, "19-29")

        assert limits["energy_kcal"] == 2000.0
        assert limits["protein_g"] == 55.0

    def test_30_49_bracket_uses_lower_baseline(self):
        _, limits = get_trimester_limits(8, "30-49")

        assert limits["energy_kcal"] == 1900.0
        assert limits["protein_g"] == 50.0

    def test_30_49_bracket_still_applies_trimester_additions(self):
        # late(28주 이상): energy +450, protein +30
        _, limits = get_trimester_limits(30, "30-49")

        assert limits["energy_kcal"] == 1900.0 + 450.0
        assert limits["protein_g"] == 50.0 + 30.0


class TestResolveUserNutritionContext:
    def test_falls_back_to_week_20_and_bracket_19_29_when_unset(self):
        week, age_bracket = resolve_user_nutrition_context({})

        assert week == 20
        assert age_bracket == "19-29"

    def test_reads_age_bracket_from_user_row(self):
        week, age_bracket = resolve_user_nutrition_context({"age_bracket": "30-49"})

        assert age_bracket == "30-49"

    def test_reads_pregnancy_week_from_user_row(self):
        week, _ = resolve_user_nutrition_context({"pregnancy_week": 25})

        assert week == 25
