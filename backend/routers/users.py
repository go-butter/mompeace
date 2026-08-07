import sqlite3
from datetime import date
from backend.intake_totals import TRIMESTER_LABELS, get_trimester_limits, resolve_user_nutrition_context

from fastapi import APIRouter, HTTPException, Depends

from backend.database import get_db
from backend.models import NutrientPreferenceUpdate, PregnancyUpdate
from backend.nutrition_constants import parse_selected_nutrients, validate_age_bracket, validate_selected_nutrients
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

    try:
        age_bracket_value = validate_age_bracket(info.age_bracket)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    # info.pregnancy_week / info.due_date / info.age_bracket이 None이면 COALESCE가
    # 기존 값을 그대로 유지한다. 모든 필드가 None인 요청(no-op PUT)도 에러 없이
    # 200으로 현재 값을 반환한다.
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
            pregnancy_entered_at = COALESCE(?, pregnancy_entered_at),
            age_bracket = COALESCE(?, age_bracket)
        WHERE user_id = ?
    """, (
        info.pregnancy_week,
        info.pregnancy_day,
        info.due_date,
        entered_at,
        age_bracket_value,
        user_id
    ))

    db.commit()

    cursor.execute(
        "SELECT pregnancy_week, pregnancy_day, due_date, pregnancy_entered_at, age_bracket FROM users WHERE user_id = ?",
        (user_id,)
    )
    updated = cursor.fetchone()

    return {
        "user_id": user_id,
        "pregnancy_week": updated["pregnancy_week"],
        "pregnancy_day": updated["pregnancy_day"],
        "due_date": updated["due_date"],
        "pregnancy_entered_at": updated["pregnancy_entered_at"],
        "age_bracket": updated["age_bracket"],
        "message": "임신 정보 수정 완료"
    }


@router.put("/users/{user_id}/nutrient-preferences")
def update_nutrient_preferences(
    user_id: int,
    prefs: NutrientPreferenceUpdate,
    db: sqlite3.Connection = Depends(get_db)
):
    """홈 화면 요약에 표시할 선택 영양소 수정 (최대 4개).
    selected_nutrients가 None이면 값을 바꾸지 않고 현재 상태를 그대로 반환한다
    (update_pregnancy_info의 부분 업데이트 방식과 동일)."""

    cursor = db.cursor()

    cursor.execute("SELECT user_id FROM users WHERE user_id = ?", (user_id,))
    if not cursor.fetchone():
        raise HTTPException(status_code=404, detail="사용자를 찾을 수 없습니다.")

    try:
        selected_nutrients_value = validate_selected_nutrients(prefs.selected_nutrients)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    if selected_nutrients_value is not None:
        cursor.execute(
            "UPDATE users SET selected_nutrients = ? WHERE user_id = ?",
            (selected_nutrients_value, user_id),
        )
        db.commit()

    cursor.execute("SELECT selected_nutrients FROM users WHERE user_id = ?", (user_id,))
    updated = cursor.fetchone()

    return {
        "user_id": user_id,
        "selected_nutrients": parse_selected_nutrients(updated["selected_nutrients"]),
        "message": "선택 영양소 수정 완료"
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

@router.get("/users/{user_id}/nutrition-limits")
def get_nutrition_limits(
    user_id: int,
    db: sqlite3.Connection = Depends(get_db)
):
    """마이페이지 '초/중/후기별 제한사항' 화면용 — 3개 트라이메스터 기준을 한 번에 반환.

    각 트라이메스터의 대표 주차(초기 8주/중기 20주/후기 32주)로 get_trimester_limits()를
    호출해 3개 구간 값을 모두 계산한다. current_trimester는 사용자의 실제 임신 주차 기준.
    """
    cursor = db.cursor()
    cursor.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
    user = cursor.fetchone()
    if not user:
        raise HTTPException(status_code=404, detail="사용자를 찾을 수 없습니다.")
    user = dict(user)

    week, age_bracket = resolve_user_nutrition_context(user)
    current_trimester, _ = get_trimester_limits(week, age_bracket)

    representative_weeks = {"early": 8, "middle": 20, "late": 32}
    trimesters = {}
    for key, rep_week in representative_weeks.items():
        trimester_key, limits = get_trimester_limits(rep_week, age_bracket)
        trimesters[key] = {
            "label": TRIMESTER_LABELS[trimester_key],
            **limits,
        }

    return {
        "current_trimester": current_trimester,
        "trimesters": trimesters,
    }