import sqlite3

from fastapi import APIRouter, HTTPException, Depends

from backend.database import get_db, cleanup_expired_food_logs
from backend.models import PremiumUpgradeRequest, PremiumStatusResponse
from backend.risk import calculate_current_pregnancy_age
from backend.intake_totals import get_trimester_limits

router = APIRouter()


@router.get("/premium/status/{user_id}", response_model=PremiumStatusResponse)
def get_premium_status(
    user_id: int,
    db: sqlite3.Connection = Depends(get_db)
):
    """프리미엄 가입 여부 확인"""
    cursor = db.cursor()
    cursor.execute("SELECT user_id, is_premium, premium_started_at, premium_updated_at FROM users WHERE user_id = ?", (user_id,))
    user = cursor.fetchone()
    if not user:
        raise HTTPException(status_code=404, detail="사용자를 찾을 수 없습니다.")
    user = dict(user)
    is_premium = bool(user.get("is_premium"))
    if is_premium:
        return {
            "user_id": user_id,
            "is_premium": True,
            "premium_started_at": user.get("premium_started_at"),
            "premium_updated_at": user.get("premium_updated_at"),
            "message": "프리미엄 회원입니다.",
        }
    return {
        "user_id": user_id,
        "is_premium": False,
        "message": "프리미엄 리포트는 유료 회원 전용 기능입니다.",
    }


@router.post("/premium/upgrade")
def upgrade_to_premium(
    req: PremiumUpgradeRequest,
    db: sqlite3.Connection = Depends(get_db)
):
    """프리미엄 전환 (시뮬레이션, 실제 결제 없음)"""
    if not req.agree:
        raise HTTPException(status_code=400, detail="동의 항목을 체크해야 프리미엄으로 전환됩니다.")
    cursor = db.cursor()
    cursor.execute("SELECT user_id, is_premium, premium_started_at FROM users WHERE user_id = ?", (req.user_id,))
    user = cursor.fetchone()
    if not user:
        raise HTTPException(status_code=404, detail="사용자를 찾을 수 없습니다.")
    user = dict(user)
    # premium_started_at은 처음 전환 시에만 기록
    if user.get("premium_started_at"):
        cursor.execute("""
            UPDATE users
            SET is_premium = 1, premium_updated_at = datetime('now')
            WHERE user_id = ?
        """, (req.user_id,))
    else:
        cursor.execute("""
            UPDATE users
            SET is_premium = 1,
                premium_started_at = datetime('now'),
                premium_updated_at = datetime('now')
            WHERE user_id = ?
        """, (req.user_id,))
    db.commit()
    return {
        "user_id": req.user_id,
        "is_premium": True,
        "message": "프리미엄 회원으로 전환되었습니다.",
    }


@router.post("/premium/cancel")
def cancel_premium(
    req: PremiumUpgradeRequest,
    db: sqlite3.Connection = Depends(get_db)
):
    """프리미엄 해지 (로그 즉시 삭제 없음, 다음 cleanup 시 24시간 기준 적용)"""
    cursor = db.cursor()
    cursor.execute("SELECT user_id FROM users WHERE user_id = ?", (req.user_id,))
    if not cursor.fetchone():
        raise HTTPException(status_code=404, detail="사용자를 찾을 수 없습니다.")
    cursor.execute("""
        UPDATE users
        SET is_premium = 0, premium_updated_at = datetime('now')
        WHERE user_id = ?
    """, (req.user_id,))
    db.commit()
    return {
        "user_id": req.user_id,
        "is_premium": False,
        "message": "프리미엄이 해지되었습니다.",
    }


def _get_percent(value: float, standard: float) -> float:
    if standard <= 0:
        return 0.0
    return round(value / standard * 100, 1)


