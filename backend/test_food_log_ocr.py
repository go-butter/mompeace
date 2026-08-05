"""
backend/routers/food_log.py::create_food_log()의 needs_review 컬럼 저장 및
serving_multiplier 적용 테스트.

create_food_log()는 이 변경 전까지 직접 테스트가 없었으므로, needs_review
추가와 함께 두 INSERT 분기(eaten_at 있음/없음) 모두를 커버한다.

핵심 검증 대상:
- FoodLogCreate.needs_review=True로 저장하면 food_log.needs_review에
  그대로 반영된다 (eaten_at 지정/미지정 분기 모두)
- needs_review를 생략하면 기본값 False(0)로 저장된다
- OCR 입력(input_type="ocr")은 food_id가 없으므로 food_log.caffeine_mg가
  요청대로 None으로 저장된다 (카페인은 OCR 범위 밖 원칙)
- serving_multiplier가 주어지면 sugar_g/sodium_mg/caffeine_mg에 곱해져 저장된다
  (OCR 확인 화면이 보내는 1회 제공량 기준 값 × 인분수/그램 비율)
- serving_multiplier를 곱해도 원본이 None이면 결과는 항상 None (정보 없음 ≠ 0)
- food_id가 함께 전달되면 food_id 경로(_judge_food_log_from_food_item)가 우선
  적용되고 serving_multiplier는 무시된다 (이중 곱셈 방지)
- fat_g/cholesterol_mg/iron_mg 직접 입력값은 그대로 저장되고, 생략 시 None으로 남는다
- food_id 경로에서는 food_items의 fat_g/cholesterol_mg/iron_mg에도 amount가 곱해져 저장된다
"""
import sqlite3

from backend.models import FoodLogCreate
from backend.routers.food_log import create_food_log

from .conftest import make_user


def _make_food_item(db, **overrides):
    defaults = {
        "food_name": "테스트 식품",
        "sugar_g": 10.0,
        "sodium_mg": 100.0,
        "caffeine_mg": None,
    }
    defaults.update(overrides)
    cols = ", ".join(defaults.keys())
    placeholders = ", ".join("?" for _ in defaults)
    cursor = db.cursor()
    cursor.execute(
        f"INSERT INTO food_items ({cols}) VALUES ({placeholders})",
        list(defaults.values()),
    )
    db.commit()
    return cursor.lastrowid


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


