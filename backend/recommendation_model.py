"""
임신 중 식품 추천 ML 예측 모듈

RandomForest 모델로 식품 추천 상태(possible/caution/avoid)를 예측하고
규칙 기반 안전장치를 적용하여 최종 결과를 반환한다.

주의:
- 규칙 기반 기준을 바탕으로 학습한 초기 ML 추천 모델
- 공식 임신 주차별 의학 기준이 아님
- food_nutrition_api 소스는 카페인 미제공 API → caffeine_mg=0 포함 항상 missing 처리
- caffeine_mg = None 은 missing 으로 처리 (0으로 변환 금지)
"""
import json
import pickle
from pathlib import Path
from typing import Optional

from backend.food_search_api import detect_caffeine_keywords
from backend.risk import get_trimester

_HERE = Path(__file__).resolve().parent
MODEL_PATH = _HERE / "ml" / "recommendation_model.pkl"
META_PATH = _HERE / "ml" / "recommendation_model_meta.json"

# 트라이메스터별 1일 허용 기준 (앱 내부 보수적 기준, 공식 의학 기준 아님)
DAILY_LIMITS = {
    "early":  {"caffeine": 200.0, "sugar": 30.0,  "sodium": 2000.0},
    "middle": {"caffeine": 200.0, "sugar": 40.0,  "sodium": 2000.0},
    "late":   {"caffeine": 200.0, "sugar": 30.0,  "sodium": 1800.0},
}

TRIMESTER_ENCODE = {"early": 0, "middle": 1, "late": 2}
STATUS_LABEL_KO = {"possible": "섭취 가능", "caution": "주의", "avoid": "비추천"}
STATUS_RANK = {"possible": 0, "caution": 1, "avoid": 2}

# ── 모델 로딩 (서버 시작 시 1회) ───────────────────────────
try:
    with open(MODEL_PATH, "rb") as _f:
        _model = pickle.load(_f)
    with open(META_PATH, "r", encoding="utf-8") as _f:
        _meta = json.load(_f)
    _feature_columns: list = _meta["feature_columns"]
    _model_available: bool = True
    print(f"✅ 추천 모델 로드 완료: {MODEL_PATH}")
except FileNotFoundError:
    _model = None
    _meta = {}
    _feature_columns = []
    _model_available = False
    print("⚠️  추천 모델 파일 없음. 규칙 기반 안전장치만으로 판정합니다.")
    print("   python -m backend.ml.generate_training_data 후 python -m backend.ml.train_model 을 실행하세요.")
except Exception as _e:
    _model = None
    _model_available = False
    print(f"⚠️  추천 모델 로드 실패: {_e}")


# ── 소스 인식 카페인 missing 판별 ──────────────────────────
def _is_caffeine_missing(food: dict) -> bool:
    """
    카페인 정보 missing 여부 판단.

    카페인 미제공 소스(food_nutrition_api, processed_food_db_download)는
    caffeine_mg 값에 관계없이 항상 missing 처리.
    dish_db_download, food_qr_api 는 caffeine_mg is None 인 경우에만 missing.
    """
    data_source = food.get("data_source") or ""
    if data_source in ("food_nutrition_api", "processed_food_db_download"):
        return True
    return food.get("caffeine_mg") is None


# ── 피처 벡터 빌드 ─────────────────────────────────────────
def build_feature_vector(
    food: dict,
    pregnancy_week: int,
    trimester: str,
    today_intake: dict,
    allergy_match: int,
) -> list:
    limits = DAILY_LIMITS[trimester]
    caffeine_limit = limits["caffeine"]
    sugar_limit = limits["sugar"]
    sodium_limit = limits["sodium"]

    # 소스 인식 caffeine_missing (food_nutrition_api는 항상 missing)
    caffeine_missing = 1 if _is_caffeine_missing(food) else 0
    raw_caffeine = food.get("caffeine_mg")
    food_caffeine = raw_caffeine if (raw_caffeine is not None and not caffeine_missing) else 0.0

    raw_sugar = food.get("sugar_g")
    sugar_missing = 1 if raw_sugar is None else 0
    food_sugar = raw_sugar if raw_sugar is not None else 0.0

    raw_sodium = food.get("sodium_mg")
    sodium_missing = 1 if raw_sodium is None else 0
    food_sodium = raw_sodium if raw_sodium is not None else 0.0

    food_carb = food.get("carbohydrate_g") or 0.0
    food_protein = food.get("protein_g") or 0.0

    caffeine_keywords = detect_caffeine_keywords(food.get("food_name") or "")
    caffeine_keyword_detected = 1 if caffeine_keywords else 0

    today_caffeine = today_intake.get("caffeine_mg") or 0.0
    today_sugar = today_intake.get("sugar_g") or 0.0
    today_sodium = today_intake.get("sodium_mg") or 0.0

    remaining_caffeine = max(0.0, caffeine_limit - today_caffeine)
    remaining_sugar = max(0.0, sugar_limit - today_sugar)
    remaining_sodium = max(0.0, sodium_limit - today_sodium)

    # ratio: missing 영양소는 0으로 수치 계산 (flag 별도 유지)
    caffeine_for_ratio = food_caffeine if not caffeine_missing else 0.0
    sugar_for_ratio = food_sugar if not sugar_missing else 0.0
    sodium_for_ratio = food_sodium if not sodium_missing else 0.0

    after_caffeine_ratio = (today_caffeine + caffeine_for_ratio) / caffeine_limit
    after_sugar_ratio = (today_sugar + sugar_for_ratio) / sugar_limit
    after_sodium_ratio = (today_sodium + sodium_for_ratio) / sodium_limit

    return [
        pregnancy_week,
        TRIMESTER_ENCODE.get(trimester, 1),
        food_caffeine,
        food_sugar,
        food_sodium,
        food_carb,
        food_protein,
        caffeine_missing,
        sugar_missing,
        sodium_missing,
        caffeine_keyword_detected,
        today_caffeine,
        today_sugar,
        today_sodium,
        remaining_caffeine,
        remaining_sugar,
        remaining_sodium,
        round(after_caffeine_ratio, 4),
        round(after_sugar_ratio, 4),
        round(after_sodium_ratio, 4),
        allergy_match,
    ]


