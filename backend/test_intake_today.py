"""
backend/main.py 의 get_today_intake() 테스트.

핵심 검증 대상:
- 응답에 pregnancy_day, due_date, days_until_due 필드가 포함된다
- due_date가 미래로 설정되어 있으면 days_until_due는 양의 정수다
- due_date가 없으면 days_until_due는 None이다
- fat/saturated_fat/trans_fat_status: energy_total(kcal) * ratio를 그램으로
  환산(KCAL_PER_GRAM_FAT)하지 않고 그램 값과 직접 비교하면 상한 초과가 "avoid"가
  아니라 "low"로 잘못 판정된다 — 이 회귀를 가드한다
"""
from backend.routers.intake import get_today_intake

from .conftest import make_food_log, make_user


class TestGetTodayIntakeStatusLabelVocabulary:
    """Food Diary(get_today_intake)의 status_label은 홈 화면(/intake/summary)과 동일한
    simplified_status_label() 어휘를 재사용해야 한다 — 같은 상태 코드가 화면마다 다른
    단어로 보이면 안전 앱에서 사용자 혼란을 유발한다."""

    def test_ceiling_caution_uses_shared_vocabulary_not_old_local_wording(self, db):
        # 150/200 = 0.75 -> caution. 예전 로컬 status_label()은 "주의"를 반환했지만,
        # simplified_status_label("ceiling", "caution")은 "안전"이다.
        user_id = make_user(db)
        make_food_log(db, user_id, caffeine_mg=150)

        result = get_today_intake(user_id=user_id, db=db)

        assert result["status"]["caffeine_status"] == "caution"
        assert result["status_label"]["caffeine"] == "안전"

    def test_band_caution_uses_ceiling_style_wording(self, db):
        # fat_status는 get_fat_status()(band)의 결과이며, caution 구간은 ceiling과
        # 동일한 어휘("안전")를 쓴다 (_BAND_LABELS 참고).
        user_id = make_user(db)
        make_food_log(db, user_id, calories_kcal=2000, fat_g=55)  # ceiling 쪽 caution 구간

        result = get_today_intake(user_id=user_id, db=db)

        assert result["status"]["fat_status"] == "caution"
        assert result["status_label"]["fat"] == "안전"

    def test_iron_band_uses_same_vocabulary_as_fat(self, db):
        # 철분은 콜레스테롤을 대체한 판정형 영양소로, fat과 동일한 band 어휘를 쓴다.
        # 40mg: 권장량(24mg) 이상이지만 상한(45mg)의 70%(31.5mg)를 넘어 caution 구간.
        user_id = make_user(db)
        make_food_log(db, user_id, iron_mg=40)

        result = get_today_intake(user_id=user_id, db=db)

        assert result["status"]["iron_status"] == "caution"
        assert result["status_label"]["iron"] == "안전"


class TestGetTodayIntakeIronStatus:
    def test_iron_below_recommended_is_low(self, db):
        # 10mg < 권장량(24mg) -> low(부족)
        user_id = make_user(db)
        make_food_log(db, user_id, iron_mg=10)

        result = get_today_intake(user_id=user_id, db=db)

        assert result["status"]["iron_status"] == "low"
        assert result["status_label"]["iron"] == "부족"

    def test_iron_between_recommended_and_caution_threshold_is_safe(self, db):
        # 30mg: 권장량(24mg) 이상이면서 상한(45mg)의 70%(31.5mg) 미만 -> safe(여유)
        user_id = make_user(db)
        make_food_log(db, user_id, iron_mg=30)

        result = get_today_intake(user_id=user_id, db=db)

        assert result["status"]["iron_status"] == "safe"
        assert result["status_label"]["iron"] == "여유"

    def test_iron_above_upper_limit_is_avoid(self, db):
        # 50mg > 상한(45mg) -> avoid(위험)
        user_id = make_user(db)
        make_food_log(db, user_id, iron_mg=50)

        result = get_today_intake(user_id=user_id, db=db)

        assert result["status"]["iron_status"] == "avoid"
        assert result["status_label"]["iron"] == "위험"


class TestGetTodayIntakeDueDate:
    def test_includes_due_date_fields_when_due_date_set(self, db):
        user_id = make_user(db, due_date="2099-01-01")

        result = get_today_intake(user_id=user_id, db=db)

        assert "pregnancy_day" in result
        assert "due_date" in result
        assert "days_until_due" in result
        assert result["due_date"] == "2099-01-01"
        assert isinstance(result["days_until_due"], int)
        assert result["days_until_due"] > 0

    def test_days_until_due_is_none_when_due_date_not_set(self, db):
        user_id = make_user(db, due_date=None)

        result = get_today_intake(user_id=user_id, db=db)

        assert result["due_date"] is None
        assert result["days_until_due"] is None


class TestGetTodayIntakeFatStatus:
    def test_fat_status_compares_grams_against_gram_limit(self, db):
        # 90g 지방 / 2000kcal = 총 에너지의 40.5%, 상한(30%) 그램 환산 66.7g을 초과 -> avoid.
        # 환산 없이 비교하면 90/(2000*0.30)=0.15로 "safe"가 되어버린다.
        user_id = make_user(db)
        make_food_log(db, user_id, calories_kcal=2000, fat_g=90)

        result = get_today_intake(user_id=user_id, db=db)

        assert result["status"]["fat_status"] == "avoid"

    def test_saturated_fat_status_compares_grams_against_gram_limit(self, db):
        # 20g 포화지방 / 2000kcal: 상한(7%) 그램 환산 15.56g을 초과 -> avoid.
        user_id = make_user(db)
        make_food_log(db, user_id, calories_kcal=2000, saturated_fat_g=20)

        result = get_today_intake(user_id=user_id, db=db)

        assert result["status"]["saturated_fat_status"] == "avoid"

    def test_trans_fat_status_compares_grams_against_gram_limit(self, db):
        # 5g 트랜스지방 / 2000kcal: 상한(1%) 그램 환산 2.22g을 초과 -> avoid.
        user_id = make_user(db)
        make_food_log(db, user_id, calories_kcal=2000, trans_fat_g=5)

        result = get_today_intake(user_id=user_id, db=db)

        assert result["status"]["trans_fat_status"] == "avoid"
