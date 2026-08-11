"""
backend/routers/report.py 의 get_report() 테스트 (기존 커버리지 없음).

핵심 검증 대상:
- 400/404 기본 검증
- daily: 4개 시간대(새벽/오전/오후/저녁) 버킷팅, 항목별 caffeine_pct/sugar_pct/sodium_pct,
  항목별/전체 status가 unknown(NULL 존재)을 safe/caution/avoid와 구분해서 반영
- weekly: 요일별 버킷팅, 항목별/전체 status, daily_average는 항상 7일 기준
- weekly comparison(지난주 대비): 퍼센트포인트 차이로 계산되고, 지난주 기록이 전혀 없으면 null
- "기록 자체가 없음"과 "기록은 있지만 값이 NULL(unknown)"을 구분하는 회귀 가드
- food_log.fat_g/iron_mg에 실제 값이 있으면 fat_status/iron_status가
  더 이상 항상 "unknown"이 아니라 실제 값 기반으로 계산된다 (기존에는 두 컬럼이
  한 번도 채워진 적이 없어 이 경로가 커버되지 않았음)
"""
from datetime import date

import pytest
from fastapi import HTTPException

from backend.routers.report import _aggregate_day_slots, _aggregate_week, _chart_item_status, get_report

from backend.nutrition_constants import DAILY_WATER_TARGET_ML

from .conftest import make_food_log, make_user, make_water_log


class TestGetReportBasicValidation:
    def test_invalid_period_returns_400(self, db):
        user_id = make_user(db)
        with pytest.raises(HTTPException) as exc_info:
            get_report(user_id=user_id, period="monthly", db=db)
        assert exc_info.value.status_code == 400

    def test_invalid_date_format_returns_400(self, db):
        user_id = make_user(db)
        with pytest.raises(HTTPException) as exc_info:
            get_report(user_id=user_id, period="daily", date="not-a-date", db=db)
        assert exc_info.value.status_code == 400

    def test_unknown_user_returns_404(self, db):
        with pytest.raises(HTTPException) as exc_info:
            get_report(user_id=999999, period="daily", db=db)
        assert exc_info.value.status_code == 404


class TestGetReportDaily:
    def _item(self, result, label):
        return next(i for i in result["chart"]["items"] if i["label"] == label)

    def test_basic_totals_and_slot_bucketing(self, db):
        user_id = make_user(db, pregnancy_week=20)
        make_food_log(db, user_id, caffeine_mg=20, sugar_g=0, sodium_mg=0,
                       eaten_at="2030-01-10 03:00:00")   # 새벽
        make_food_log(db, user_id, caffeine_mg=30, sugar_g=0, sodium_mg=0,
                       eaten_at="2030-01-10 08:00:00")   # 오전
        make_food_log(db, user_id, caffeine_mg=40, sugar_g=0, sodium_mg=0,
                       eaten_at="2030-01-10 15:00:00")   # 오후
        make_food_log(db, user_id, caffeine_mg=50, sugar_g=0, sodium_mg=0,
                       eaten_at="2030-01-10 20:00:00")   # 저녁

        result = get_report(user_id=user_id, period="daily", date="2030-01-10", db=db)

        assert result["totals"]["caffeine_mg"] == 140.0
        assert result["percentages"]["caffeine"] == 70.0  # 140/200
        assert self._item(result, "새벽")["nutrients"]["caffeine"]["value"] == 20.0
        assert self._item(result, "새벽")["nutrients"]["caffeine"]["pct"] == 10.0  # 20/200
        assert self._item(result, "오전")["nutrients"]["caffeine"]["value"] == 30.0
        assert self._item(result, "오후")["nutrients"]["caffeine"]["value"] == 40.0
        assert self._item(result, "저녁")["nutrients"]["caffeine"]["value"] == 50.0

    def test_known_sugar_value_used_even_when_another_food_has_null_sugar(self, db):
        # 회귀 가드: 같은 슬롯/하루에 확인된 값이 하나라도 있으면, 다른 음식의 NULL이
        # 그 값을 "정보없음"으로 뭉개버리면 안 된다 (known_count > 0이므로 실제 값 기준 판정).
        user_id = make_user(db, pregnancy_week=20)
        make_food_log(db, user_id, caffeine_mg=0, sugar_g=8, sodium_mg=0,
                       eaten_at="2030-01-11 02:00:00")   # 새벽, 확인된 값
        make_food_log(db, user_id, caffeine_mg=0, sugar_g=None, sodium_mg=0,
                       eaten_at="2030-01-11 04:00:00")   # 새벽, unknown

        result = get_report(user_id=user_id, period="daily", date="2030-01-11", db=db)

        dawn = self._item(result, "새벽")
        assert dawn["nutrients"]["sugar"]["value"] == 8.0    # unknown은 0으로 뭉개지지 않고 부분합 유지
        assert dawn["nutrients"]["sugar"]["status"] == "safe"  # 확인된 값(8g)이 있으므로 더 이상 unknown이 아님
        assert result["status"]["sugar_status"] == "safe"  # 전체(top-level)에도 반영

    def test_empty_slot_is_safe_not_unknown(self, db):
        # 시간대에 로그가 아예 없는 것과 unknown 값이 있는 것은 다른 상태여야 한다.
        # 탄수화물은 기본 선택 영양소(DEFAULT_SELECTED_NUTRIENTS)라 함께 집계되고
        # floor형이라 0은 "정보없음"이 아니라 "부족"(insufficient)이다 — 하지만 버킷
        # 롤업 status는 floor형을 제외하므로(_chart_item_status), 이 "부족"이 항목
        # 전체를 caution으로 끌어내리지 않는다(§7: 부족은 경고가 아니다).
        user_id = make_user(db, pregnancy_week=20)
        make_food_log(db, user_id, caffeine_mg=10, sugar_g=5, sodium_mg=50,
                       eaten_at="2030-01-12 03:00:00")   # 새벽만 기록

        result = get_report(user_id=user_id, period="daily", date="2030-01-12", db=db)

        evening = self._item(result, "저녁")
        assert evening["nutrients"]["caffeine"]["value"] == 0.0
        assert evening["nutrients"]["caffeine"]["status"] == "safe"
        assert evening["nutrients"]["sugar"]["status"] == "safe"
        assert evening["nutrients"]["sodium"]["status"] == "safe"
        assert evening["nutrients"]["carbohydrate"]["status"] == "insufficient"
        assert evening["nutrients"]["carbohydrate"]["tier"] == "neutral"
        assert evening["status"] == "safe"


