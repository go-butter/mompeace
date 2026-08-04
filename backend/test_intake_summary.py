"""
backend/routers/intake.py 의 get_intake_summary() (GET /intake/summary/{user_id}) 테스트.

핵심 검증 대상:
- 카페인과 물은 항상 응답에 포함된다
- 선택 영양소는 users.selected_nutrients를 서버에서 직접 조회한다 (엔드포인트에
  선택을 지정하는 파라미터 자체가 없음 — 클라이언트가 우회할 방법이 없다)
- selected_nutrients 미설정 시 DEFAULT_SELECTED_NUTRIENTS로 대체되고, 저장된
  순서를 그대로 유지한다
- selected_nutrients를 명시적으로 빈 값으로 설정하면 카페인+물만 반환된다
  (크래시 없음)
- 영양소 유형별로 simplified_status_label()이 올바른 방향의 어휘를 쓴다:
  ceiling(당류 등)=여유/안전/위험, floor(탄수화물 등)=충분/부족(이진, 완충 구간 없음),
  band(지방)=상황에 따라 두 어휘를 섞어 씀, informational(콜레스테롤)=판정 없음
- 알 수 없는 사용자는 404
"""
from fastapi import HTTPException
import pytest

from backend.routers.intake import get_intake_summary

from .conftest import make_food_log, make_user


class TestIntakeSummaryAlwaysOnFields:
    def test_returns_caffeine_and_water_always_present(self, db):
        user_id = make_user(db, selected_nutrients="")
        make_food_log(db, user_id, caffeine_mg=50)

        result = get_intake_summary(user_id=user_id, db=db)

        assert result["caffeine"]["key"] == "caffeine"
        assert result["caffeine"]["total"] == 50.0
        assert result["water"]["key"] == "water"
        assert result["water"]["unit"] == "mL"

    def test_unknown_user_returns_404(self, db):
        with pytest.raises(HTTPException) as exc_info:
            get_intake_summary(user_id=999999, db=db)
        assert exc_info.value.status_code == 404


class TestIntakeSummarySelectedNutrients:
    def test_unset_falls_back_to_default_and_preserves_order(self, db):
        user_id = make_user(db)  # selected_nutrients 미설정 (NULL)

        result = get_intake_summary(user_id=user_id, db=db)

        assert [item["key"] for item in result["selected_nutrients"]] == [
            "carbohydrate", "sugar", "sodium"
        ]

    def test_explicit_empty_selection_returns_only_caffeine_and_water(self, db):
        user_id = make_user(db, selected_nutrients="")

        result = get_intake_summary(user_id=user_id, db=db)

        assert result["selected_nutrients"] == []
        assert result["caffeine"] is not None
        assert result["water"] is not None

    def test_custom_selection_order_is_preserved_as_stored(self, db):
        user_id = make_user(db, selected_nutrients="fat,carbohydrate,sugar")

        result = get_intake_summary(user_id=user_id, db=db)

        assert [item["key"] for item in result["selected_nutrients"]] == [
            "fat", "carbohydrate", "sugar"
        ]


class TestIntakeSummaryCeilingType:
    def test_sugar_safe_status_and_label(self, db):
        user_id = make_user(db, selected_nutrients="sugar")
        make_food_log(db, user_id, sugar_g=20)  # 20/50 = 0.4 -> safe

        result = get_intake_summary(user_id=user_id, db=db)

        sugar = result["selected_nutrients"][0]
        assert sugar["total"] == 20.0
        assert sugar["status"] == "safe"
        assert sugar["status_label"] == "여유"


class TestIntakeSummaryFloorType:
    def test_carbohydrate_sufficient_status_and_label(self, db):
        user_id = make_user(db, selected_nutrients="carbohydrate")
        make_food_log(db, user_id, carbohydrate_g=200)  # 200/175 >= 1.0 -> sufficient

        result = get_intake_summary(user_id=user_id, db=db)

        carb = result["selected_nutrients"][0]
        assert carb["status"] == "sufficient"
        assert carb["status_label"] == "충분"

    def test_carbohydrate_insufficient_status_uses_binary_label(self, db):
        user_id = make_user(db, selected_nutrients="carbohydrate")
        make_food_log(db, user_id, carbohydrate_g=174)  # 174/175 = 0.994 -> insufficient
        # (get_floor_status()는 이제 완충 구간 없는 이진 판정이라, 목표치 바로 아래인
        # 99.4%도 예전의 "low"가 아니라 곧바로 "insufficient"다.)

        result = get_intake_summary(user_id=user_id, db=db)

        carb = result["selected_nutrients"][0]
        assert carb["status"] == "insufficient"
        assert carb["status_label"] == "부족"


