import sqlite3
from datetime import date

from fastapi import APIRouter, HTTPException, Depends

from backend.database import get_db
from backend.models import PregnancyUpdate
from backend.sensitivity import get_user_adj, recalculate_sensitivity

router = APIRouter()


@router.get("/users/{user_id}")
def get_user(
    user_id: int,
    db: sqlite3.Connection = Depends(get_db)
):
    """사용자 정보 조회"""

    cursor = db.cursor()
    cursor.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
    user = cursor.fetchone()

    if not user:
        raise HTTPException(status_code=404, detail="사용자를 찾을 수 없습니다.")

    user_dict = dict(user)

    # 비밀번호는 응답에서 제외
    user_dict.pop("password", None)

    return user_dict


@router.put("/users/{user_id}/pregnancy")
def update_pregnancy_info(
    user_id: int,
    info: PregnancyUpdate,
    db: sqlite3.Connection = Depends(get_db)
):
    """임신 주차 및 출산 예정일 수정 (부분 업데이트: None인 필드는 기존 값을 유지)"""

    cursor = db.cursor()

    cursor.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
    user = cursor.fetchone()

    if not user:
        raise HTTPException(status_code=404, detail="사용자를 찾을 수 없습니다.")

    # info.pregnancy_week / info.due_date가 None이면 COALESCE가 기존 값을 그대로 유지한다.
    # 두 필드 모두 None인 요청(no-op PUT)도 에러 없이 200으로 현재 값을 반환한다.
    # pregnancy_week/pregnancy_day 중 하나라도 제공되면, 그 시점을 pregnancy_entered_at으로 기록해
    # 이후 실시간 주차 계산의 기준점으로 사용한다.
    entered_at = (
        date.today().isoformat()
        if (info.pregnancy_week is not None or info.pregnancy_day is not None)
        else None
    )

    cursor.execute("""
        UPDATE users
        SET pregnancy_week = COALESCE(?, pregnancy_week),
            pregnancy_day = COALESCE(?, pregnancy_day),
            due_date = COALESCE(?, due_date),
            pregnancy_entered_at = COALESCE(?, pregnancy_entered_at)
        WHERE user_id = ?
    """, (
        info.pregnancy_week,
        info.pregnancy_day,
        info.due_date,
        entered_at,
        user_id
    ))

    db.commit()

    cursor.execute(
        "SELECT pregnancy_week, pregnancy_day, due_date, pregnancy_entered_at FROM users WHERE user_id = ?",
        (user_id,)
    )
    updated = cursor.fetchone()

    return {
        "user_id": user_id,
        "pregnancy_week": updated["pregnancy_week"],
        "pregnancy_day": updated["pregnancy_day"],
        "due_date": updated["due_date"],
        "pregnancy_entered_at": updated["pregnancy_entered_at"],
        "message": "임신 정보 수정 완료"
    }


@router.get("/users/{user_id}/sensitivity")
def get_user_sensitivity(
    user_id: int,
    db: sqlite3.Connection = Depends(get_db)
):
    """사용자의 현재 영양소별 민감도 조정값과 최근 조정 이력을 조회한다."""
    cursor = db.cursor()
    cursor.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
    user = cursor.fetchone()
    if not user:
        raise HTTPException(status_code=404, detail="사용자를 찾을 수 없습니다.")
    user = dict(user)

    cursor.execute(
        """
        SELECT log_id, nutrient, old_adj, new_adj, trigger_reason, created_at
        FROM user_sensitivity_log
        WHERE user_id = ?
        ORDER BY created_at DESC
        LIMIT 20
        """,
        (user_id,),
    )
    history = [dict(r) for r in cursor.fetchall()]

    return {
        "user_id": user_id,
        "sensitivity_adj": get_user_adj(user),
        "history": history,
    }


@router.post("/users/{user_id}/sensitivity/recalculate")
def recalculate_user_sensitivity(
    user_id: int,
    db: sqlite3.Connection = Depends(get_db)
):
    """피드백을 다시 받지 않고도 수동으로 민감도 재계산을 트리거한다 (데모/테스트용)."""
    cursor = db.cursor()
    cursor.execute("SELECT user_id FROM users WHERE user_id = ?", (user_id,))
    if not cursor.fetchone():
        raise HTTPException(status_code=404, detail="사용자를 찾을 수 없습니다.")

    updated_adj = recalculate_sensitivity(user_id, db)
    return {"user_id": user_id, "sensitivity_adj": updated_adj}