class TestGetReportFatIron:
    def test_fat_and_iron_totals_and_status_from_real_values(self, db):
        user_id = make_user(db, pregnancy_week=20)
        # 40g 지방 / 2000kcal = 총 에너지의 18% -> 15~30% 밴드 안쪽 (safe)
        # 30mg 철분: 권장량(24mg) 이상, 상한(45mg)의 70%(31.5mg) 미만 -> safe
        make_food_log(db, user_id, caffeine_mg=0, sugar_g=0, sodium_mg=0,
                       calories_kcal=2000, fat_g=40, iron_mg=30,
                       eaten_at="2030-01-15 09:00:00")

        result = get_report(user_id=user_id, period="daily", date="2030-01-15", db=db)

        assert result["totals"]["fat_g"] == 40.0
        assert result["totals"]["iron_mg"] == 30.0
        assert result["status"]["fat_status"] == "safe"
        assert result["status"]["iron_status"] == "safe"

    def test_weekly_fat_status_uses_daily_average_not_period_sum(self, db):
        # 회귀 가드(T7 Finding A): 지방의 분모가 "하루 에너지 목표"로 바뀌면서
        # 분자도 반드시 일평균이어야 한다. 기간 합계를 그대로 쓰면 7일치 지방
        # (7 * 40 = 280g)을 하루치 상한(78g)과 비교하게 되어, 지극히 정상적인
        # 한 주가 영구적으로 "avoid"로 표시된다.
        #
        # 예전(누적 에너지 분모)에는 합계/합계와 평균/평균이 수학적으로 같아서
        # 나누지 않아도 괜찮았지만, 분모가 고정되는 순간 그 등가성이 깨진다.
        user_id = make_user(db, pregnancy_week=20)
        # 2030-01-14(월) ~ 01-20(일) 주. 매일 2000kcal / 지방 40g = 하루 18%로 안전한 주.
        for day in range(14, 21):
            make_food_log(db, user_id, caffeine_mg=0, sugar_g=0, sodium_mg=0,
                           calories_kcal=2000, fat_g=40,
                           eaten_at=f"2030-01-{day} 09:00:00")

        result = get_report(user_id=user_id, period="weekly", date="2030-01-15", db=db)

        assert result["totals"]["fat_g"] == 280.0  # 기간 합계 노출은 기존 그대로
        # 판정은 일평균(280/7=40g) 대 하루 상한(78g) — 합계(280g)를 쓰면 avoid가 된다.
        assert result["status"]["fat_status"] == "safe"

    def test_fat_status_compares_grams_against_gram_limit_not_raw_kcal_number(self, db):
        # 회귀 가드: energy_total(kcal) * ratio는 kcal 단위이므로, 그램 단위인
        # total_fat과 비교하려면 KCAL_PER_GRAM_FAT(9kcal/g)로 나눠야 한다. 이 환산이
        # 없으면 90g(총 에너지의 40.5%, 상한 30%를 크게 초과)이 "avoid"가 아니라
        # "low"로(=상한 초과를 부족으로) 잘못 판정된다.
        user_id = make_user(db, pregnancy_week=20)
        make_food_log(db, user_id, caffeine_mg=0, sugar_g=0, sodium_mg=0,
                       calories_kcal=2000, fat_g=90,
                       eaten_at="2030-01-16 09:00:00")

        result = get_report(user_id=user_id, period="daily", date="2030-01-16", db=db)

        assert result["status"]["fat_status"] == "avoid"

    def test_saturated_fat_status_compares_grams_against_gram_limit(self, db):
        # 20g 포화지방 / 2000kcal: 상한(7%) 그램 환산 15.56g을 초과 -> avoid여야 한다.
        # 환산 없이 비교하면 20/(2000*0.07)=0.14로 "safe"가 되어버린다.
        user_id = make_user(db, pregnancy_week=20)
        make_food_log(db, user_id, caffeine_mg=0, sugar_g=0, sodium_mg=0,
                       calories_kcal=2000, saturated_fat_g=20,
                       eaten_at="2030-01-17 09:00:00")

        result = get_report(user_id=user_id, period="daily", date="2030-01-17", db=db)

        assert result["status"]["saturated_fat_status"] == "avoid"

    def test_trans_fat_status_compares_grams_against_gram_limit(self, db):
        # 5g 트랜스지방 / 2000kcal: 상한(1%) 그램 환산 2.22g을 초과 -> avoid여야 한다.
        # 환산 없이 비교하면 5/(2000*0.01)=0.25로 "safe"가 되어버린다.
        user_id = make_user(db, pregnancy_week=20)
        make_food_log(db, user_id, caffeine_mg=0, sugar_g=0, sodium_mg=0,
                       calories_kcal=2000, trans_fat_g=5,
                       eaten_at="2030-01-18 09:00:00")

        result = get_report(user_id=user_id, period="daily", date="2030-01-18", db=db)

        assert result["status"]["trans_fat_status"] == "avoid"


