"""
OCR 경로로 저장된 food_log.caffeine_mg가 오늘 누적 섭취량 합산에 정상 반영되는지 검증.
(회귀 방지: food_log_extra_nutrients로만 기록된 카페인은 집계에서 누락되던 버그의 재발 방지)
"""
from datetime import date

from backend.intake_totals import compute_today_intake_totals
from backend.routers.intake import get_today_intake

from .conftest import make_food_log, make_user


class TestOcrCaffeineIncludedInDailyTotal:
    def test_compute_today_intake_totals_sums_ocr_caffeine(self, db):
        user_id = make_user(db)
        today = date.today().isoformat()
        make_food_log(
            db, user_id, input_type="ocr", caffeine_mg=80,
            sugar_g=5, sodium_mg=120, needs_review=1,
            eaten_at=f"{today} 09:00:00",
        )

        totals = compute_today_intake_totals(user_id, db)

        assert totals["caffeine_mg"] == 80
        assert totals["unknown_caffeine_count"] == 0

    def test_get_today_intake_reflects_ocr_caffeine(self, db):
        user_id = make_user(db, pregnancy_week=20)
        today = date.today().isoformat()
        make_food_log(
            db, user_id, input_type="ocr", caffeine_mg=80,
            sugar_g=5, sodium_mg=120, needs_review=1,
            eaten_at=f"{today} 09:00:00",
        )

        result = get_today_intake(user_id=user_id, db=db)

        assert result["intake"]["total_caffeine"] == 80
