import sqlite3
from datetime import date as date_type, timedelta

from fastapi import APIRouter, HTTPException, Depends

from backend.database import get_db
from backend.models import WaterLogCreate
from backend.nutrition_constants import DAILY_WATER_TARGET_ML

router = APIRouter()

WEEKDAY_LABELS = ["월", "화", "수", "목", "금", "토", "일"]


def _get_percent(value: float, standard: float) -> float:
    if standard <= 0:
        return 0.0
    return round(value / standard * 100, 1)


def fetch_water_summary_for_date(user_id: int, target_date: str, db: sqlite3.Connection) -> dict:
    """주어진 날짜의 수분 섭취 기록 + 합계/퍼센트 계산: Water Diary 화면용"""
    cursor = db.cursor()

    cursor.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
    if not cursor.fetchone():
        raise HTTPException(status_code=404, detail="사용자를 찾을 수 없습니다.")

    cursor.execute("""
        SELECT log_id, amount_ml, logged_at
        FROM water_log
        WHERE user_id = ? AND DATE(logged_at) = ?
        ORDER BY logged_at ASC
    """, (user_id, target_date))

    logs = []
    total_ml = 0.0
    for row in cursor.fetchall():
        row = dict(row)
        total_ml += row["amount_ml"]
        logs.append({
            "log_id": row["log_id"],
            "amount_ml": row["amount_ml"],
            "logged_at": row["logged_at"],
            "time": row["logged_at"][11:16] if row["logged_at"] else None,
        })

    return {
        "user_id": user_id,
        "date": target_date,
        "target_ml": DAILY_WATER_TARGET_ML,
        "total_ml": round(total_ml, 1),
        "percent": _get_percent(total_ml, DAILY_WATER_TARGET_ML),
        "logs": logs,
    }


@router.post("/water-log")
def create_water_log(
    log: WaterLogCreate,
    db: sqlite3.Connection = Depends(get_db)
):
    """수분 섭취 기록 저장"""
    cursor = db.cursor()

    cursor.execute("SELECT * FROM users WHERE user_id = ?", (log.user_id,))
    if not cursor.fetchone():
        raise HTTPException(status_code=404, detail="사용자를 찾을 수 없습니다.")

    if log.logged_at is not None:
        cursor.execute(
            "INSERT INTO water_log (user_id, amount_ml, logged_at) VALUES (?, ?, ?)",
            (log.user_id, log.amount_ml, log.logged_at),
        )
    else:
        cursor.execute(
            "INSERT INTO water_log (user_id, amount_ml) VALUES (?, ?)",
            (log.user_id, log.amount_ml),
        )

    new_log_id = cursor.lastrowid
    db.commit()

    return {"log_id": new_log_id, "message": "수분 섭취 기록 완료"}


@router.get("/water-log/today/{user_id}")
def get_today_water_log(
    user_id: int,
    db: sqlite3.Connection = Depends(get_db)
):
    """오늘 수분 섭취 기록 + 합계 조회: Water Diary 화면용"""
    today = date_type.today().isoformat()
    return fetch_water_summary_for_date(user_id, today, db)


@router.get("/water-log/by-date/{user_id}")
def get_water_log_by_date(
    user_id: int,
    date: str = None,
    db: sqlite3.Connection = Depends(get_db)
):
    """임의 날짜의 수분 섭취 기록 조회. date 미지정 시 오늘."""
    if date:
        try:
            target_date = date_type.fromisoformat(date)
        except ValueError:
            raise HTTPException(status_code=400, detail="날짜 형식이 올바르지 않습니다. YYYY-MM-DD 형식을 사용해 주세요.")
    else:
        target_date = date_type.today()

    return fetch_water_summary_for_date(user_id, target_date.isoformat(), db)


def fetch_water_totals_by_day(
    user_id: int, monday: date_type, sunday: date_type, db: sqlite3.Connection
) -> list[dict]:
    """기간 내 날짜별 수분 합계. 범위 쿼리 한 번 + 파이썬 버킷팅

    (routers/report.py의 _aggregate_week와 같은 패턴 — 날짜마다 쿼리를 돌리지 않는다).
    표시용 플래그(hit_target/is_today)는 호출부의 책임이라 여기서 붙이지 않는다.
    """
    cursor = db.cursor()
    cursor.execute("""
        SELECT amount_ml, DATE(logged_at) AS log_date
        FROM water_log
        WHERE user_id = ? AND DATE(logged_at) BETWEEN ? AND ?
    """, (user_id, monday.isoformat(), sunday.isoformat()))
    rows = [dict(r) for r in cursor.fetchall()]

    days = []
    for i in range((sunday - monday).days + 1):
        d_str = (monday + timedelta(days=i)).isoformat()
        day_rows = [r for r in rows if r["log_date"] == d_str]
        days.append({
            "label": WEEKDAY_LABELS[i] if i < len(WEEKDAY_LABELS) else None,
            "date": d_str,
            "amount_ml": round(sum(r["amount_ml"] for r in day_rows), 1),
            "log_count": len(day_rows),
        })
    return days


@router.get("/water-log/week/{user_id}")
def get_water_log_week(
    user_id: int,
    date: str = None,
    db: sqlite3.Connection = Depends(get_db)
):
    """월~일 7일간 요일별 수분 섭취 합계 조회: 주간 차트용. date는 대상 주에 속한 임의 날짜(기본값 오늘)."""
    cursor = db.cursor()

    cursor.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
    if not cursor.fetchone():
        raise HTTPException(status_code=404, detail="사용자를 찾을 수 없습니다.")

    if date:
        try:
            target_date = date_type.fromisoformat(date)
        except ValueError:
            raise HTTPException(status_code=400, detail="날짜 형식이 올바르지 않습니다. YYYY-MM-DD 형식을 사용해 주세요.")
    else:
        target_date = date_type.today()

    monday = target_date - timedelta(days=target_date.weekday())
    sunday = monday + timedelta(days=6)
    today_str = date_type.today().isoformat()

    days = [
        {
            "label": day["label"],
            "date": day["date"],
            "amount_ml": day["amount_ml"],
            "hit_target": day["amount_ml"] >= DAILY_WATER_TARGET_ML,
            "is_today": day["date"] == today_str,
        }
        for day in fetch_water_totals_by_day(user_id, monday, sunday, db)
    ]

    return {
        "user_id": user_id,
        "date_range": {
            "start": monday.isoformat(),
            "end": sunday.isoformat(),
        },
        "target_ml": DAILY_WATER_TARGET_ML,
        "days": days,
    }


@router.delete("/water-log/{log_id}")
def delete_water_log(
    log_id: int,
    user_id: int,
    db: sqlite3.Connection = Depends(get_db)
):
    """수분 섭취 기록 삭제 (본인 기록만 삭제 가능)"""
    cursor = db.cursor()
    cursor.execute(
        "SELECT log_id FROM water_log WHERE log_id = ? AND user_id = ?",
        (log_id, user_id)
    )
    if not cursor.fetchone():
        raise HTTPException(status_code=404, detail="해당 기록을 찾을 수 없습니다.")

    cursor.execute("DELETE FROM water_log WHERE log_id = ? AND user_id = ?", (log_id, user_id))
    db.commit()

    return {"log_id": log_id, "message": "수분 섭취 기록이 삭제되었습니다."}