class TestGetReportWeekly:
    def _item(self, result, label):
        return next(i for i in result["chart"]["items"] if i["label"] == label)

    def test_basic_totals_and_weekday_bucketing(self, db):
        user_id = make_user(db, pregnancy_week=20)
        make_food_log(db, user_id, caffeine_mg=100, sugar_g=20, sodium_mg=500,
                       eaten_at="2030-01-07 09:00:00")   # 월요일
        make_food_log(db, user_id, caffeine_mg=50, sugar_g=10, sodium_mg=300,
                       eaten_at="2030-01-08 09:00:00")   # 화요일

        result = get_report(user_id=user_id, period="weekly", date="2030-01-07", db=db)

        assert result["date_range"]["start"] == "2030-01-07"
        assert result["date_range"]["end"] == "2030-01-13"
        assert result["totals"]["caffeine_mg"] == 150.0
        assert self._item(result, "월")["nutrients"]["caffeine"]["value"] == 100.0
        assert self._item(result, "화")["nutrients"]["caffeine"]["value"] == 50.0
        assert self._item(result, "수")["nutrients"]["caffeine"]["value"] == 0.0

    def test_unknown_status_propagates_top_level_and_per_item(self, db):
        user_id = make_user(db, pregnancy_week=20)
        make_food_log(db, user_id, caffeine_mg=None, sugar_g=10, sodium_mg=300,
                       eaten_at="2030-01-08 09:00:00")   # 화요일, 카페인 unknown

        result = get_report(user_id=user_id, period="weekly", date="2030-01-07", db=db)

        tuesday = self._item(result, "화")
        assert tuesday["nutrients"]["caffeine"]["status"] == "unknown"
        assert result["status"]["caffeine_status"] == "unknown"
        assert tuesday["nutrients"]["caffeine"]["tier"] == "unknown"
        assert result["status"]["caffeine_tier"] == "unknown"

    def test_daily_average_divides_by_days_with_data(self, db):
        # 7일 중 3일(월/수/금)에만 기록이 있으면 daily_average는 3으로 나눈다 (7로 나누지 않는다)
        user_id = make_user(db, pregnancy_week=20)
        make_food_log(db, user_id, caffeine_mg=210, sugar_g=0, sodium_mg=0,
                       eaten_at="2030-01-07 09:00:00")  # 월
        make_food_log(db, user_id, caffeine_mg=210, sugar_g=0, sodium_mg=0,
                       eaten_at="2030-01-09 09:00:00")  # 수
        make_food_log(db, user_id, caffeine_mg=210, sugar_g=0, sodium_mg=0,
                       eaten_at="2030-01-11 09:00:00")  # 금

        result = get_report(user_id=user_id, period="weekly", date="2030-01-07", db=db)

        assert result["daily_average"]["caffeine_mg"] == 210.0  # 630/3, not 630/7

    def test_daily_average_is_zero_not_error_when_week_is_entirely_empty(self, db):
        user_id = make_user(db, pregnancy_week=20)

        result = get_report(user_id=user_id, period="weekly", date="2030-01-07", db=db)

        assert result["daily_average"] == {
            "caffeine_mg": 0.0, "sugar_g": 0.0, "sodium_mg": 0.0,
            "energy_kcal": 0.0, "carbohydrate_g": 0.0, "protein_g": 0.0,
            "water_ml": 0.0,
        }

    def test_comparison_uses_days_with_data_on_previous_week_too(self, db):
        user_id = make_user(db, pregnancy_week=20)
        # 이번 주: 7일 모두 기록, 하루 평균 카페인 100mg = 50%
        for i in range(7):
            day = 14 + i
            make_food_log(db, user_id, caffeine_mg=100, sugar_g=0, sodium_mg=0,
                           eaten_at=f"2030-01-{day:02d} 09:00:00")
        # 지난 주: 2일(월/화)에만 기록, 각 50mg -> 기록 있는 날 기준 평균 50mg = 25%
        make_food_log(db, user_id, caffeine_mg=50, sugar_g=0, sodium_mg=0,
                       eaten_at="2030-01-07 09:00:00")
        make_food_log(db, user_id, caffeine_mg=50, sugar_g=0, sodium_mg=0,
                       eaten_at="2030-01-08 09:00:00")

        result = get_report(user_id=user_id, period="weekly", date="2030-01-14", db=db)

        # 지난 주 평균이 100/7(=14.3%)이 아니라 50/2(=25%)로 계산되어야 delta가 25.0이 된다
        assert result["comparison"]["caffeine_vs_previous_pct"] == 25.0  # 50% - 25%

    def test_comparison_percentage_point_delta(self, db):
        user_id = make_user(db, pregnancy_week=20)
        # 이번 주(2030-01-14~01-20): 하루 평균 카페인 100mg = 50%
        for i in range(7):
            day = 14 + i
            make_food_log(db, user_id, caffeine_mg=100, sugar_g=0, sodium_mg=0,
                           eaten_at=f"2030-01-{day:02d} 09:00:00")
        # 지난 주(2030-01-07~01-13): 하루 평균 카페인 50mg = 25%
        for i in range(7):
            day = 7 + i
            make_food_log(db, user_id, caffeine_mg=50, sugar_g=0, sodium_mg=0,
                           eaten_at=f"2030-01-{day:02d} 09:00:00")

        result = get_report(user_id=user_id, period="weekly", date="2030-01-14", db=db)

        assert result["comparison"]["previous_period"]["start"] == "2030-01-07"
        assert result["comparison"]["previous_period"]["end"] == "2030-01-13"
        assert result["comparison"]["caffeine_vs_previous_pct"] == 25.0  # 50% - 25%

    def test_comparison_is_null_when_previous_week_has_no_logs(self, db):
        user_id = make_user(db, pregnancy_week=20)
        make_food_log(db, user_id, caffeine_mg=100, sugar_g=10, sodium_mg=100,
                       eaten_at="2030-01-14 09:00:00")
        # 지난 주(2030-01-07~01-13)에는 아무 기록도 없음

        result = get_report(user_id=user_id, period="weekly", date="2030-01-14", db=db)

        assert result["comparison"]["caffeine_vs_previous_pct"] is None
        assert result["comparison"]["sugar_vs_previous_pct"] is None
        assert result["comparison"]["sodium_vs_previous_pct"] is None

    def test_comparison_is_null_only_for_nutrient_unknown_on_every_previous_week_row(self, db):
        # 지난 주에 기록은 있지만, sugar_g만 모든 행에서 NULL(unknown)인 경우
        # sugar만 null이고 caffeine/sodium은 정상적으로 계산되어야 한다.
        user_id = make_user(db, pregnancy_week=20)
        for i in range(7):
            day = 14 + i
            make_food_log(db, user_id, caffeine_mg=100, sugar_g=0, sodium_mg=100,
                           eaten_at=f"2030-01-{day:02d} 09:00:00")
        for i in range(7):
            day = 7 + i
            make_food_log(db, user_id, caffeine_mg=50, sugar_g=None, sodium_mg=50,
                           eaten_at=f"2030-01-{day:02d} 09:00:00")

        result = get_report(user_id=user_id, period="weekly", date="2030-01-14", db=db)

        assert result["comparison"]["sugar_vs_previous_pct"] is None
        assert result["comparison"]["caffeine_vs_previous_pct"] is not None
        assert result["comparison"]["sodium_vs_previous_pct"] is not None
        assert result["comparison"]["caffeine_vs_previous_pct"] == 25.0  # 50% - 25%
        assert result["comparison"]["sodium_vs_previous_pct"] == 2.1     # 4.3% - 2.2% (limit 2300mg)


