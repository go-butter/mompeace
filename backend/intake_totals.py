import sqlite3
from datetime import date

from backend.nutrition_constants import (
    BASE_ENERGY_KCAL,
    BASE_PROTEIN_G,
    DAILY_CAFFEINE_LIMIT_MG,
    DAILY_CARB_MINIMUM_G,
    DAILY_SODIUM_LIMIT_MG,
    DAILY_SUGAR_LIMIT_G,
    DEFAULT_AGE_BRACKET,
    FAT_ENERGY_RATIO_MAX,
    FAT_ENERGY_RATIO_MIN,
    KCAL_PER_GRAM_FAT,
    SATURATED_FAT_ENERGY_RATIO_MAX,
    TRANS_FAT_ENERGY_RATIO_MAX,
    TRIMESTER_ENERGY_ADD_KCAL,
    TRIMESTER_NOTES,
    TRIMESTER_PROTEIN_ADD_G,
)
from backend.risk import calculate_current_pregnancy_age


def compute_today_intake_totals(user_id: int, db: sqlite3.Connection) -> dict:
    """오늘 누적 섭취량(카페인/당류/나트륨)을 합산한다. /recommendations, 음식 기록 추천 판정에서 공유."""
    cursor = db.cursor()
    today = date.today().isoformat()
    cursor.execute("""
        SELECT
            COALESCE(SUM(caffeine_mg), 0) AS total_caffeine,
            COALESCE(SUM(CASE WHEN caffeine_mg IS NULL THEN 1 ELSE 0 END), 0) AS unknown_caffeine_count,
            COALESCE(SUM(sugar_g), 0)    AS total_sugar,
            COALESCE(SUM(CASE WHEN sugar_g IS NULL THEN 1 ELSE 0 END), 0) AS unknown_sugar_count,
            COALESCE(SUM(sodium_mg), 0)  AS total_sodium,
            COALESCE(SUM(CASE WHEN sodium_mg IS NULL THEN 1 ELSE 0 END), 0) AS unknown_sodium_count
        FROM food_log
        WHERE user_id = ? AND DATE(eaten_at) = ?
    """, (user_id, today))
    row = dict(cursor.fetchone())
    return {
        "caffeine_mg": row["total_caffeine"],
        "sugar_g": row["total_sugar"],
        "sodium_mg": row["total_sodium"],
        "unknown_caffeine_count": row["unknown_caffeine_count"],
        "unknown_sugar_count": row["unknown_sugar_count"],
        "unknown_sodium_count": row["unknown_sodium_count"],
    }


def _is_data_unresolved(known_count: int, logged_count: int) -> bool:
    """오늘 무언가는 기록됐는데(logged_count>0) 이 영양소 값이 하나도 확인되지
    않은 경우(known_count==0)에만 unknown으로 판정한다. 아예 기록이 없는 날
    (logged_count==0)은 이 함수가 관여하지 않고, 호출부의 기존 기본 판정
    (ceiling은 0으로 계산되어 safe, floor/band는 각자의 기존 로직)을 그대로 따른다 —
    그렇지 않으면 음식을 하나도 기록하지 않은 날조차 "정보없음"으로 보이게 된다.
    """
    return logged_count > 0 and known_count == 0


def get_status(value, standard, known_count, logged_count) -> str:
    """단일 영양소 섭취 상태 판정 (safe/caution/avoid/unknown)."""
    if _is_data_unresolved(known_count, logged_count):
        return "unknown"

    if standard <= 0:
        return "unknown"

    ratio = value / standard

    if ratio <= 0.7:
        return "safe"
    elif ratio <= 1.0:
        return "caution"
    else:
        return "avoid"


def compute_overall_status(*statuses) -> str:
    """여러 영양소 상태를 종합한 전체 상태 (avoid > unknown > caution > safe).

    "info"(콜레스테롤처럼 판정 자체가 없는 참고용 수치)는 집계에서 제외한다.
    하한선 미달 상태("insufficient", 탄수화물·단백질·에너지·물 — 이진 판정)와
    "low"(지방 밴드 판정의 하한 쪽 전용)는 caution과 동급으로만 취급하며 avoid로는
    절대 올라가지 않는다 — 미달은 초과보다 약한 신호로 다루기로 한 정책 결정.
    """
    filtered = [s for s in statuses if s is not None and s != "info"]
    if not filtered:
        return "safe"

    if "avoid" in filtered:
        return "avoid"
    if "unknown" in filtered:
        return "unknown"

    CAUTION_EQUIVALENT = {"caution", "low", "insufficient"}
    if any(s in CAUTION_EQUIVALENT for s in filtered):
        return "caution"
    return "safe"