def _build_daily_ai_summary(
    caffeine_pct: float,
    sugar_pct: float,
    sodium_pct: float,
    slot_scores: dict,   # {"새벽": score, "오전": score, ...}
) -> dict:
    messages = []

    # 최다 섭취 시간대 (정규화 점수 기준)
    best_slot = max(slot_scores, key=lambda k: slot_scores[k])
    if slot_scores[best_slot] > 0:
        messages.append(f"{best_slot} 시간대에 섭취가 가장 많았어요.")

    if caffeine_pct >= 70:
        messages.append("카페인 섭취량이 기준에 가까워지고 있어요.")
    if sugar_pct >= 70:
        messages.append("당류 섭취량이 높은 편이에요. 달콤한 간식은 조금 조절해 주세요.")
    if sodium_pct >= 70:
        messages.append("나트륨 수치가 높아지고 있어요. 짠 음식은 조금 조심해 주세요.")

    if not any([caffeine_pct >= 70, sugar_pct >= 70, sodium_pct >= 70]):
        messages.append("오늘은 전반적으로 기준 이내에서 섭취했어요.")

    return {"title": "AI 분석 요약", "messages": messages}


def _build_weekly_ai_summary(
    caffeine_avg_pct: float,
    sugar_avg_pct: float,
    sodium_avg_pct: float,
    day_scores: list,   # [{"label": "월", "score": float}, ...]
) -> dict:
    messages = []

    # 최다 섭취 요일 (정규화 점수 합산 기준)
    data_days = [d for d in day_scores if d["score"] > 0]
    if len(data_days) >= 2:
        best_day = max(data_days, key=lambda d: d["score"])
        messages.append(f"이번 주는 {best_day['label']}요일에 섭취량이 가장 높았어요.")
    else:
        messages.append("이번 주는 아직 기록된 날이 적어요. 기록이 쌓이면 요일별 흐름을 더 정확히 볼 수 있어요.")

    if caffeine_avg_pct >= 70:
        messages.append("이번 주 카페인 평균 섭취량이 기준에 가까워요.")
    if sugar_avg_pct >= 70:
        messages.append("이번 주 당류 평균 섭취량이 기준에 가까워요.")
    if sodium_avg_pct >= 70:
        messages.append("이번 주 나트륨 평균 섭취량이 높은 편이에요.")

    if not any([caffeine_avg_pct >= 70, sugar_avg_pct >= 70, sodium_avg_pct >= 70]):
        messages.append("이번 주는 전반적으로 안정적인 섭취 흐름을 보였어요.")

    return {"title": "AI 분석 요약", "messages": messages}