class TestGetReportNutrientItems:
    """/intake/summary와 같은 형태로 미리 해석된 nutrient_items 블록."""

    def test_daily_block_has_caffeine_and_selected_nutrients_in_stored_order(self, db):
        user_id = make_user(db, pregnancy_week=20, selected_nutrients="sodium,carbohydrate,sugar")
        make_food_log(db, user_id, caffeine_mg=50, sugar_g=10, sodium_mg=300,
                       eaten_at="2030-01-10 09:00:00")

        result = get_report(user_id=user_id, period="daily", date="2030-01-10", db=db)
        block = result["nutrient_items"]

        assert block["caffeine"]["key"] == "caffeine"
        assert [n["key"] for n in block["nutrients"]] == ["sodium", "carbohydrate", "sugar"]

    def test_block_omits_water_entirely(self, db):
        user_id = make_user(db, pregnancy_week=20)
        make_water_log(db, user_id, amount_ml=1000, logged_at="2030-01-10 09:00:00")

        result = get_report(user_id=user_id, period="daily", date="2030-01-10", db=db)
        block = result["nutrient_items"]

        assert "water" not in block
        assert all(n["key"] != "water" for n in block["nutrients"])
        # flat 블록에는 여전히 수분이 있다 (이 결정은 nutrient_items에만 적용된다)
        assert result["totals"]["water_ml"] == 1000.0

    def test_items_carry_label_unit_and_status_label(self, db):
        user_id = make_user(db, pregnancy_week=20, selected_nutrients="sugar")
        make_food_log(db, user_id, caffeine_mg=50, sugar_g=10, sodium_mg=300,
                       eaten_at="2030-01-10 09:00:00")

        result = get_report(user_id=user_id, period="daily", date="2030-01-10", db=db)
        sugar = result["nutrient_items"]["nutrients"][0]

        assert sugar["label"] == "당류"
        assert sugar["unit"] == "g"
        assert sugar["status"] == "safe"
        assert sugar["status_label"] == "여유"
        assert result["nutrient_items"]["caffeine"]["unit"] == "mg"

    def test_daily_values_equal_flat_totals_because_divisor_is_one(self, db):
        user_id = make_user(
            db, pregnancy_week=20, selected_nutrients="carbohydrate,protein,iron"
        )
        make_food_log(db, user_id, caffeine_mg=50, sugar_g=10, sodium_mg=300,
                       calories_kcal=600, carbohydrate_g=80, protein_g=25,
                       fat_g=20, iron_mg=6, eaten_at="2030-01-10 09:00:00")

        result = get_report(user_id=user_id, period="daily", date="2030-01-10", db=db)
        block = result["nutrient_items"]
        by_key = {n["key"]: n for n in block["nutrients"]}

        assert block["caffeine"]["total"] == result["totals"]["caffeine_mg"]
        assert by_key["carbohydrate"]["total"] == result["totals"]["carbohydrate_g"]
        assert by_key["protein"]["total"] == result["totals"]["protein_g"]
        assert by_key["iron"]["total"] == result["totals"]["iron_mg"]

    def test_weekly_values_are_daily_averages_not_period_totals(self, db):
        user_id = make_user(db, pregnancy_week=20, selected_nutrients="iron")
        # 월~수 3일, 매일 카페인 100mg / 철분 6mg
        for i in range(3):
            make_food_log(db, user_id, caffeine_mg=100, sugar_g=0, sodium_mg=0, iron_mg=6,
                           eaten_at=f"2030-01-{7 + i:02d} 09:00:00")

        result = get_report(user_id=user_id, period="weekly", date="2030-01-07", db=db)
        block = result["nutrient_items"]
        iron = block["nutrients"][0]

        # 합계는 300mg/18mg이지만 블록은 일평균(100mg/6mg)을 판정 대상으로 쓴다
        assert result["totals"]["caffeine_mg"] == 300.0
        assert block["caffeine"]["total"] == 100.0
        assert result["totals"]["iron_mg"] == 18.0
        assert iron["total"] == 6.0

    def test_weekly_block_may_disagree_with_flat_status_for_ceiling_types(self, db):
        # 알려진 불일치의 회귀 가드: 하루 100mg(=50%)씩 7일이면 flat status는 기간
        # 합계(700mg)를 하루 한도(200mg)와 비교해 avoid가 되지만, 블록은 일평균을 본다.
        user_id = make_user(db, pregnancy_week=20, selected_nutrients="sugar")
        for i in range(7):
            make_food_log(db, user_id, caffeine_mg=100, sugar_g=0, sodium_mg=0,
                           eaten_at=f"2030-01-{7 + i:02d} 09:00:00")

        result = get_report(user_id=user_id, period="weekly", date="2030-01-07", db=db)

        assert result["status"]["caffeine_status"] == "avoid"
        assert result["nutrient_items"]["caffeine"]["status"] == "safe"

    def test_empty_selection_returns_caffeine_only(self, db):
        user_id = make_user(db, pregnancy_week=20, selected_nutrients="")

        result = get_report(user_id=user_id, period="daily", date="2030-01-10", db=db)

        assert result["nutrient_items"]["nutrients"] == []
        assert result["nutrient_items"]["caffeine"]["key"] == "caffeine"

    def test_unset_selection_falls_back_to_default_three(self, db):
        user_id = make_user(db, pregnancy_week=20)  # selected_nutrients 미설정 (NULL)

        result = get_report(user_id=user_id, period="weekly", date="2030-01-07", db=db)

        assert [n["key"] for n in result["nutrient_items"]["nutrients"]] == [
            "carbohydrate", "sugar", "sodium",
        ]


