import sqlite3
from datetime import date

from backend.nutrition_constants import (
    BASE_ENERGY_KCAL,
    BASE_PROTEIN_G,
    DAILY_CAFFEINE_LIMIT_MG,
    DAILY_CARB_MINIMUM_G,
    DAILY_SODIUM_LIMIT_MG,
    DAILY_SUGAR_LIMIT_G,
    FAT_ENERGY_RATIO_MAX,
    FAT_ENERGY_RATIO_MIN,
    SATURATED_FAT_ENERGY_RATIO_MAX,
    TRANS_FAT_ENERGY_RATIO_MAX,
    TRIMESTER_ENERGY_ADD_KCAL,
    TRIMESTER_NOTES,
    TRIMESTER_PROTEIN_ADD_G,
)


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


def get_status(value, standard, unknown_count) -> str:
    """단일 영양소 섭취 상태 판정 (safe/caution/avoid/unknown)."""
    if unknown_count > 0:
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
    하한선 미달 상태("low"/"insufficient", 탄수화물·단백질·에너지 등)는 caution과
    동급으로만 취급하며 avoid로는 절대 올라가지 않는다 — 미달은 초과보다 약한 신호로
    다루기로 한 정책 결정.
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


def get_floor_status(value, minimum, unknown_count) -> str:
    """하한선(최소 섭취 권장량) 기준 상태 판정 — 탄수화물/단백질/에너지처럼
    "초과"가 아니라 "미달"이 문제인 영양소용. get_status()의 상한선 판정과는
    방향이 반대이므로 별도 함수로 분리한다.

    sufficient: 최소량 이상 / low: 70% 이상 최소량 미만 / insufficient: 70% 미만
    """
    if unknown_count > 0:
        return "unknown"
    if minimum <= 0:
        return "unknown"

    ratio = value / minimum

    if ratio >= 1.0:
        return "sufficient"
    elif ratio >= 0.7:
        return "low"
    else:
        return "insufficient"


def get_informational_status(value) -> str:
    """콜레스테롤처럼 공식 상한 기준이 없어 safe/caution/avoid 판정 자체를
    하지 않는 영양소용. 값이 있으면 "info"(참고용 표시), 없으면 "unknown"."""
    return "unknown" if value is None else "info"


def get_fat_status(value, energy_total, ratio_min, ratio_max, unknown_count) -> str:
    """총 지방처럼 상한(ratio_max)과 하한(ratio_min)이 모두 있는 "밴드"형 판정.
    총 에너지 섭취량 대비 비율로 기준을 동적으로 계산하므로, 오늘 에너지 섭취가
    없으면(0 이하) 비율 자체를 계산할 수 없어 unknown을 반환한다.

    상한 초과는 get_status()의 기존 safe/caution/avoid 티어를 그대로 재사용하고,
    하한 미달은 별도로 "low"를 반환한다 (미달은 초과보다 약한 신호로 다루는 정책상
    avoid로 올라가지 않음 — compute_overall_status 참고).
    """
    if unknown_count > 0:
        return "unknown"
    if energy_total <= 0:
        return "unknown"

    upper_limit = energy_total * ratio_max
    ceiling_status = get_status(value, upper_limit, 0)
    if ceiling_status in ("caution", "avoid"):
        return ceiling_status

    lower_limit = energy_total * ratio_min
    if value < lower_limit:
        return "low"
    return "safe"


def get_trimester_limits(pregnancy_week: int) -> tuple[str, dict]:
    """트라이메스터 판별 및 1일 허용 기준 조회.

    절대 기준값(카페인/당류/나트륨)은 트라이메스터와 무관하게 항상 동일하다(nutrition_constants 참고).
    트라이메스터별로 달라지는 것은 note(안내 문구)뿐이다.
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
        "protein_g":   BASE_PROTEIN_G + TRIMESTER_PROTEIN_ADD_G[trimester],
        "energy_kcal": BASE_ENERGY_KCAL + TRIMESTER_ENERGY_ADD_KCAL[trimester],
        "fat_ratio_min": FAT_ENERGY_RATIO_MIN,
        "fat_ratio_max": FAT_ENERGY_RATIO_MAX,
        "saturated_fat_ratio_max": SATURATED_FAT_ENERGY_RATIO_MAX,
        "trans_fat_ratio_max": TRANS_FAT_ENERGY_RATIO_MAX,
        "note":        TRIMESTER_NOTES[trimester],
    }
