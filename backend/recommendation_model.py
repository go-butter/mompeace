"""
임신 중 식품 추천 규칙 기반 판정 모듈

규칙 기반 로직으로 식품 추천 상태(possible/caution/avoid)를 판정하고
규칙 기반 안전장치를 적용하여 최종 결과를 반환한다.

주의:
- 공식 임신 주차별 의학 기준이 아님
- food_nutrition_api 소스는 카페인 미제공 API → caffeine_mg=0 포함 항상 missing 처리
- caffeine_mg = None 은 missing 으로 처리 (0으로 변환 금지)
"""
from pathlib import Path
from typing import Optional

from backend.food_search_api import detect_caffeine_keywords
from backend.risk import get_trimester

_HERE = Path(__file__).resolve().parent

# 트라이메스터별 1일 허용 기준 (앱 내부 보수적 기준, 공식 의학 기준 아님)
DAILY_LIMITS = {
    "early":  {"caffeine": 200.0, "sugar": 50.0, "sodium": 2000.0},
    "middle": {"caffeine": 200.0, "sugar": 50.0, "sodium": 2000.0},
    "late":   {"caffeine": 200.0, "sugar": 50.0, "sodium": 1500.0},
}

STATUS_LABEL_KO = {"possible": "섭취 가능", "caution": "주의", "avoid": "비추천"}
STATUS_RANK = {"possible": 0, "caution": 1, "avoid": 2}

SENSITIVITY_ADJ_MIN = -0.15
SENSITIVITY_ADJ_MAX = 0.15


def get_effective_limits(trimester: str, user_adj: Optional[dict] = None) -> dict:
    """
    DAILY_LIMITS[trimester]를 사용자별 민감도 조정값으로 스케일링한다.
    user_adj: {"caffeine": float, "sugar": float, "sodium": float}, 각 [-0.15, 0.15] 범위.
    알레르기 일치/절대 초과 같은 하드 안전 규칙에는 영향을 주지 않고,
    그 규칙이 사용하는 비율 계산의 기준값만 조정한다.
    """
    base = DAILY_LIMITS[trimester]
    user_adj = user_adj or {}

    def _scaled(nutrient: str) -> float:
        adj = max(SENSITIVITY_ADJ_MIN, min(SENSITIVITY_ADJ_MAX, user_adj.get(nutrient, 0) or 0))
        return base[nutrient] * (1 + adj)

    return {
        "caffeine": _scaled("caffeine"),
        "sugar": _scaled("sugar"),
        "sodium": _scaled("sodium"),
    }

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


# ── 규칙 기반 안전장치 ──────────────────────────────────────
def apply_safety_guard(
    status: str,
    food: dict,
    allergy_match: int,
    today_intake: dict,
    trimester: str,
    user_adj: Optional[dict] = None,
) -> str:
    """
    ML 예측 결과에 규칙 기반 안전장치를 적용한다.
    안전 방향(avoid/caution)으로만 올릴 수 있으며, 내리지 않는다.
    """
    limits = get_effective_limits(trimester, user_adj)
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

    # 3.5 임신 초기: 카페인 60% 초과 → at least caution
    if trimester == "early":
        early_caffeine_ratio = (today_caffeine + (food_caffeine if not caffeine_missing else 0.0)) / limits["caffeine"]
        if early_caffeine_ratio > 0.6:
            status = _upgrade(status, "caution")

    # 3.6 임신 후기: 나트륨 80% 초과 → at least caution
    if trimester == "late":
        late_sodium_ratio = (today_sodium + food_sodium) / limits["sodium"]
        if late_sodium_ratio > 0.8:
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
    user_adj: Optional[dict] = None,
) -> tuple:
    """반환값: (한국어 이유 메시지, reason_nutrient 태그)"""
    limits = get_effective_limits(trimester, user_adj)
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
        return "알레르기 정보와 관련될 수 있어 섭취 전 확인이 필요해요.", "allergy"

    if status == "avoid":
        caffeine_for_ratio = food_caffeine if not caffeine_missing else 0.0
        if (today_caffeine + caffeine_for_ratio) / limits["caffeine"] > 1.0:
            return "카페인이 오늘 허용량을 초과할 수 있어 섭취를 권장하지 않아요.", "caffeine"
        if (today_sugar + food_sugar) / limits["sugar"] > 1.0:
            return "당류가 오늘 허용량을 초과할 수 있어 섭취를 권장하지 않아요.", "sugar"
        if (today_sodium + food_sodium) / limits["sodium"] > 1.0:
            return "나트륨이 오늘 허용량을 초과할 수 있어 섭취를 권장하지 않아요.", "sodium"
        return "오늘 누적 섭취량 기준으로 이 음식은 비추천이에요.", None

    if status == "caution":
        if caffeine_missing and caffeine_keywords:
            return "음식명에 카페인 관련 표현이 있어 카페인 함량 확인이 필요해요.", "caffeine"
        if food.get("sugar_g") is None or food.get("sodium_mg") is None:
            return "일부 영양성분 정보가 없어 주의가 필요해요.", None
        if (today_sugar + food_sugar) / limits["sugar"] > 0.7:
            return "당류가 남은 허용량에 비해 높아 주의가 필요해요.", "sugar"
        if (today_sodium + food_sodium) / limits["sodium"] > 0.7:
            return "나트륨이 오늘 기준에 가까워지고 있어요.", "sodium"
        return "오늘 섭취 흐름을 함께 확인해 주세요.", None

    # possible: 카페인이 실제 값으로 존재하면 카페인 안내 우선
    if not caffeine_missing and food_caffeine > 0:
        return "카페인이 포함되어 있어요. 오늘의 총 카페인 섭취량을 함께 확인하면 섭취 가능해요.", "caffeine"
    return "현재 남은 허용량 안에서 비교적 부담이 낮은 음식이에요.", None


# ── 규칙 기반 판정 (메인 판단 로직) ────────────────────────
def judge_food_rules(
    food: dict,
    trimester: str,
    today_intake: dict,
    allergy_match: int,
    user_adj: Optional[dict] = None,
) -> str:
    """규칙 기반으로 식품 추천 상태(possible/caution/avoid)를 판정한다."""
    limits = get_effective_limits(trimester, user_adj)
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
    user_adj: Optional[dict] = None,
) -> dict:
    """
    식품 1개에 대한 추천 결과를 반환한다.

    Returns:
        status: possible / caution / avoid
        label: 추천 / 주의 / 비추천 (한국어)
        reason: 한국어 이유
        reason_nutrient: caffeine / sugar / sodium / allergy / None
    """
    trimester = get_trimester(pregnancy_week)

    status = judge_food_rules(food, trimester, today_intake, allergy_match, user_adj)

    # 안전장치: 판정 결과를 안전 방향으로만 보정
    status = apply_safety_guard(status, food, allergy_match, today_intake, trimester, user_adj)
    reason, reason_nutrient = make_reason(status, food, today_intake, trimester, allergy_match, user_adj)

    return {
        "status": status,
        "label": STATUS_LABEL_KO.get(status, status),
        "reason": reason,
        "reason_nutrient": reason_nutrient,
    }