class TestGetReportWater:
    """수분은 floor형이며, 분모는 food_log가 아니라 water_log 기준 날 수다."""

    def test_daily_water_totals_percent_and_status(self, db):
        user_id = make_user(db, pregnancy_week=20)
        make_water_log(db, user_id, amount_ml=500, logged_at="2030-01-10 09:00:00")
        make_water_log(db, user_id, amount_ml=300, logged_at="2030-01-10 15:00:00")

        result = get_report(user_id=user_id, period="daily", date="2030-01-10", db=db)

        assert result["totals"]["water_ml"] == 800.0
        assert result["limits"]["water_target_ml"] == DAILY_WATER_TARGET_ML
        assert result["percentages"]["water"] == round(800 / DAILY_WATER_TARGET_ML * 100, 1)
        assert result["status"]["water_status"] == "insufficient"
        assert result["status"]["water_tier"] == "neutral"
        assert result["status"]["water_status_label"] == "부족"

    def test_daily_water_meeting_target_is_sufficient(self, db):
        user_id = make_user(db, pregnancy_week=20)
        make_water_log(db, user_id, amount_ml=DAILY_WATER_TARGET_ML,
                       logged_at="2030-01-10 09:00:00")

        result = get_report(user_id=user_id, period="daily", date="2030-01-10", db=db)

        assert result["status"]["water_status"] == "sufficient"
        assert result["status"]["water_tier"] == "safe"
        assert result["status"]["water_status_label"] == "충분"

    def test_daily_water_is_zero_not_error_when_no_water_logged(self, db):
        user_id = make_user(db, pregnancy_week=20)

        result = get_report(user_id=user_id, period="daily", date="2030-01-10", db=db)

        assert result["totals"]["water_ml"] == 0.0
        assert result["percentages"]["water"] == 0.0
        assert result["status"]["water_status"] == "insufficient"

    def test_weekly_water_divides_by_water_days_not_food_days(self, db):
        # 물은 5일(월~금), 음식은 1일(월)만 기록한다. days_with_data(food_log 기준)는 1이지만
        # 수분 일평균은 5로 나눠야 한다 — 1로 나누면 5일치가 하루치로 보고된다.
        user_id = make_user(db, pregnancy_week=20)
        make_food_log(db, user_id, caffeine_mg=10, sugar_g=1, sodium_mg=10,
                       eaten_at="2030-01-07 09:00:00")   # 월요일에만 음식 기록
        for i in range(5):                                # 월~금 물 1000mL씩
            day = 7 + i
            make_water_log(db, user_id, amount_ml=1000, logged_at=f"2030-01-{day:02d} 10:00:00")

        result = get_report(user_id=user_id, period="weekly", date="2030-01-07", db=db)

        assert result["totals"]["water_ml"] == 5000.0
        # 5000/5 = 1000.0 (5000/1 = 5000.0이 아니다)
        assert result["daily_average"]["water_ml"] == 1000.0
        assert result["percentages"]["water"] == round(1000 / DAILY_WATER_TARGET_ML * 100, 1)
        # food_log 기준 분모는 여전히 1이라는 것도 함께 확인한다 (수분만 다른 분모를 쓴다)
        assert result["daily_average"]["caffeine_mg"] == 10.0

    def test_weekly_water_divisor_is_one_when_no_water_logged(self, db):
        user_id = make_user(db, pregnancy_week=20)
        make_food_log(db, user_id, caffeine_mg=10, sugar_g=1, sodium_mg=10,
                       eaten_at="2030-01-07 09:00:00")

        result = get_report(user_id=user_id, period="weekly", date="2030-01-07", db=db)

        assert result["totals"]["water_ml"] == 0.0
        assert result["daily_average"]["water_ml"] == 0.0
        assert result["status"]["water_status"] == "insufficient"

    def test_water_is_not_added_to_chart_or_comparison(self, db):
        user_id = make_user(db, pregnancy_week=20)
        make_water_log(db, user_id, amount_ml=1000, logged_at="2030-01-07 10:00:00")

        result = get_report(user_id=user_id, period="weekly", date="2030-01-07", db=db)

        assert all("water_ml" not in item for item in result["chart"]["items"])
        assert all("water_status" not in item for item in result["chart"]["items"])
        assert "water_vs_previous_pct" not in result["comparison"]


class TestGetReportTiers:
    """raw status 옆에 붙는 tier/status_label 형제 키 (OCR 확인 화면과 같은 어휘)."""

    def _item(self, result, label):
        return next(i for i in result["chart"]["items"] if i["label"] == label)

    def test_floor_shortfall_is_neutral_tier_but_deficient_label(self, db):
        user_id = make_user(db, pregnancy_week=20)

        result = get_report(user_id=user_id, period="daily", date="2030-01-10", db=db)

        assert result["status"]["carbohydrate_status"] == "insufficient"
        assert result["status"]["carbohydrate_tier"] == "neutral"
        assert result["status"]["carbohydrate_status_label"] == "부족"

    def test_chart_item_gains_tier_and_status_label(self, db):
        user_id = make_user(db, pregnancy_week=20)
        make_food_log(db, user_id, caffeine_mg=30, sugar_g=5, sodium_mg=100,
                       eaten_at="2030-01-10 08:00:00")   # 오전

        result = get_report(user_id=user_id, period="daily", date="2030-01-10", db=db)

        morning = self._item(result, "오전")
        # 항목 전체(top-level) status/tier/status_label은 여전히 _attach_tiers가 붙인다.
        # 탄수화물(기본 선택, 0g)은 floor형이라 버킷 롤업(_chart_item_status)에서
        # 제외되므로, ceiling형(카페인/당류/나트륨)만으로 판정한 결과가 그대로 온다.
        assert morning["status"] == "safe"
        assert morning["tier"] == "safe"
        assert morning["status_label"] == "여유"
        # 영양소별 tier/status_label은 flat <key>_tier 형제 키가 아니라
        # nutrients[key] 안에 build_nutrient_summary_item() 결과로 이미 들어 있다.
        assert morning["nutrients"]["caffeine"]["tier"] == "safe"
        assert morning["nutrients"]["caffeine"]["status_label"] == "여유"
        # 탄수화물 자체의 판정은 그대로 남아 있다 — 배제된 건 롤업뿐이다.
        assert morning["nutrients"]["carbohydrate"]["status"] == "insufficient"
        assert morning["nutrients"]["carbohydrate"]["tier"] == "neutral"

    def test_raw_status_values_are_unchanged(self, db):
        user_id = make_user(db, pregnancy_week=20)
        make_food_log(db, user_id, caffeine_mg=250, sugar_g=5, sodium_mg=100,
                       eaten_at="2030-01-10 08:00:00")

        result = get_report(user_id=user_id, period="daily", date="2030-01-10", db=db)

        assert result["status"]["caffeine_status"] == "avoid"
        assert result["status"]["caffeine_tier"] == "avoid"
        assert result["status"]["caffeine_status_label"] == "위험"
        assert result["status"]["overall_status"] == "avoid"
        assert result["status"]["overall_tier"] == "avoid"

    def test_weekly_report_also_carries_tiers(self, db):
        user_id = make_user(db, pregnancy_week=20)
        make_food_log(db, user_id, caffeine_mg=100, sugar_g=10, sodium_mg=300,
                       eaten_at="2030-01-07 09:00:00")   # 월요일

        result = get_report(user_id=user_id, period="weekly", date="2030-01-07", db=db)

        assert result["status"]["sugar_tier"] == "safe"
        assert result["status"]["sugar_status_label"] == "여유"
        # 탄수화물(기본 선택, 0g)은 floor형이라 버킷 롤업에서 제외된다 — 이 날의
        # 조합 tier는 ceiling형(카페인/당류/나트륨)만으로 계산되어 safe로 남는다.
        assert self._item(result, "월")["tier"] == "safe"
        assert self._item(result, "월")["nutrients"]["sugar"]["tier"] == "safe"
        assert self._item(result, "월")["nutrients"]["carbohydrate"]["status"] == "insufficient"

    def test_non_status_keys_are_left_alone(self, db):
        user_id = make_user(db, pregnancy_week=20)

        result = get_report(user_id=user_id, period="weekly", date="2030-01-07", db=db)

        assert "tier" not in result
        assert "status_label" not in result
        assert set(result["daily_average"]) == {
            "caffeine_mg", "sugar_g", "sodium_mg",
            "energy_kcal", "carbohydrate_g", "protein_g", "water_ml",
        }