@router.get("/premium/report/{user_id}")
def get_premium_report(
    user_id: int,
    period: str,
    date: str = None,
    db: sqlite3.Connection = Depends(get_db)
):
    """
    프리미엄 일간/주간 섭취 리포트.
    period: "daily" | "weekly"
    date: YYYY-MM-DD (기본값: 오늘)
    프리미엄 회원만 접근 가능.
    공식 의학 기준 아님.
    """
    cleanup_expired_food_logs(db)
    cursor = db.cursor()

    # 1. 사용자 및 프리미엄 확인
    cursor.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
    user = cursor.fetchone()
    if not user:
        raise HTTPException(status_code=404, detail="사용자를 찾을 수 없습니다.")
    user = dict(user)

    if user.get("is_premium") != 1:
        raise HTTPException(status_code=403, detail="프리미엄 리포트는 유료 회원만 이용할 수 있습니다.")

    # 2. period 유효성
    if period not in ("daily", "weekly"):
        raise HTTPException(status_code=400, detail="period는 daily 또는 weekly만 허용됩니다.")

    # 3. date 파싱
    from datetime import date as date_type, timedelta
    if date:
        try:
            target_date = date_type.fromisoformat(date)
        except ValueError:
            raise HTTPException(status_code=400, detail="날짜 형식이 올바르지 않습니다. YYYY-MM-DD 형식을 사용해 주세요.")
    else:
        target_date = date_type.today()

    computed_age = calculate_current_pregnancy_age(
        user.get("pregnancy_week"), user.get("pregnancy_day"), user.get("pregnancy_entered_at")
    )
    week = computed_age["week"] or 20
    trimester, limits = get_trimester_limits(cursor, week)
    caffeine_limit = limits["caffeine_mg"]
    sugar_limit    = limits["sugar_g"]
    sodium_limit   = limits["sodium_mg"]

    # ── 일간 리포트 ──────────────────────────────────────
    if period == "daily":
        date_str = target_date.isoformat()
        cursor.execute("""
            SELECT caffeine_mg, sugar_g, sodium_mg, eaten_at
            FROM food_log
            WHERE user_id = ? AND DATE(eaten_at) = ?
        """, (user_id, date_str))
        rows = [dict(r) for r in cursor.fetchall()]

        # 시간대 초기화
        SLOTS = ["새벽", "오전", "오후", "저녁"]
        slot_data = {s: {"caffeine_mg": 0.0, "sugar_g": 0.0, "sodium_mg": 0.0} for s in SLOTS}

        total_caffeine = total_sugar = total_sodium = 0.0
        for r in rows:
            c = r.get("caffeine_mg") or 0.0
            s = r.get("sugar_g") or 0.0
            n = r.get("sodium_mg") or 0.0
            total_caffeine += c
            total_sugar    += s
            total_sodium   += n
            # 시간대 분류
            try:
                hour = int(r["eaten_at"][11:13])
            except (TypeError, ValueError, IndexError):
                hour = 12
            if hour < 6:
                slot = "새벽"
            elif hour < 12:
                slot = "오전"
            elif hour < 18:
                slot = "오후"
            else:
                slot = "저녁"
            slot_data[slot]["caffeine_mg"] += c
            slot_data[slot]["sugar_g"]     += s
            slot_data[slot]["sodium_mg"]   += n

        caffeine_pct = _get_percent(total_caffeine, caffeine_limit)
        sugar_pct    = _get_percent(total_sugar,    sugar_limit)
        sodium_pct   = _get_percent(total_sodium,   sodium_limit)

        # 시간대별 정규화 점수 (AI 요약용)
        slot_scores = {
            slot: (
                _get_percent(slot_data[slot]["caffeine_mg"], caffeine_limit)
                + _get_percent(slot_data[slot]["sugar_g"],    sugar_limit)
                + _get_percent(slot_data[slot]["sodium_mg"],  sodium_limit)
            )
            for slot in SLOTS
        }

        chart_items = [
            {
                "label":       slot,
                "caffeine_mg": round(slot_data[slot]["caffeine_mg"], 2),
                "sugar_g":     round(slot_data[slot]["sugar_g"], 2),
                "sodium_mg":   round(slot_data[slot]["sodium_mg"], 2),
            }
            for slot in SLOTS
        ]

        formatted_date = target_date.strftime("%Y.%m.%d")
        return {
            "user_id":        user_id,
            "is_premium":     True,
            "period":         "daily",
            "date":           date_str,
            "pregnancy_week": week,
            "trimester":      trimester,
            "title":          "일간 섭취 리포트",
            "summary_card": {
                "title":      f"{week}주차",
                "subtitle":   "오늘 섭취 흐름을 분석했어요 :)",
                "date_range": formatted_date,
            },
            "totals": {
                "caffeine_mg": round(total_caffeine, 2),
                "sugar_g":     round(total_sugar, 2),
                "sodium_mg":   round(total_sodium, 2),
            },
            "limits": {
                "caffeine_mg": caffeine_limit,
                "sugar_g":     sugar_limit,
                "sodium_mg":   sodium_limit,
            },
            "percentages": {
                "caffeine": caffeine_pct,
                "sugar":    sugar_pct,
                "sodium":   sodium_pct,
            },
            "chart": {
                "type":  "time_slot",
                "title": "일간 섭취 추이",
                "items": chart_items,
            },
            "ai_summary": _build_daily_ai_summary(
                caffeine_pct, sugar_pct, sodium_pct, slot_scores
            ),
        }

    # ── 주간 리포트 ──────────────────────────────────────
    from datetime import timedelta
    monday = target_date - timedelta(days=target_date.weekday())
    sunday = monday + timedelta(days=6)

    cursor.execute("""
        SELECT caffeine_mg, sugar_g, sodium_mg, DATE(eaten_at) AS log_date
        FROM food_log
        WHERE user_id = ? AND DATE(eaten_at) BETWEEN ? AND ?
    """, (user_id, monday.isoformat(), sunday.isoformat()))
    rows = [dict(r) for r in cursor.fetchall()]

    # 요일별 집계 초기화
    WEEKDAY_LABELS = ["월", "화", "수", "목", "금", "토", "일"]
    week_days = []
    for i in range(7):
        d = monday + timedelta(days=i)
        week_days.append({
            "label":       WEEKDAY_LABELS[i],
            "date":        d.isoformat(),
            "caffeine_mg": 0.0,
            "sugar_g":     0.0,
            "sodium_mg":   0.0,
        })

    for r in rows:
        c = r.get("caffeine_mg") or 0.0
        s = r.get("sugar_g") or 0.0
        n = r.get("sodium_mg") or 0.0
        for day in week_days:
            if day["date"] == r["log_date"]:
                day["caffeine_mg"] += c
                day["sugar_g"]     += s
                day["sodium_mg"]   += n
                break

    # 주간 합계
    total_caffeine = sum(d["caffeine_mg"] for d in week_days)
    total_sugar    = sum(d["sugar_g"]     for d in week_days)
    total_sodium   = sum(d["sodium_mg"]   for d in week_days)

    # 일평균 (7일 기준)
    avg_caffeine = round(total_caffeine / 7, 1)
    avg_sugar    = round(total_sugar    / 7, 1)
    avg_sodium   = round(total_sodium   / 7, 1)

    caffeine_avg_pct = _get_percent(avg_caffeine, caffeine_limit)
    sugar_avg_pct    = _get_percent(avg_sugar,    sugar_limit)
    sodium_avg_pct   = _get_percent(avg_sodium,   sodium_limit)

    # 요일별 정규화 점수 (AI 요약용)
    day_scores = [
        {
            "label": d["label"],
            "score": (
                _get_percent(d["caffeine_mg"], caffeine_limit)
                + _get_percent(d["sugar_g"],    sugar_limit)
                + _get_percent(d["sodium_mg"],  sodium_limit)
            ),
        }
        for d in week_days
    ]

    chart_items = [
        {
            "label":       d["label"],
            "date":        d["date"],
            "caffeine_mg": round(d["caffeine_mg"], 2),
            "sugar_g":     round(d["sugar_g"], 2),
            "sodium_mg":   round(d["sodium_mg"], 2),
        }
        for d in week_days
    ]

    date_range_str = f"{monday.strftime('%Y.%m.%d.')} ~ {sunday.strftime('%m.%d.')}"
    return {
        "user_id":        user_id,
        "is_premium":     True,
        "period":         "weekly",
        "date_range": {
            "start": monday.isoformat(),
            "end":   sunday.isoformat(),
        },
        "pregnancy_week": week,
        "trimester":      trimester,
        "title":          "주간 섭취 리포트",
        "summary_card": {
            "title":      f"{week}주차",
            "subtitle":   "이번 주 섭취 흐름을 분석했어요 :)",
            "date_range": date_range_str,
        },
        "totals": {
            "caffeine_mg": round(total_caffeine, 2),
            "sugar_g":     round(total_sugar, 2),
            "sodium_mg":   round(total_sodium, 2),
        },
        "daily_average": {
            "caffeine_mg": avg_caffeine,
            "sugar_g":     avg_sugar,
            "sodium_mg":   avg_sodium,
        },
        "limits": {
            "daily_caffeine_mg": caffeine_limit,
            "daily_sugar_g":     sugar_limit,
            "daily_sodium_mg":   sodium_limit,
        },
        "percentages": {
            "caffeine": caffeine_avg_pct,
            "sugar":    sugar_avg_pct,
            "sodium":   sodium_avg_pct,
        },
        "chart": {
            "type":  "weekday",
            "title": "주간 섭취 추이",
            "items": chart_items,
        },
        "ai_summary": _build_weekly_ai_summary(
            caffeine_avg_pct, sugar_avg_pct, sodium_avg_pct, day_scores
        ),
    }
