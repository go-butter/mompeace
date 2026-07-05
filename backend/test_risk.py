"""
evaluate_food_risk()의 sugar/sodium NULL(정보 없음) 처리 검증.

핵심 검증 대상:
- sugar_g/sodium_mg가 None이면 0으로 뭉개지지 않고 그대로 None으로 유지되며
  status가 "unknown"("정보 없음")이 되어야 한다 (caffeine과 동일한 동작)
- sugar_g=0처럼 실제로 확인된 0 값은 여전히 "safe"로 판정되어야 한다
  (None과 0을 구분하지 못하는 회귀가 없어야 한다)
- 일부 영양소가 unknown이어도 다른 영양소의 avoid 판정은 overall_status에 그대로 반영된다
"""
from backend.risk import evaluate_food_risk

# pregnancy_week=20 → trimester "middle" (sugar safe_max=10/caution_max=30,
# sodium safe_max=500/caution_max=1500, caffeine safe_max=70/caution_max=200)
PREGNANCY_WEEK_MIDDLE = 20


class TestSugarSodiumUnknownHandling:
    def test_sugar_none_is_preserved_and_marked_unknown(self):
        food_data = {"food_name": "정보 없는 음식", "caffeine_mg": 0, "sugar_g": None, "sodium_mg": 5}

        result = evaluate_food_risk(food_data, PREGNANCY_WEEK_MIDDLE)

        assert result["details"]["sugar"]["value"] is None
        assert result["details"]["sugar"]["status"] == "unknown"
        assert result["details"]["sugar"]["label"] == "정보 없음"

    def test_sodium_none_is_preserved_and_marked_unknown(self):
        food_data = {"food_name": "정보 없는 음식", "caffeine_mg": 0, "sugar_g": 5, "sodium_mg": None}

        result = evaluate_food_risk(food_data, PREGNANCY_WEEK_MIDDLE)

        assert result["details"]["sodium"]["value"] is None
        assert result["details"]["sodium"]["status"] == "unknown"
        assert result["details"]["sodium"]["label"] == "정보 없음"

    def test_confirmed_zero_sugar_is_still_safe_not_unknown(self):
        """None과 0을 구분하지 못하는 회귀가 없어야 한다."""
        food_data = {"food_name": "무당 음식", "caffeine_mg": 0, "sugar_g": 0, "sodium_mg": 0}

        result = evaluate_food_risk(food_data, PREGNANCY_WEEK_MIDDLE)

        assert result["details"]["sugar"]["value"] == 0
        assert result["details"]["sugar"]["status"] == "safe"
        assert result["details"]["sodium"]["value"] == 0
        assert result["details"]["sodium"]["status"] == "safe"

    def test_overall_status_ignores_unknown_but_reflects_other_avoid(self):
        food_data = {
            "food_name": "카페인 과다, 나머지 정보 없음",
            "caffeine_mg": 250,  # middle caution_max=200 초과 → avoid
            "sugar_g": None,
            "sodium_mg": None,
        }

        result = evaluate_food_risk(food_data, PREGNANCY_WEEK_MIDDLE)

        assert result["details"]["sugar"]["status"] == "unknown"
        assert result["details"]["sodium"]["status"] == "unknown"
        assert result["overall_status"] == "avoid"