class TestAggregateHelpersBandTypeKey:
    """_aggregate_week()/_aggregate_day_slots()가 band형 영양소(예: 철분)를 포함한
    keys를 받아도 values/known 중첩 구조를 올바르게 만드는지 확인한다."""

    def test_aggregate_week_shapes_values_and_known_for_iron(self, db):
        user_id = make_user(db, pregnancy_week=20)
        make_food_log(db, user_id, caffeine_mg=10, iron_mg=6,
                       eaten_at="2030-02-04 09:00:00")  # 월요일

        week_days, row_count = _aggregate_week(
            cursor=db.cursor(), user_id=user_id,
            monday=date(2030, 2, 4),
            sunday=date(2030, 2, 10),
            keys=["caffeine", "iron"],
        )

        assert row_count == 1
        monday = next(d for d in week_days if d["label"] == "월")
        assert monday["values"] == {"caffeine": 10.0, "iron": 6.0}
        assert monday["known"] == {"caffeine": 1, "iron": 1}
        tuesday = next(d for d in week_days if d["label"] == "화")
        assert tuesday["values"] == {"caffeine": 0.0, "iron": 0.0}
        assert tuesday["known"] == {"caffeine": 0, "iron": 0}

    def test_aggregate_day_slots_shapes_values_and_known_for_iron(self, db):
        user_id = make_user(db, pregnancy_week=20)
        make_food_log(db, user_id, caffeine_mg=10, iron_mg=6,
                       eaten_at="2030-02-04 09:00:00")  # 오전

        slot_data, row_count = _aggregate_day_slots(
            cursor=db.cursor(), user_id=user_id, date_str="2030-02-04", keys=["caffeine", "iron"]
        )

        assert row_count == 1
        assert slot_data["오전"]["values"] == {"caffeine": 10.0, "iron": 6.0}
        assert slot_data["오전"]["known"] == {"caffeine": 1, "iron": 1}
        # 철분이 아예 기록되지 않은 시간대는 0/0으로 남는다 (unknown 여부는 이 구조가
        # 아니라 build_nutrient_summary_item()의 _is_data_unresolved가 판단한다).
        assert slot_data["새벽"]["values"] == {"caffeine": 0.0, "iron": 0.0}
        assert slot_data["새벽"]["known"] == {"caffeine": 0, "iron": 0}


class TestGetReportChartFollowsSelectedNutrients:
    """차트(chart.items[].nutrients)가 nutrient_items와 같은 selected_nutrients를
    따라가는지 확인한다 — 이 파일이 고치는 "같은 화면, 모순된 내용" 버그의 회귀 가드."""

    def test_chart_includes_non_default_selected_nutrient(self, db):
        user_id = make_user(db, pregnancy_week=20, selected_nutrients="protein")
        make_food_log(db, user_id, caffeine_mg=10, sugar_g=0, sodium_mg=0,
                       protein_g=20, eaten_at="2030-02-04 09:00:00")

        result = get_report(user_id=user_id, period="daily", date="2030-02-04", db=db)

        morning = next(i for i in result["chart"]["items"] if i["label"] == "오전")
        assert set(morning["nutrients"]) == {"caffeine", "protein"}
        assert morning["nutrients"]["protein"]["value"] == 20.0
        assert morning["nutrients"]["protein"]["label"] == "단백질"

    def test_chart_omits_unselected_default_nutrients(self, db):
        # sugar/sodium이 기본 선택 목록에 있지만, 이 사용자는 protein만 선택했으므로
        # 차트 nutrients에 sugar/sodium이 나타나면 안 된다.
        user_id = make_user(db, pregnancy_week=20, selected_nutrients="protein")

        result = get_report(user_id=user_id, period="weekly", date="2030-02-04", db=db)

        for item in result["chart"]["items"]:
            assert "sugar" not in item["nutrients"]
            assert "sodium" not in item["nutrients"]

    def test_chart_band_type_nutrient_has_null_pct_but_real_tier(self, db):
        # fat/iron(band형)은 build_nutrient_summary_item()이 항상 percent=None을
        # 돌려준다 — 단일 퍼센트 개념이 없기 때문이다. 값이 있으면 tier/status는
        # 여전히 실제로 계산된다.
        user_id = make_user(db, pregnancy_week=20, selected_nutrients="iron")
        make_food_log(db, user_id, caffeine_mg=0, iron_mg=30,
                       eaten_at="2030-02-04 09:00:00")  # 30mg: 권장 이상, 상한 미만 -> safe

        result = get_report(user_id=user_id, period="daily", date="2030-02-04", db=db)

        morning = next(i for i in result["chart"]["items"] if i["label"] == "오전")
        assert morning["nutrients"]["iron"]["pct"] is None
        assert morning["nutrients"]["iron"]["value"] == 30.0
        assert morning["nutrients"]["iron"]["status"] == "safe"
        assert morning["nutrients"]["iron"]["tier"] == "safe"

    def test_chart_caffeine_only_when_selection_is_empty(self, db):
        user_id = make_user(db, pregnancy_week=20, selected_nutrients="")
        make_food_log(db, user_id, caffeine_mg=10, eaten_at="2030-02-04 09:00:00")

        result = get_report(user_id=user_id, period="daily", date="2030-02-04", db=db)

        for item in result["chart"]["items"]:
            assert set(item["nutrients"]) == {"caffeine"}