class TestIntakeSummaryBandType:
    """fat은 상한/하한이 모두 있는 밴드형이라 safe/low는 floor 어휘, caution/avoid는
    ceiling 어휘를 섞어 쓴다 (nutrition_constants._BAND_LABELS 참고)."""

    def test_fat_safe(self, db):
        user_id = make_user(db, selected_nutrients="fat")
        make_food_log(db, user_id, calories_kcal=2000, fat_g=40)  # 18% of energy

        result = get_intake_summary(user_id=user_id, db=db)

        fat = result["selected_nutrients"][0]
        assert fat["status"] == "safe"
        assert fat["status_label"] == "여유"

    def test_fat_low_uses_floor_style_label(self, db):
        user_id = make_user(db, selected_nutrients="fat")
        make_food_log(db, user_id, calories_kcal=2000, fat_g=20)  # below 15% floor

        result = get_intake_summary(user_id=user_id, db=db)

        fat = result["selected_nutrients"][0]
        assert fat["status"] == "low"
        assert fat["status_label"] == "부족"

    def test_fat_caution_uses_ceiling_style_label(self, db):
        user_id = make_user(db, selected_nutrients="fat")
        make_food_log(db, user_id, calories_kcal=2000, fat_g=55)  # approaching 30% ceiling

        result = get_intake_summary(user_id=user_id, db=db)

        fat = result["selected_nutrients"][0]
        assert fat["status"] == "caution"
        assert fat["status_label"] == "안전"

    def test_fat_avoid(self, db):
        user_id = make_user(db, selected_nutrients="fat")
        make_food_log(db, user_id, calories_kcal=2000, fat_g=90)  # over 30% ceiling

        result = get_intake_summary(user_id=user_id, db=db)

        fat = result["selected_nutrients"][0]
        assert fat["status"] == "avoid"
        assert fat["status_label"] == "위험"


class TestIntakeSummaryAgeBracket:
    """energy/protein 목표치(floor limit)는 users.age_bracket에 따라 baseline이 달라진다
    (nutrition_constants.BASE_ENERGY_KCAL / BASE_PROTEIN_G)."""

    def test_unset_age_bracket_falls_back_to_19_29_baseline(self, db):
        user_id = make_user(db, selected_nutrients="energy,protein", pregnancy_week=8)  # early: +0/+0

        result = get_intake_summary(user_id=user_id, db=db)

        energy, protein = result["selected_nutrients"]
        assert energy["limit"] == 2000.0
        assert protein["limit"] == 55.0

    def test_30_49_bracket_uses_lower_baseline(self, db):
        user_id = make_user(
            db, selected_nutrients="energy,protein", pregnancy_week=8, age_bracket="30-49"
        )  # early: +0/+0

        result = get_intake_summary(user_id=user_id, db=db)

        energy, protein = result["selected_nutrients"]
        assert energy["limit"] == 1900.0
        assert protein["limit"] == 50.0


class TestIntakeSummaryInformationalType:
    def test_cholesterol_known_value_has_no_status_label(self, db):
        user_id = make_user(db, selected_nutrients="cholesterol")
        make_food_log(db, user_id, cholesterol_mg=45)

        result = get_intake_summary(user_id=user_id, db=db)

        cholesterol = result["selected_nutrients"][0]
        assert cholesterol["total"] == 45.0
        assert cholesterol["status"] == "info"
        assert cholesterol["status_label"] is None
        assert cholesterol["limit"] is None
        assert cholesterol["percent"] is None

    def test_cholesterol_unknown_value_shows_no_info_label(self, db):
        user_id = make_user(db, selected_nutrients="cholesterol")
        make_food_log(db, user_id, calories_kcal=2000)  # cholesterol_mg 미기록 (NULL)

        result = get_intake_summary(user_id=user_id, db=db)

        cholesterol = result["selected_nutrients"][0]
        assert cholesterol["status"] == "unknown"
        assert cholesterol["status_label"] == "정보없음"