class TestServingMultiplier:
    def test_serving_multiplier_scales_nutrients(self, db):
        user_id = make_user(db)
        log = FoodLogCreate(
            user_id=user_id,
            food_name="감자깡",
            input_type="ocr",
            sugar_g=3.6,
            sodium_mg=15.0,
            serving_multiplier=2.0,
        )
        result = create_food_log(log=log, db=db)
        row = _fetch_log(db, result["log_id"])
        assert row["sugar_g"] == 7.2
        assert row["sodium_mg"] == 30.0

    def test_serving_multiplier_none_nutrient_stays_none(self, db):
        user_id = make_user(db)
        log = FoodLogCreate(
            user_id=user_id,
            food_name="감자깡",
            input_type="ocr",
            sugar_g=None,  # 라벨에서 읽지 못함
            sodium_mg=15.0,
            serving_multiplier=2.0,
        )
        result = create_food_log(log=log, db=db)
        row = _fetch_log(db, result["log_id"])
        assert row["sugar_g"] is None
        assert row["sodium_mg"] == 30.0

    def test_serving_multiplier_omitted_leaves_values_unchanged(self, db):
        user_id = make_user(db)
        log = FoodLogCreate(
            user_id=user_id,
            food_name="감자깡",
            input_type="ocr",
            sugar_g=3.6,
            sodium_mg=15.0,
        )
        result = create_food_log(log=log, db=db)
        row = _fetch_log(db, result["log_id"])
        assert row["sugar_g"] == 3.6
        assert row["sodium_mg"] == 15.0

    def test_serving_multiplier_scales_all_seven_tracked_fields(self, db):
        # OCR 응답이 이제 7개 영양소를 전부 반환하므로, 인분수/그램 배율도 당류/
        # 나트륨뿐 아니라 전부에 적용되어야 한다 (그렇지 않으면 5개가 1회 제공량이
        # 아닌 원본 그대로 저장된다).
        user_id = make_user(db)
        log = FoodLogCreate(
            user_id=user_id,
            food_name="감자깡",
            input_type="ocr",
            sugar_g=3.6,
            sodium_mg=15.0,
            calories_kcal=45.0,
            carbohydrate_g=7.0,
            protein_g=0.6,
            fat_g=1.8,
            iron_mg=0.12,
            serving_multiplier=2.0,
        )
        result = create_food_log(log=log, db=db)
        row = _fetch_log(db, result["log_id"])
        assert row["sugar_g"] == 7.2
        assert row["sodium_mg"] == 30.0
        assert row["calories_kcal"] == 90.0
        assert row["carbohydrate_g"] == 14.0
        assert row["protein_g"] == 1.2
        assert row["fat_g"] == 3.6
        assert row["iron_mg"] == 0.24

    def test_serving_multiplier_none_preserving_per_field(self, db):
        # 일부 영양소는 라벨에서 읽지 못해 None일 수 있다 — 그 필드만 None으로
        # 남고 나머지는 정상적으로 스케일되어야 한다.
        user_id = make_user(db)
        log = FoodLogCreate(
            user_id=user_id,
            food_name="감자깡",
            input_type="ocr",
            sugar_g=3.6,
            sodium_mg=15.0,
            carbohydrate_g=7.0,
            protein_g=None,  # 라벨에서 읽지 못함
            fat_g=1.8,
            iron_mg=None,  # 라벨에서 읽지 못함
            serving_multiplier=2.0,
        )
        result = create_food_log(log=log, db=db)
        row = _fetch_log(db, result["log_id"])
        assert row["carbohydrate_g"] == 14.0
        assert row["fat_g"] == 3.6
        assert row["protein_g"] is None
        assert row["iron_mg"] is None

    def test_serving_multiplier_ignored_when_food_id_present(self, db):
        # food_id 경로가 우선이므로, 혹시라도 serving_multiplier가 함께
        # 전달돼도 food_id 기준 판정(_judge_food_log_from_food_item, amount 배율)
        # 결과가 이중으로 곱해지지 않아야 한다.
        user_id = make_user(db)
        food_id = _make_food_item(db, sugar_g=10.0, sodium_mg=100.0)
        log = FoodLogCreate(
            user_id=user_id,
            food_name="무시됨",
            input_type="food_id",
            food_id=food_id,
            amount=2.0,
            serving_multiplier=5.0,  # food_id 경로에서는 사용되지 않아야 함
        )
        result = create_food_log(log=log, db=db)
        row = _fetch_log(db, result["log_id"])
        # amount(2.0)만 적용됨 — serving_multiplier(5.0)가 추가로 곱해졌다면
        # 100.0/1000.0이 아니라 20.0/200.0이어야 한다.
        assert row["sugar_g"] == 20.0
        assert row["sodium_mg"] == 200.0


class TestFatCholesterolDirectField:
    def test_direct_fat_and_cholesterol_persist(self, db):
        user_id = make_user(db)
        log = FoodLogCreate(
            user_id=user_id,
            food_name="테스트 음식",
            input_type="manual",
            fat_g=12.5,
            cholesterol_mg=45.0,
            iron_mg=8.0,
        )
        result = create_food_log(log=log, db=db)
        row = _fetch_log(db, result["log_id"])
        assert row["fat_g"] == 12.5
        assert row["cholesterol_mg"] == 45.0
        assert row["iron_mg"] == 8.0

    def test_omitted_fat_and_cholesterol_stay_none(self, db):
        user_id = make_user(db)
        log = FoodLogCreate(
            user_id=user_id,
            food_name="테스트 음식",
            input_type="manual",
        )
        result = create_food_log(log=log, db=db)
        row = _fetch_log(db, result["log_id"])
        assert row["fat_g"] is None
        assert row["cholesterol_mg"] is None
        assert row["iron_mg"] is None

    def test_food_id_path_derives_fat_and_cholesterol_from_food_items(self, db):
        user_id = make_user(db)
        food_id = _make_food_item(db, fat_g=10.0, cholesterol_mg=20.0, iron_mg=5.0)
        log = FoodLogCreate(
            user_id=user_id,
            food_name="무시됨",
            input_type="food_id",
            food_id=food_id,
            amount=2.0,
        )
        result = create_food_log(log=log, db=db)
        row = _fetch_log(db, result["log_id"])
        assert row["fat_g"] == 20.0
        assert row["cholesterol_mg"] == 40.0
        assert row["iron_mg"] == 10.0