class TestChartItemStatusExcludesFloorType:
    """_chart_item_status()의 floor형 제외 규칙을 직접 검증한다.

    회귀 배경: compute_overall_status()는 하루 전체 합계용으로 설계되어 floor형의
    "미달"을 caution 동급으로 취급한다. 버킷(시간대/요일) 단위에 그대로 적용하면
    거의 모든 버킷이 caution으로 물드는데(하루치 최소량을 한 버킷에서 채우는 경우는
    없으므로), mompeace_ocr_design.md §7은 이 "부족"이 경고가 아니라고 명시한다.
    """

    def test_floor_insufficient_does_not_pollute_bucket_when_ceiling_is_safe(self):
        nutrients = {
            "caffeine": {"status": "safe"},
            "carbohydrate": {"status": "insufficient"},  # floor형, 버킷 단위에서는 항상 미달
        }
        assert _chart_item_status(nutrients, ["caffeine", "carbohydrate"]) == "safe"

    def test_ceiling_avoid_still_wins_regardless_of_floor_status(self):
        nutrients = {
            "caffeine": {"status": "avoid"},
            "carbohydrate": {"status": "insufficient"},
        }
        assert _chart_item_status(nutrients, ["caffeine", "carbohydrate"]) == "avoid"

    def test_band_type_iron_still_counted_in_rollup(self):
        nutrients = {
            "caffeine": {"status": "safe"},
            "iron": {"status": "avoid"},  # band형은 floor가 아니므로 롤업에 포함된다
        }
        assert _chart_item_status(nutrients, ["caffeine", "iron"]) == "avoid"