# ── 규칙 기반 안전장치 ──────────────────────────────────────
def apply_safety_guard(
    status: str,
    food: dict,
    allergy_match: int,
    today_intake: dict,
    trimester: str,
) -> str:
    """
    ML 예측 결과에 규칙 기반 안전장치를 적용한다.
    안전 방향(avoid/caution)으로만 올릴 수 있으며, 내리지 않는다.
    """
    limits = DAILY_LIMITS[trimester]
    today_caffeine = today_intake.get("caffeine_mg") or 0.0
    today_sugar = today_intake.get("sugar_g") or 0.0
    today_sodium = today_intake.get("sodium_mg") or 0.0

    caffeine_missing = _is_caffeine_missing(food)
    raw_caffeine = food.get("caffeine_mg")
    food_caffeine = raw_caffeine if (raw_caffeine is not None and not caffeine_missing) else 0.0
    food_sugar = food.get("sugar_g") or 0.0
    food_sodium = food.get("sodium_mg") or 0.0
    caffeine_keywords = detect_caffeine_keywords(food.get("food_name") or "")

    def _upgrade(current: str, target: str) -> str:
        if STATUS_RANK.get(current, 0) < STATUS_RANK.get(target, 0):
            return target
        return current

    # 1. 알레르기 → avoid (무조건)
    if allergy_match:
        return "avoid"

    # 2. 알려진 영양소 기준 초과 → avoid
    caffeine_for_ratio = food_caffeine if not caffeine_missing else 0.0
    after_caffeine_ratio = (today_caffeine + caffeine_for_ratio) / limits["caffeine"]
    after_sugar_ratio = (today_sugar + food_sugar) / limits["sugar"]
    after_sodium_ratio = (today_sodium + food_sodium) / limits["sodium"]

    if after_caffeine_ratio > 1.0 or after_sugar_ratio > 1.0 or after_sodium_ratio > 1.0:
        return "avoid"

    # 3. 카페인 missing + 음식명 키워드 → at least caution (커피·초코 등)
    if caffeine_missing and caffeine_keywords:
        status = _upgrade(status, "caution")

    # 4. 당류 또는 나트륨 missing → at least caution
    if food.get("sugar_g") is None or food.get("sodium_mg") is None:
        status = _upgrade(status, "caution")

    return status