def get_floor_status(value, minimum, known_count, logged_count) -> str:
    """하한선(최소 섭취 권장량) 기준 상태 판정 — 탄수화물/단백질/에너지처럼
    "초과"가 아니라 "미달"이 문제인 영양소용. get_status()의 상한선 판정과는
    방향이 반대이므로 별도 함수로 분리한다.

    공식 기준이 목표치 하나뿐이라(완충 구간에 대한 별도 기준이 없음) 중간 단계
    없는 이진 판정이다: sufficient: 최소량 이상 / insufficient: 최소량 미만
    """
    if _is_data_unresolved(known_count, logged_count):
        return "unknown"
    if minimum <= 0:
        return "unknown"

    ratio = value / minimum

    if ratio >= 1.0:
        return "sufficient"
    else:
        return "insufficient"


def get_informational_status(value) -> str:
    """공식 상한 기준이 없어 safe/caution/avoid 판정 자체를 하지 않는 영양소용.
    값이 있으면 "info"(참고용 표시), 없으면 "unknown".

    현재 호출하는 곳은 없다(콜레스테롤이 판정 대상에서 제외되며 유일한 사용처가
    사라짐) — 향후 공식 기준이 없는 영양소가 다시 생기면 재사용할 수 있어 남겨둔다."""
    return "unknown" if value is None else "info"


def get_fat_status(value, energy_total, ratio_min, ratio_max, known_count, logged_count) -> str:
    """총 지방처럼 상한(ratio_max)과 하한(ratio_min)이 모두 있는 "밴드"형 판정.
    총 에너지 섭취량 대비 비율로 기준을 동적으로 계산하므로, 오늘 에너지 섭취가
    없으면(0 이하) 비율 자체를 계산할 수 없어 unknown을 반환한다.

    energy_total(kcal) * ratio는 kcal 단위이므로, food_log에 그램 단위로 저장된
    value와 비교하려면 KCAL_PER_GRAM_FAT(9kcal/g)로 나눠 그램 기준으로 환산해야
    한다 — 환산 없이 비교하면 사실상 도달 불가능한 상한과, 정상 섭취량도 걸리는
    하한이 되어버린다.

    상한 초과는 get_status()의 기존 safe/caution/avoid 티어를 그대로 재사용하고,
    하한 미달은 별도로 "low"를 반환한다 (미달은 초과보다 약한 신호로 다루는 정책상
    avoid로 올라가지 않음 — compute_overall_status 참고).
    """
    if _is_data_unresolved(known_count, logged_count):
        return "unknown"
    if energy_total <= 0:
        return "unknown"

    upper_limit_g = energy_total * ratio_max / KCAL_PER_GRAM_FAT
    ceiling_status = get_status(value, upper_limit_g, known_count=1, logged_count=1)
    if ceiling_status in ("caution", "avoid"):
        return ceiling_status

    lower_limit_g = energy_total * ratio_min / KCAL_PER_GRAM_FAT
    if value < lower_limit_g:
        return "low"
    return "safe"


def get_iron_status(value, recommended, upper_limit, known_count, logged_count) -> str:
    """철분처럼 권장량(하한)과 상한섭취량이 모두 있는 "밴드"형 판정.
    fat(get_fat_status)과 달리 절대 mg 기준이라 에너지 비율 환산이 필요 없다.
    """
    if _is_data_unresolved(known_count, logged_count):
        return "unknown"

    ceiling_status = get_status(value, upper_limit, known_count=1, logged_count=1)
    if ceiling_status in ("caution", "avoid"):
        return ceiling_status

    if value < recommended:
        return "low"
    return "safe"


_CEILING_LABELS = {"safe": "여유", "caution": "안전", "avoid": "위험", "unknown": "정보없음"}
_FLOOR_LABELS = {"sufficient": "충분", "insufficient": "부족", "unknown": "정보없음"}
_BAND_LABELS = {"safe": "여유", "low": "부족", "caution": "안전", "avoid": "위험", "unknown": "정보없음"}