class TestGetReportAiSummary:
    """ai_summary가 chart_keys(카페인 + 선택 영양소) 전체를 따라가는지, 그리고
    ceiling/floor/band 타입별로 올바른 문구·심각도를 고르는지 검증한다.
    pregnancy_week=20(middle) 기준 한도: 카페인 200mg, 당류 50g, 나트륨 2300mg,
    탄수화물 최소 175g, 에너지 목표 2340kcal, 단백질 70g, 지방 상한 78g(2340*0.30/9),
    철분 권장 24mg/상한 45mg.
    """

    def test_ceiling_avoid_uses_daily_specific_wording(self, db):
        user_id = make_user(db, pregnancy_week=20, selected_nutrients="")
        make_food_log(db, user_id, caffeine_mg=250, sugar_g=0, sodium_mg=0,
                       eaten_at="2030-03-01 09:00:00")  # 250/200 -> avoid

        result = get_report(user_id=user_id, period="daily", date="2030-03-01", db=db)

        assert result["ai_summary"]["messages"][0] == (
            "카페인 섭취량이 기준을 넘었어요. 오늘은 추가 섭취를 피하는 것이 좋아요."
        )

    def test_ceiling_caution_uses_daily_specific_wording(self, db):
        user_id = make_user(db, pregnancy_week=20, selected_nutrients="")
        make_food_log(db, user_id, caffeine_mg=150, sugar_g=0, sodium_mg=0,
                       eaten_at="2030-03-02 09:00:00")  # 150/200 = 75% -> caution

        result = get_report(user_id=user_id, period="daily", date="2030-03-02", db=db)

        assert result["ai_summary"]["messages"][0] == "카페인 섭취량이 기준에 가까워지고 있어요."

    def test_ceiling_weekly_wording_reads_as_average_not_a_single_day(self, db):
        # 일간 문구("섭취량이 기준을 넘었어요")를 주간에 그대로 쓰면 "어느 하루
        # 초과했다"로 읽힌다 — 주간 카드는 하루 평균이므로 반드시 다른 문구를 써야 한다.
        user_id = make_user(db, pregnancy_week=20, selected_nutrients="")
        for day in range(14, 21):
            make_food_log(db, user_id, caffeine_mg=250, sugar_g=0, sodium_mg=0,
                           eaten_at=f"2030-01-{day} 09:00:00")  # 매일 250mg -> 평균도 avoid

        result = get_report(user_id=user_id, period="weekly", date="2030-01-15", db=db)

        message = result["ai_summary"]["messages"][0]
        assert "이번 주" in message
        assert "평균" in message
        assert message != (
            "카페인 섭취량이 기준을 넘었어요. 오늘은 추가 섭취를 피하는 것이 좋아요."
        )

    def test_floor_insufficient_below_half_uses_gentle_far_from_goal_wording(self, db):
        user_id = make_user(db, pregnancy_week=20, selected_nutrients="carbohydrate")
        make_food_log(db, user_id, caffeine_mg=0, carbohydrate_g=50,  # 50/175 = 28.6% (<50%)
                       eaten_at="2030-03-03 09:00:00")

        result = get_report(user_id=user_id, period="daily", date="2030-03-03", db=db)

        assert result["ai_summary"]["messages"][0] == (
            "탄수화물 섭취가 아직 많이 부족해요. 조금씩 채워보세요."
        )

    def test_floor_insufficient_above_half_uses_almost_there_wording(self, db):
        user_id = make_user(db, pregnancy_week=20, selected_nutrients="carbohydrate")
        make_food_log(db, user_id, caffeine_mg=0, carbohydrate_g=100,  # 100/175 = 57.1% (>=50%)
                       eaten_at="2030-03-04 09:00:00")

        result = get_report(user_id=user_id, period="daily", date="2030-03-04", db=db)

        assert result["ai_summary"]["messages"][0] == (
            "탄수화물 섭취가 목표에 거의 다 왔어요. 조금만 더 신경 써주세요."
        )

    def test_floor_sufficient_produces_no_message(self, db):
        user_id = make_user(db, pregnancy_week=20, selected_nutrients="carbohydrate")
        make_food_log(db, user_id, caffeine_mg=0, carbohydrate_g=200,  # >= 175 -> sufficient
                       eaten_at="2030-03-05 09:00:00")

        result = get_report(user_id=user_id, period="daily", date="2030-03-05", db=db)

        assert "탄수화물" not in " ".join(result["ai_summary"]["messages"])

    def test_band_avoid_and_caution_use_ceiling_style_wording(self, db):
        user_id = make_user(db, pregnancy_week=20, selected_nutrients="fat")
        # 90g / 2340kcal 기준 상한(78g) 초과 -> avoid
        make_food_log(db, user_id, caffeine_mg=0, calories_kcal=2340, fat_g=90,
                       eaten_at="2030-03-06 09:00:00")

        result = get_report(user_id=user_id, period="daily", date="2030-03-06", db=db)

        assert result["ai_summary"]["messages"][0] == (
            "지방 섭취량이 상한을 넘었어요. 오늘은 섭취를 줄이는 것이 좋아요."
        )

    def test_band_low_uses_gentle_non_warning_wording(self, db):
        user_id = make_user(db, pregnancy_week=20, selected_nutrients="iron")
        make_food_log(db, user_id, caffeine_mg=0, iron_mg=10,  # < 24mg 권장량 -> low
                       eaten_at="2030-03-07 09:00:00")

        result = get_report(user_id=user_id, period="daily", date="2030-03-07", db=db)

        assert result["ai_summary"]["messages"][0] == "철분 섭취가 부족해요. 조금 더 신경 써주세요."

    def test_warnings_ordered_worst_tier_first_regardless_of_chart_key_order(self, db):
        # chart_keys 순서는 caffeine, carbohydrate, sugar, fat인데(선택 순서 그대로),
        # 심각도 순서(avoid > caution > neutral)가 그 순서를 이겨야 한다.
        user_id = make_user(db, pregnancy_week=20, selected_nutrients="carbohydrate,sugar,fat")
        make_food_log(
            db, user_id,
            caffeine_mg=0,                 # safe -> 메시지 없음
            carbohydrate_g=50,              # insufficient -> neutral
            sugar_g=60,                     # 60/50 > 1.0 -> avoid
            calories_kcal=2340, fat_g=60,    # 60/78 = 76.9% -> caution
            eaten_at="2030-03-08 09:00:00",
        )

        result = get_report(user_id=user_id, period="daily", date="2030-03-08", db=db)
        messages = result["ai_summary"]["messages"]

        assert "당류" in messages[0] and "넘었" in messages[0]        # avoid
        assert "지방" in messages[1] and "가까워지고" in messages[1]  # caution
        assert "탄수화물" in messages[2] and "부족" in messages[2]    # neutral

    def test_nutrient_warnings_capped_at_three(self, db):
        # chart_keys 최대 4개(카페인 + 선택 3개) 전부 avoid를 내도 카드는 3개까지만
        # 보여준다 — 동률(전부 avoid)이면 chart_keys 순서(카페인 우선)로 상위 3개.
        user_id = make_user(db, pregnancy_week=20, selected_nutrients="sugar,sodium,fat")
        make_food_log(
            db, user_id,
            caffeine_mg=250, sugar_g=60, sodium_mg=2400,      # 전부 avoid
            calories_kcal=2340, fat_g=90,                      # avoid
            eaten_at="2030-03-09 09:00:00",
        )

        result = get_report(user_id=user_id, period="daily", date="2030-03-09", db=db)
        warning_count = sum(
            1 for m in result["ai_summary"]["messages"]
            if "넘었" in m or "상한을 넘었" in m
        )
        assert warning_count == 3
        assert "카페인" in result["ai_summary"]["messages"][0]
        assert "당류" in result["ai_summary"]["messages"][1]
        assert "나트륨" in result["ai_summary"]["messages"][2]
        assert "지방" not in " ".join(result["ai_summary"]["messages"][:3])

    def test_fallback_message_when_nothing_fires(self, db):
        user_id = make_user(db, pregnancy_week=20, selected_nutrients="")
        make_food_log(db, user_id, caffeine_mg=10, sugar_g=0, sodium_mg=0,
                       eaten_at="2030-03-10 09:00:00")

        result = get_report(user_id=user_id, period="daily", date="2030-03-10", db=db)

        assert "오늘은 전반적으로 기준 이내에서 섭취했어요." in result["ai_summary"]["messages"]

    def test_weekly_fallback_message_when_nothing_fires(self, db):
        user_id = make_user(db, pregnancy_week=20, selected_nutrients="")
        for day in range(14, 21):
            make_food_log(db, user_id, caffeine_mg=10, sugar_g=0, sodium_mg=0,
                           eaten_at=f"2030-01-{day} 09:00:00")

        result = get_report(user_id=user_id, period="weekly", date="2030-01-15", db=db)

        assert "이번 주는 전반적으로 안정적인 섭취 흐름을 보였어요." in result["ai_summary"]["messages"]

    def test_all_floor_type_returns_unknown_not_safe(self):
        # 방어적 케이스: chart_keys가 카페인 없이 floor형만으로 구성되면(현재 코드에서는
        # chart_keys가 항상 "caffeine"으로 시작해 도달 불가능하다) compute_overall_status()의
        # 빈 인자 기본값("safe")을 그대로 쓰지 않는다 — 아무것도 판정 안 하고 "안전"이라
        # 말하는 것은 과장이다. "unknown"을 쓴다.
        nutrients = {
            "carbohydrate": {"status": "insufficient"},
            "protein": {"status": "sufficient"},
        }
        assert _chart_item_status(nutrients, ["carbohydrate", "protein"]) == "unknown"
