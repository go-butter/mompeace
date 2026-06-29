import sqlite3
from datetime import date

from fastapi import HTTPException


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


def compute_overall_status(caffeine_status, sugar_status, sodium_status) -> str:
    """카페인/당류/나트륨 상태를 종합한 전체 상태 (avoid > unknown > caution > safe)."""
    statuses = [caffeine_status, sugar_status, sodium_status]

    if "avoid" in statuses:
        return "avoid"
    elif "unknown" in statuses:
        return "unknown"
    elif "caution" in statuses:
        return "caution"
    else:
        return "safe"


def get_trimester_limits(cursor, pregnancy_week: int) -> tuple[str, dict]:
    """트라이메스터 판별 및 pregnancy_limits 조회"""
    if pregnancy_week <= 12:
        trimester = "early"
    elif pregnancy_week <= 27:
        trimester = "middle"
    else:
        trimester = "late"
    cursor.execute("SELECT * FROM pregnancy_limits WHERE trimester = ?", (trimester,))
    limit_row = cursor.fetchone()
    if not limit_row:
        raise HTTPException(status_code=500, detail="임신 주차별 기준 정보를 찾을 수 없습니다.")
    limits = dict(limit_row)
    return trimester, {
        "caffeine_mg": limits["caffeine_limit_mg"],
        "sugar_g":     limits["sugar_caution_g"],
        "sodium_mg":   limits["sodium_caution_mg"],
        "note":        limits["note"],
    }
