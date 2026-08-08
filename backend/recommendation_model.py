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

from backend.caffeine_relevance import (
    TIER_CAFFEINE_POSSIBLE,
    classify_caffeine_relevance,
)
from backend.food_search_api import detect_caffeine_keywords
from backend.nutrition_constants import (
    DAILY_CAFFEINE_LIMIT_MG,
    DAILY_SODIUM_LIMIT_MG,
    DAILY_SUGAR_LIMIT_G,
)
from backend.risk import get_trimester

_HERE = Path(__file__).resolve().parent

# 1일 허용 기준 (앱 내부 보수적 기준, 공식 의학 기준 아님). 트라이메스터와 무관하게 항상 동일하며,
# 트라이메스터는 apply_safety_guard()의 caution 민감도(early 카페인 60%, late 나트륨 80%)에만 영향을 준다.
DAILY_LIMITS = {
    "caffeine": DAILY_CAFFEINE_LIMIT_MG,
    "sugar": DAILY_SUGAR_LIMIT_G,
    "sodium": DAILY_SODIUM_LIMIT_MG,
}

STATUS_LABEL_KO = {"possible": "섭취 가능", "caution": "주의", "avoid": "비추천"}
STATUS_RANK = {"possible": 0, "caution": 1, "avoid": 2}

SENSITIVITY_ADJ_MIN = -0.15
SENSITIVITY_ADJ_MAX = 0.15