# ── 한국어 이유 생성 ────────────────────────────────────────
def make_reason(
    status: str,
    food: dict,
    today_intake: dict,
    trimester: str,
    allergy_match: int,
) -> str:
    limits = DAILY_LIMITS[trimester]
    today_caffeine = today_intake.get("caffeine_mg") or 0.0
    today_sugar = today_intake.get("sugar_g") or 0.0
    today_sodium = today_intake.get("sodium_mg") or 0.0

    caffeine_missing = _is_caffeine_missing(food)
    raw_caffeine = food.get("caffeine_mg")
    food_caffeine = raw_caffeine if (raw_caffeine is not None and not caffeine_missing) else 0.0
    food_sugar = food.get("sugar_g") or 0.0
    food_sodium = food.get("sodium_mg") or 0.0
    caffeine_keywords = detect_caffeine_keywords(food.get("food_name") or "")

    if allergy_match:
        return "알레르기 정보와 관련될 수 있어 섭취 전 확인이 필요해요."

    if status == "avoid":
        caffeine_for_ratio = food_caffeine if not caffeine_missing else 0.0
        if (today_caffeine + caffeine_for_ratio) / limits["caffeine"] > 1.0:
            return "카페인이 오늘 허용량을 초과할 수 있어 섭취를 권장하지 않아요."
        if (today_sugar + food_sugar) / limits["sugar"] > 1.0:
            return "당류가 오늘 허용량을 초과할 수 있어 섭취를 권장하지 않아요."
        if (today_sodium + food_sodium) / limits["sodium"] > 1.0:
            return "나트륨이 오늘 허용량을 초과할 수 있어 섭취를 권장하지 않아요."
        return "오늘 누적 섭취량 기준으로 이 음식은 비추천이에요."

    if status == "caution":
        if caffeine_missing and caffeine_keywords:
            return "음식명에 카페인 관련 표현이 있어 카페인 함량 확인이 필요해요."
        if food.get("sugar_g") is None or food.get("sodium_mg") is None:
            return "일부 영양성분 정보가 없어 주의가 필요해요."
        if (today_sugar + food_sugar) / limits["sugar"] > 0.7:
            return "당류가 남은 허용량에 비해 높아 주의가 필요해요."
        if (today_sodium + food_sodium) / limits["sodium"] > 0.7:
            return "나트륨이 오늘 기준에 가까워지고 있어요."
        return "오늘 섭취 흐름을 함께 확인해 주세요."

    # possible: 카페인이 실제 값으로 존재하면 카페인 안내 우선
    if not caffeine_missing and food_caffeine > 0:
        return "카페인이 포함되어 있어요. 오늘의 총 카페인 섭취량을 함께 확인하면 섭취 가능해요."
    return "현재 남은 허용량 안에서 비교적 부담이 낮은 음식이에요."


# ── 규칙 기반 폴백 예측 (모델 없을 때) ────────────────────
def _fallback_predict(
    food: dict,
    trimester: str,
    today_intake: dict,
    allergy_match: int,
) -> str:
    limits = DAILY_LIMITS[trimester]
    today_caffeine = today_intake.get("caffeine_mg") or 0.0
    today_sugar = today_intake.get("sugar_g") or 0.0
    today_sodium = today_intake.get("sodium_mg") or 0.0

    caffeine_missing = _is_caffeine_missing(food)
    raw_caffeine = food.get("caffeine_mg")
    food_caffeine = raw_caffeine if (raw_caffeine is not None and not caffeine_missing) else 0.0
    food_sugar = food.get("sugar_g") or 0.0
    food_sodium = food.get("sodium_mg") or 0.0
    caffeine_keywords = detect_caffeine_keywords(food.get("food_name") or "")

    caffeine_for_ratio = food_caffeine if not caffeine_missing else 0.0
    after_caffeine_ratio = (today_caffeine + caffeine_for_ratio) / limits["caffeine"]
    after_sugar_ratio = (today_sugar + food_sugar) / limits["sugar"]
    after_sodium_ratio = (today_sodium + food_sodium) / limits["sodium"]

    if (after_caffeine_ratio > 1.0 or
            after_sugar_ratio > 1.0 or
            after_sodium_ratio > 1.0):
        return "avoid"
    if (after_caffeine_ratio > 0.7 or
            after_sugar_ratio > 0.7 or
            after_sodium_ratio > 0.7):
        return "caution"
    if caffeine_missing and caffeine_keywords:
        return "caution"
    return "possible"


# ── 메인 추천 함수 ─────────────────────────────────────────
def recommend_food(
    food: dict,
    pregnancy_week: int,
    today_intake: dict,
    allergy_match: int,
) -> dict:
    """
    식품 1개에 대한 추천 결과를 반환한다.

    Returns:
        status: possible / caution / avoid
        label: 추천 / 주의 / 비추천 (한국어)
        confidence: 예측 확률 (모델 있을 때만)
        reason: 한국어 이유
        model_available: 모델 파일 사용 여부
    """
    trimester = get_trimester(pregnancy_week)
    confidence: Optional[float] = None

    if _model_available and _model is not None:
        try:
            fv = build_feature_vector(food, pregnancy_week, trimester, today_intake, allergy_match)
            proba = _model.predict_proba([fv])[0]
            classes = list(_model.classes_)
            predicted_idx = int(proba.argmax())
            status = classes[predicted_idx]
            confidence = round(float(proba[predicted_idx]), 4)
        except Exception as e:
            print(f"ML 예측 실패, 규칙 기반 폴백 사용: {e}")
            status = _fallback_predict(food, trimester, today_intake, allergy_match)
            confidence = None
    else:
        status = _fallback_predict(food, trimester, today_intake, allergy_match)

    # 안전장치: ML 결과를 안전 방향으로만 보정
    status = apply_safety_guard(status, food, allergy_match, today_intake, trimester)
    reason = make_reason(status, food, today_intake, trimester, allergy_match)

    return {
        "status": status,
        "label": STATUS_LABEL_KO.get(status, status),
        "confidence": confidence,
        "reason": reason,
        "model_available": _model_available,
    }