def simplified_status_label(nutrient_type: str, status: str) -> str | None:
    """홈 화면 요약 카드용 간소화 라벨 (여유/안전/위험/정보없음 계열).

    Food Diary용 status_label()(routers/intake.py, caution="주의")과는 별도의
    홈 화면 전용 어휘다.

    nutrient_type:
    - "ceiling": get_status() 결과용 (caffeine/sugar/sodium)
    - "floor": get_floor_status() 결과용 (carbohydrate/protein/energy/water) — 공식
      기준이 목표치 하나뿐이라 완충 구간 없는 이진 판정(충분/부족)이다
    - "band": get_fat_status()/get_iron_status() 결과용 (fat/iron) — safe/caution/avoid는
      ceiling과 같은 어휘, low(하한 미달)는 floor와 같은 의미이므로 같은 단어("부족")를 재사용한다
    - "informational": get_informational_status() 결과용 (공식 상한 기준이 없는 영양소) — "info"는
      판정 자체가 없으므로 라벨 없이 None을 반환한다 (숫자만 표시, 칩 없음). 현재 실제 호출처 없음.
    """
    if nutrient_type == "ceiling":
        return _CEILING_LABELS.get(status, "정보없음")
    if nutrient_type == "floor":
        return _FLOOR_LABELS.get(status, "정보없음")
    if nutrient_type == "band":
        return _BAND_LABELS.get(status, "정보없음")
    if nutrient_type == "informational":
        return None if status == "info" else "정보없음"
    raise ValueError(f"알 수 없는 nutrient_type: {nutrient_type}")


TRIMESTER_LABELS = {"early": "임신 초기", "middle": "임신 중기", "late": "임신 후기"}


def get_trimester_limits(pregnancy_week: int, age_bracket: str = DEFAULT_AGE_BRACKET) -> tuple[str, dict]:
    """트라이메스터 판별 및 1일 허용 기준 조회.

    절대 기준값(카페인/당류/나트륨)은 트라이메스터와 무관하게 항상 동일하다(nutrition_constants 참고).
    에너지/단백질만 age_bracket("19-29"/"30-49")에 따라 baseline이 달라진다.
    트라이메스터별로 달라지는 것은 (에너지/단백질 가산량과) note(안내 문구)다.
    """
    if pregnancy_week <= 12:
        trimester = "early"
    elif pregnancy_week <= 27:
        trimester = "middle"
    else:
        trimester = "late"
    return trimester, {
        "caffeine_mg": DAILY_CAFFEINE_LIMIT_MG,
        "sugar_g":     DAILY_SUGAR_LIMIT_G,
        "sodium_mg":   DAILY_SODIUM_LIMIT_MG,
        "carbohydrate_g": DAILY_CARB_MINIMUM_G,
        "protein_g":   BASE_PROTEIN_G[age_bracket] + TRIMESTER_PROTEIN_ADD_G[trimester],
        "energy_kcal": BASE_ENERGY_KCAL[age_bracket] + TRIMESTER_ENERGY_ADD_KCAL[trimester],
        "fat_ratio_min": FAT_ENERGY_RATIO_MIN,
        "fat_ratio_max": FAT_ENERGY_RATIO_MAX,
        "saturated_fat_ratio_max": SATURATED_FAT_ENERGY_RATIO_MAX,
        "trans_fat_ratio_max": TRANS_FAT_ENERGY_RATIO_MAX,
        "note":        TRIMESTER_NOTES[trimester],
    }


def resolve_user_nutrition_context(user: dict) -> tuple[int, str]:
    """사용자 row에서 get_trimester_limits()에 바로 넘길 (임신 주차, 나이대)를 계산한다.

    임신 주차는 calculate_current_pregnancy_age()로 "오늘" 기준 값을 계산하고,
    미입력이면 20주로 대체한다. 나이대는 미입력(NULL)이면 DEFAULT_AGE_BRACKET으로
    대체한다 — 기존 고정 baseline과 동일해 회귀가 없다.
    """
    computed_age = calculate_current_pregnancy_age(
        user.get("pregnancy_week"), user.get("pregnancy_day"), user.get("pregnancy_entered_at")
    )
    week = computed_age["week"] or 20
    age_bracket = user.get("age_bracket") or DEFAULT_AGE_BRACKET
    return week, age_bracket