def get_effective_limits(user_adj: Optional[dict] = None) -> dict:
    """
    DAILY_LIMITS를 사용자별 민감도 조정값으로 스케일링한다.
    user_adj: {"caffeine": float, "sugar": float, "sodium": float}, 각 [-0.15, 0.15] 범위.
    알레르기 일치/절대 초과 같은 하드 안전 규칙에는 영향을 주지 않고,
    그 규칙이 사용하는 비율 계산의 기준값만 조정한다.
    """
    base = DAILY_LIMITS
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
    dish_db_download 는 caffeine_mg is None 인 경우에만 missing.
    """
    data_source = food.get("data_source") or ""
    if data_source in ("food_nutrition_api", "processed_food_db_download"):
        return True
    return food.get("caffeine_mg") is None


def _caffeine_tier(food: dict) -> str:
    """식품 분류 기준 카페인 관련성 티어 (backend/caffeine_relevance.py).

    _is_caffeine_missing()과는 서로 다른 질문에 답한다: 저쪽은 "이 행의 카페인 수치를
    믿고 쓸 수 있는가", 이쪽은 "이 종류의 음식에서 카페인이 애초에 의미가 있는가".
    두 판정을 함께 써야 "정보 없음"과 "확인된 0"을 구분할 수 있다.
    """
    return classify_caffeine_relevance(food.get("category"), food.get("subcategory"))


# ── 규칙 기반 안전장치 ──────────────────────────────────────
def apply_safety_guard(
    status: str,
    food: dict,
    today_intake: dict,
    trimester: str,
    user_adj: Optional[dict] = None,
) -> str:
    """
    ML 예측 결과에 규칙 기반 안전장치를 적용한다.
    안전 방향(avoid/caution)으로만 올릴 수 있으며, 내리지 않는다.
    """
    limits = get_effective_limits(user_adj)
    today_caffeine = today_intake.get("caffeine_mg") or 0.0
    today_sugar = today_intake.get("sugar_g") or 0.0
    today_sodium = today_intake.get("sodium_mg") or 0.0

    caffeine_missing = _is_caffeine_missing(food)
    raw_caffeine = food.get("caffeine_mg")
    food_caffeine = raw_caffeine if (raw_caffeine is not None and not caffeine_missing) else 0.0
    food_sugar = food.get("sugar_g") or 0.0
    food_sodium = food.get("sodium_mg") or 0.0
    caffeine_keywords = detect_caffeine_keywords(food.get("food_name") or "")
    caffeine_tier = _caffeine_tier(food)

    def _upgrade(current: str, target: str) -> str:
        if STATUS_RANK.get(current, 0) < STATUS_RANK.get(target, 0):
            return target
        return current

    # 1. 알려진 영양소 기준 초과 → avoid
    caffeine_for_ratio = food_caffeine if not caffeine_missing else 0.0
    after_caffeine_ratio = (today_caffeine + caffeine_for_ratio) / limits["caffeine"]
    after_sugar_ratio = (today_sugar + food_sugar) / limits["sugar"]
    after_sodium_ratio = (today_sodium + food_sodium) / limits["sodium"]

    if after_caffeine_ratio > 1.0 or after_sugar_ratio > 1.0 or after_sodium_ratio > 1.0:
        return "avoid"

    # 3. 카페인 missing + 음식명 키워드 → at least caution (커피·초코 등)
    #    [키워드 규칙 티어 게이트 — make_reason에도 같은 표시의 한 곳이 더 있다.
    #     이 두 곳만 되돌리면 키워드 규칙은 예전처럼 티어와 무관하게 동작한다]
    #    FREE/NOT_MEASURED 식품군에서는 발동하지 않는다. 게이트가 없으면 같은 음식에
    #    대해 티어는 "확인된 0", 키워드는 "카페인 있을 수 있음"이라고 서로 반대로
    #    말하게 된다 — 실제로 빵 및 과자류 카페인 NULL 8,427행 중 419행(5.0%)이
    #    모카빵·초코소라빵처럼 맛 표현 때문에 키워드에 걸리고 있었다.
    if caffeine_missing and caffeine_keywords and caffeine_tier == TIER_CAFFEINE_POSSIBLE:
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

    # 5. 카페인 정보 없음 + 카페인이 들어갈 수 있는 식품군 → at least caution
    #    4번(당류·나트륨 missing)과 같은 취지의 규칙이다. 카페인만 이 보호가 없어서
    #    NULL이 조용히 0으로 계산돼 왔고, 그 결과 "확인된 0"과 "정보 없음"이 출력에서
    #    구분되지 않았다 (실측 기준 possible 판정의 84%가 카페인 미측정 상태였다).
    #    raw None이 아니라 _is_caffeine_missing()으로 판단한다 — 카페인 미제공 소스의
    #    값도 믿을 수 없는 값이므로 같은 취급을 받아야 하고, 이 파일 안에 "missing"의
    #    정의가 두 벌 생기는 것을 막기 위해서다.
    if caffeine_missing and caffeine_tier == TIER_CAFFEINE_POSSIBLE:
        status = _upgrade(status, "caution")

    return status


# ── 한국어 이유 생성 ────────────────────────────────────────
def make_reason(
    status: str,
    food: dict,
    today_intake: dict,
    trimester: str,
    user_adj: Optional[dict] = None,
) -> tuple:
    """반환값: (한국어 이유 메시지, reason_nutrient 태그)"""
    limits = get_effective_limits(user_adj)
    today_caffeine = today_intake.get("caffeine_mg") or 0.0
    today_sugar = today_intake.get("sugar_g") or 0.0
    today_sodium = today_intake.get("sodium_mg") or 0.0

    caffeine_missing = _is_caffeine_missing(food)
    raw_caffeine = food.get("caffeine_mg")
    food_caffeine = raw_caffeine if (raw_caffeine is not None and not caffeine_missing) else 0.0
    food_sugar = food.get("sugar_g") or 0.0
    food_sodium = food.get("sodium_mg") or 0.0
    caffeine_keywords = detect_caffeine_keywords(food.get("food_name") or "")
    caffeine_tier = _caffeine_tier(food)

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
        if not caffeine_missing and (today_caffeine + food_caffeine) / limits["caffeine"] > 0.7:
            return "카페인이 남은 허용량에 비해 높아 주의가 필요해요.", "caffeine"
        if (today_sugar + food_sugar) / limits["sugar"] > 0.7:
            return "당류가 남은 허용량에 비해 높아 주의가 필요해요.", "sugar"
        if (today_sodium + food_sodium) / limits["sodium"] > 0.7:
            return "나트륨이 오늘 기준에 가까워지고 있어요.", "sodium"
        # [키워드 규칙 티어 게이트 — apply_safety_guard에 같은 표시의 한 곳이 더 있다]
        if caffeine_missing and caffeine_keywords and caffeine_tier == TIER_CAFFEINE_POSSIBLE:
            return "음식명에 카페인 관련 표현이 있어 카페인 함량 확인이 필요해요.", "caffeine"
        # 이름에 단서가 없어도 식품군 자체가 카페인을 가질 수 있으면 카페인을 지목한다.
        # 아래 "일부 영양성분" 문구보다 먼저 온다 — 어떤 성분인지 아는 경우에 굳이
        # 뭉뚱그린 문구를 쓸 이유가 없기 때문이다.
        if caffeine_missing and caffeine_tier == TIER_CAFFEINE_POSSIBLE:
            return "카페인이 들어 있을 수 있는데 함량 정보가 없어요. 오늘 카페인 섭취량을 함께 확인해 주세요.", "caffeine"
        if food.get("sugar_g") is None or food.get("sodium_mg") is None:
            return "일부 영양성분 정보가 없어 주의가 필요해요.", None
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
    user_adj: Optional[dict] = None,
) -> str:
    limits = get_effective_limits(user_adj)
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


def recommend_food(
    food: dict,
    pregnancy_week: int,
    today_intake: dict,
    user_adj: Optional[dict] = None,
) -> dict:
    """
    식품 1개에 대한 추천 결과를 반환한다.

    Returns:
        status: possible / caution / avoid
        label: 추천 / 주의 / 비추천 (한국어)
        reason: 한국어 이유
        reason_nutrient: caffeine / sugar / sodium / None
    """
    trimester = get_trimester(pregnancy_week)

    status = judge_food_rules(food, trimester, today_intake, user_adj)

    # 안전장치: 판정 결과를 안전 방향으로만 보정
    status = apply_safety_guard(status, food, today_intake, trimester, user_adj)
    reason, reason_nutrient = make_reason(status, food, today_intake, trimester, user_adj)

    return {
        "status": status,
        "label": STATUS_LABEL_KO.get(status, status),
        "reason": reason,
        "reason_nutrient": reason_nutrient,
    }