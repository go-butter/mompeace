import sqlite3
from datetime import date as date_type

from fastapi import APIRouter, HTTPException, Depends

from backend.database import get_db
from backend.intake_totals import TRIMESTER_LABELS, get_trimester_limits, resolve_user_nutrition_context
from backend.tips_data import COMMON_TIPS, TRIMESTER_TIPS

router = APIRouter()


@router.get("/tips/today/{user_id}")
def get_today_tip(
    user_id: int,
    date: str = None,
    db: sqlite3.Connection = Depends(get_db),
):
    """오늘의 트라이메스터별 팁 + 공통 팁 (홈 화면 정보 라이브러리용)."""
    cursor = db.cursor()
    cursor.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
    user = cursor.fetchone()
    if not user:
        raise HTTPException(status_code=404, detail="사용자를 찾을 수 없습니다.")
    user = dict(user)

    if date:
        try:
            target_date = date_type.fromisoformat(date)
        except ValueError:
            raise HTTPException(status_code=400, detail="날짜 형식이 올바르지 않습니다. YYYY-MM-DD 형식을 사용해 주세요.")
    else:
        target_date = date_type.today()

    week, age_bracket = resolve_user_nutrition_context(user)
    trimester, _ = get_trimester_limits(week, age_bracket)

    # toordinal()은 서버 로컬 타임존 기준 날짜를 그대로 사용한다 — 서버가 KST로
    # 설정되어 있다는 전제이며, 다른 타임존에서 배포되면 자정 근처 회전 시점이 밀린다.
    day_seed = target_date.toordinal()

    trimester_pool = TRIMESTER_TIPS[trimester]
    common_pool = COMMON_TIPS
    trimester_tip = trimester_pool[day_seed % len(trimester_pool)]
    common_tip = common_pool[day_seed % len(common_pool)]

    return {
        "trimester": trimester,
        "trimester_label": TRIMESTER_LABELS[trimester],
        "trimester_tip": trimester_tip,
        "common_tip": common_tip,
    }
