"""
backend/routers/food_log.py::create_food_log()의 needs_review 컬럼 저장 테스트.

create_food_log()는 이 변경 전까지 직접 테스트가 없었으므로, needs_review
추가와 함께 두 INSERT 분기(eaten_at 있음/없음) 모두를 커버한다.

핵심 검증 대상:
- FoodLogCreate.needs_review=True로 저장하면 food_log.needs_review에
  그대로 반영된다 (eaten_at 지정/미지정 분기 모두)
- needs_review를 생략하면 기본값 False(0)로 저장된다
- OCR 입력(input_type="ocr")은 food_id가 없으므로 food_log.caffeine_mg가
  요청대로 None으로 저장된다 (카페인은 OCR 범위 밖 원칙)
"""
import sqlite3

from backend.models import FoodLogCreate
from backend.routers.food_log import create_food_log

from .conftest import make_user


def _fetch_log(db: sqlite3.Connection, log_id: int) -> dict:
    cursor = db.cursor()
    cursor.execute("SELECT * FROM food_log WHERE log_id = ?", (log_id,))
    return dict(cursor.fetchone())


class TestNeedsReviewPersistence:
    def test_needs_review_true_with_eaten_at_persists(self, db):
        user_id = make_user(db)
        log = FoodLogCreate(
            user_id=user_id,
            food_name="테스트 과자",
            input_type="ocr",
            caffeine_mg=None,
            sugar_g=42.6,
            sodium_mg=177.5,
            needs_review=True,
            eaten_at="2026-08-01 09:00:00",
        )
        result = create_food_log(log=log, db=db)
        row = _fetch_log(db, result["log_id"])
        assert row["needs_review"] == 1
        assert row["input_type"] == "ocr"
        assert row["caffeine_mg"] is None

    def test_needs_review_true_without_eaten_at_persists(self, db):
        user_id = make_user(db)
        log = FoodLogCreate(
            user_id=user_id,
            food_name="테스트 과자",
            input_type="ocr",
            caffeine_mg=None,
            sugar_g=8.0,
            sodium_mg=200.0,
            needs_review=True,
        )
        result = create_food_log(log=log, db=db)
        row = _fetch_log(db, result["log_id"])
        assert row["needs_review"] == 1

    def test_needs_review_omitted_defaults_to_false(self, db):
        user_id = make_user(db)
        log = FoodLogCreate(
            user_id=user_id,
            food_name="테스트 과자",
            input_type="ocr",
            sugar_g=8.0,
            sodium_mg=200.0,
        )
        result = create_food_log(log=log, db=db)
        row = _fetch_log(db, result["log_id"])
        assert row["needs_review"] == 0
