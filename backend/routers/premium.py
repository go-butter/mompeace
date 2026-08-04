import sqlite3
from datetime import date as date_type, timedelta

from fastapi import APIRouter, HTTPException, Depends

from backend.database import get_db
from backend.nutrition_constants import IRON_RECOMMENDED_MG, IRON_UPPER_LIMIT_MG, KCAL_PER_GRAM_FAT
from backend.intake_totals import (
    compute_overall_status,
    get_fat_status,
    get_floor_status,
    get_iron_status,
    get_status,
    get_trimester_limits,
    resolve_user_nutrition_context,
)

router = APIRouter()

WEEKDAY_LABELS = ["월", "화", "수", "목", "금", "토", "일"]


def _aggregate_week(cursor, user_id: int, monday: date_type, sunday: date_type) -> tuple[list[dict], int]:
    """월요일~일요일 7일간 요일별 영양소 합계 + unknown 카운트 집계.

    반환: (week_days, row_count). row_count는 해당 기간에 존재하는 food_log 행 수로,
    "기록이 아예 없음"과 "기록은 있지만 합계가 0"을 구분하는 데 쓰인다.
    """
    cursor.execute("""
        SELECT caffeine_mg, sugar_g, sodium_mg, DATE(eaten_at) AS log_date
        FROM food_log
        WHERE user_id = ? AND DATE(eaten_at) BETWEEN ? AND ?
    """, (user_id, monday.isoformat(), sunday.isoformat()))
    rows = [dict(r) for r in cursor.fetchall()]

    week_days = []
    for i in range(7):
        d = monday + timedelta(days=i)
        week_days.append({
            "label":       WEEKDAY_LABELS[i],
            "date":        d.isoformat(),
            "caffeine_mg": 0.0,
            "sugar_g":     0.0,
            "sodium_mg":   0.0,
            "unknown_caffeine": 0,
            "unknown_sugar":    0,
            "unknown_sodium":   0,
            "log_count":        0,
        })

    for r in rows:
        caffeine_val = r.get("caffeine_mg")
        sugar_val = r.get("sugar_g")
        sodium_val = r.get("sodium_mg")
        c = caffeine_val or 0.0
        s = sugar_val or 0.0
        n = sodium_val or 0.0
        for day in week_days:
            if day["date"] == r["log_date"]:
                day["caffeine_mg"] += c
                day["sugar_g"]     += s
                day["sodium_mg"]   += n
                day["log_count"]   += 1
                if caffeine_val is None:
                    day["unknown_caffeine"] += 1
                if sugar_val is None:
                    day["unknown_sugar"] += 1
                if sodium_val is None:
                    day["unknown_sodium"] += 1
                break

    return week_days, len(rows)


def _get_percent(value: float, standard: float) -> float:
    if standard <= 0:
        return 0.0
    return round(value / standard * 100, 1)


def _compute_extra_nutrient_totals(cursor, user_id: int, start_date: str, end_date: str) -> dict:
    """탄수화물/단백질/지방류/철분/에너지의 기간 합계 + unknown 카운트.

    카페인/당류/나트륨과 달리 시간대별(daily)/요일별(weekly) 차트에는 포함하지 않고
    리포트 상단 요약(totals/limits/percentages/status)에만 쓰인다.
    """
    cursor.execute("""
        SELECT
            COALESCE(SUM(calories_kcal), 0) AS total_energy,
            COALESCE(SUM(CASE WHEN calories_kcal IS NULL THEN 1 ELSE 0 END), 0) AS unknown_energy_count,
            COALESCE(SUM(carbohydrate_g), 0) AS total_carbohydrate,
            COALESCE(SUM(CASE WHEN carbohydrate_g IS NULL THEN 1 ELSE 0 END), 0) AS unknown_carbohydrate_count,
            COALESCE(SUM(protein_g), 0) AS total_protein,
            COALESCE(SUM(CASE WHEN protein_g IS NULL THEN 1 ELSE 0 END), 0) AS unknown_protein_count,
            COALESCE(SUM(fat_g), 0) AS total_fat,
            COALESCE(SUM(CASE WHEN fat_g IS NULL THEN 1 ELSE 0 END), 0) AS unknown_fat_count,
            COALESCE(SUM(saturated_fat_g), 0) AS total_saturated_fat,
            COALESCE(SUM(CASE WHEN saturated_fat_g IS NULL THEN 1 ELSE 0 END), 0) AS unknown_saturated_fat_count,
            COALESCE(SUM(trans_fat_g), 0) AS total_trans_fat,
            COALESCE(SUM(CASE WHEN trans_fat_g IS NULL THEN 1 ELSE 0 END), 0) AS unknown_trans_fat_count,
            COALESCE(SUM(iron_mg), 0) AS total_iron,
            COALESCE(SUM(CASE WHEN iron_mg IS NULL THEN 1 ELSE 0 END), 0) AS unknown_iron_count
        FROM food_log
        WHERE user_id = ? AND DATE(eaten_at) BETWEEN ? AND ?
    """, (user_id, start_date, end_date))
    return dict(cursor.fetchone())


def _build_extra_nutrient_report_block(totals: dict, limits: dict, divisor: int) -> dict:
    """새로 추가된 영양소(에너지/탄수화물/단백질/지방류/철분)의 totals/daily_average/
    limits/percentages/status 블록.

    divisor=1이면 daily 리포트(기간 합계 = 하루 값), weekly 리포트에서는 기록이 있는 날
    수로 나눠 일평균을 낸다. 지방류 비율(총 에너지 대비)은 합계/합계와 평균/평균이
    수학적으로 동일하므로 별도로 나누지 않고 기간 합계를 그대로 사용한다.
    """
    energy_target = limits["energy_kcal"]
    carb_min = limits["carbohydrate_g"]
    protein_target = limits["protein_g"]
    fat_ratio_min = limits["fat_ratio_min"]
    fat_ratio_max = limits["fat_ratio_max"]
    saturated_fat_ratio_max = limits["saturated_fat_ratio_max"]
    trans_fat_ratio_max = limits["trans_fat_ratio_max"]

    total_energy = totals["total_energy"]
    total_carb = totals["total_carbohydrate"]
    total_protein = totals["total_protein"]
    total_fat = totals["total_fat"]
    total_saturated_fat = totals["total_saturated_fat"]
    total_trans_fat = totals["total_trans_fat"]
    total_iron = totals["total_iron"]

    avg_energy = round(total_energy / divisor, 1)
    avg_carb = round(total_carb / divisor, 1)
    avg_protein = round(total_protein / divisor, 1)

    energy_status = get_floor_status(avg_energy, energy_target, totals["unknown_energy_count"])
    carb_status = get_floor_status(avg_carb, carb_min, totals["unknown_carbohydrate_count"])
    protein_status = get_floor_status(avg_protein, protein_target, totals["unknown_protein_count"])
    fat_status = get_fat_status(
        total_fat, total_energy, fat_ratio_min, fat_ratio_max, totals["unknown_fat_count"]
    )
    # energy_total(kcal) * ratio는 kcal 단위이므로, 그램 단위인 total_saturated_fat/
    # total_trans_fat과 비교하려면 KCAL_PER_GRAM_FAT(9kcal/g)로 나눠 환산해야 한다
    # (get_fat_status()와 동일한 이유).
    saturated_fat_status = get_status(
        total_saturated_fat,
        total_energy * saturated_fat_ratio_max / KCAL_PER_GRAM_FAT,
        totals["unknown_saturated_fat_count"],
    )
    trans_fat_status = get_status(
        total_trans_fat,
        total_energy * trans_fat_ratio_max / KCAL_PER_GRAM_FAT,
        totals["unknown_trans_fat_count"],
    )
    iron_status = get_iron_status(
        total_iron, IRON_RECOMMENDED_MG, IRON_UPPER_LIMIT_MG, totals["unknown_iron_count"]
    )

    return {
        "totals": {
            "energy_kcal": round(total_energy, 2),
            "carbohydrate_g": round(total_carb, 2),
            "protein_g": round(total_protein, 2),
            "fat_g": round(total_fat, 2),
            "saturated_fat_g": round(total_saturated_fat, 2),
            "trans_fat_g": round(total_trans_fat, 2),
            "iron_mg": round(total_iron, 2),
        },
        "daily_average": {
            "energy_kcal": avg_energy,
            "carbohydrate_g": avg_carb,
            "protein_g": avg_protein,
        },
        "limits": {
            "energy_target_kcal": energy_target,
            "carbohydrate_minimum_g": carb_min,
            "protein_target_g": protein_target,
            "fat_ratio_min": fat_ratio_min,
            "fat_ratio_max": fat_ratio_max,
            "saturated_fat_ratio_max": saturated_fat_ratio_max,
            "trans_fat_ratio_max": trans_fat_ratio_max,
        },
        "percentages": {
            "energy": _get_percent(avg_energy, energy_target),
            "carbohydrate": _get_percent(avg_carb, carb_min),
            "protein": _get_percent(avg_protein, protein_target),
        },
        "status": {
            "energy_status": energy_status,
            "carbohydrate_status": carb_status,
            "protein_status": protein_status,
            "fat_status": fat_status,
            "saturated_fat_status": saturated_fat_status,
            "trans_fat_status": trans_fat_status,
            "iron_status": iron_status,
        },
    }


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
    공식 의학 기준 아님.
    """
    cursor = db.cursor()

    # 1. 사용자 확인
    cursor.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
    user = cursor.fetchone()
    if not user:
        raise HTTPException(status_code=404, detail="사용자를 찾을 수 없습니다.")
    user = dict(user)

    # 2. period 유효성
    if period not in ("daily", "weekly"):
        raise HTTPException(status_code=400, detail="period는 daily 또는 weekly만 허용됩니다.")

    # 3. date 파싱
    if date:
        try:
            target_date = date_type.fromisoformat(date)
        except ValueError:
            raise HTTPException(status_code=400, detail="날짜 형식이 올바르지 않습니다. YYYY-MM-DD 형식을 사용해 주세요.")
    else:
        target_date = date_type.today()

    week, age_bracket = resolve_user_nutrition_context(user)
    trimester, limits = get_trimester_limits(week, age_bracket)
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
        slot_data = {
            s: {
                "caffeine_mg": 0.0, "sugar_g": 0.0, "sodium_mg": 0.0,
                "unknown_caffeine": 0, "unknown_sugar": 0, "unknown_sodium": 0,
            }
            for s in SLOTS
        }

        total_caffeine = total_sugar = total_sodium = 0.0
        unknown_caffeine_count = unknown_sugar_count = unknown_sodium_count = 0
        for r in rows:
            caffeine_val = r.get("caffeine_mg")
            sugar_val = r.get("sugar_g")
            sodium_val = r.get("sodium_mg")
            if caffeine_val is None:
                unknown_caffeine_count += 1
            if sugar_val is None:
                unknown_sugar_count += 1
            if sodium_val is None:
                unknown_sodium_count += 1
            c = caffeine_val or 0.0
            s = sugar_val or 0.0
            n = sodium_val or 0.0
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
            if caffeine_val is None:
                slot_data[slot]["unknown_caffeine"] += 1
            if sugar_val is None:
                slot_data[slot]["unknown_sugar"] += 1
            if sodium_val is None:
                slot_data[slot]["unknown_sodium"] += 1

        caffeine_pct = _get_percent(total_caffeine, caffeine_limit)
        sugar_pct    = _get_percent(total_sugar,    sugar_limit)
        sodium_pct   = _get_percent(total_sodium,   sodium_limit)

        caffeine_status = get_status(total_caffeine, caffeine_limit, unknown_caffeine_count)
        sugar_status    = get_status(total_sugar,    sugar_limit,    unknown_sugar_count)
        sodium_status   = get_status(total_sodium,   sodium_limit,   unknown_sodium_count)
        overall_status  = compute_overall_status(caffeine_status, sugar_status, sodium_status)

        # 시간대별 정규화 점수 (AI 요약용)
        slot_scores = {
            slot: (
                _get_percent(slot_data[slot]["caffeine_mg"], caffeine_limit)
                + _get_percent(slot_data[slot]["sugar_g"],    sugar_limit)
                + _get_percent(slot_data[slot]["sodium_mg"],  sodium_limit)
            )
            for slot in SLOTS
        }

        chart_items = []
        for slot in SLOTS:
            d = slot_data[slot]
            item_caffeine_status = get_status(d["caffeine_mg"], caffeine_limit, d["unknown_caffeine"])
            item_sugar_status    = get_status(d["sugar_g"],     sugar_limit,    d["unknown_sugar"])
            item_sodium_status   = get_status(d["sodium_mg"],   sodium_limit,   d["unknown_sodium"])
            chart_items.append({
                "label":  slot,
                "status": compute_overall_status(item_caffeine_status, item_sugar_status, item_sodium_status),
                "caffeine_mg":     round(d["caffeine_mg"], 2),
                "caffeine_pct":    _get_percent(d["caffeine_mg"], caffeine_limit),
                "caffeine_status": item_caffeine_status,
                "sugar_g":         round(d["sugar_g"], 2),
                "sugar_pct":       _get_percent(d["sugar_g"], sugar_limit),
                "sugar_status":    item_sugar_status,
                "sodium_mg":       round(d["sodium_mg"], 2),
                "sodium_pct":      _get_percent(d["sodium_mg"], sodium_limit),
                "sodium_status":   item_sodium_status,
            })

        extra_totals = _compute_extra_nutrient_totals(cursor, user_id, date_str, date_str)
        extra_block = _build_extra_nutrient_report_block(extra_totals, limits, divisor=1)

        formatted_date = target_date.strftime("%Y.%m.%d")
        return {
            "user_id":        user_id,
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
                **extra_block["totals"],
            },
            "limits": {
                "caffeine_mg": caffeine_limit,
                "sugar_g":     sugar_limit,
                "sodium_mg":   sodium_limit,
                **extra_block["limits"],
            },
            "percentages": {
                "caffeine": caffeine_pct,
                "sugar":    sugar_pct,
                "sodium":   sodium_pct,
                **extra_block["percentages"],
            },
            "status": {
                "overall_status":  overall_status,
                "caffeine_status": caffeine_status,
                "sugar_status":    sugar_status,
                "sodium_status":   sodium_status,
                **extra_block["status"],
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
    monday = target_date - timedelta(days=target_date.weekday())
    sunday = monday + timedelta(days=6)

    week_days, _ = _aggregate_week(cursor, user_id, monday, sunday)

    # 주간 합계
    total_caffeine = sum(d["caffeine_mg"] for d in week_days)
    total_sugar    = sum(d["sugar_g"]     for d in week_days)
    total_sodium   = sum(d["sodium_mg"]   for d in week_days)

    unknown_caffeine_count = sum(d["unknown_caffeine"] for d in week_days)
    unknown_sugar_count    = sum(d["unknown_sugar"]    for d in week_days)
    unknown_sodium_count   = sum(d["unknown_sodium"]   for d in week_days)

    caffeine_status = get_status(total_caffeine, caffeine_limit, unknown_caffeine_count)
    sugar_status    = get_status(total_sugar,    sugar_limit,    unknown_sugar_count)
    sodium_status   = get_status(total_sodium,   sodium_limit,   unknown_sodium_count)
    overall_status  = compute_overall_status(caffeine_status, sugar_status, sodium_status)

    # 일평균 (기록이 있는 날 수 기준. 기록이 아예 없는 주는 0으로 나누지 않도록 1로 대체 -
    # 이 경우 분자도 0이므로 결과는 어차피 0.0)
    days_with_data = sum(1 for d in week_days if d["log_count"] > 0)
    divisor = days_with_data or 1
    avg_caffeine = round(total_caffeine / divisor, 1)
    avg_sugar    = round(total_sugar    / divisor, 1)
    avg_sodium   = round(total_sodium   / divisor, 1)

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

    chart_items = []
    for d in week_days:
        item_caffeine_status = get_status(d["caffeine_mg"], caffeine_limit, d["unknown_caffeine"])
        item_sugar_status    = get_status(d["sugar_g"],     sugar_limit,    d["unknown_sugar"])
        item_sodium_status   = get_status(d["sodium_mg"],   sodium_limit,   d["unknown_sodium"])
        chart_items.append({
            "label":  d["label"],
            "date":   d["date"],
            "status": compute_overall_status(item_caffeine_status, item_sugar_status, item_sodium_status),
            "caffeine_mg":     round(d["caffeine_mg"], 2),
            "caffeine_pct":    _get_percent(d["caffeine_mg"], caffeine_limit),
            "caffeine_status": item_caffeine_status,
            "sugar_g":         round(d["sugar_g"], 2),
            "sugar_pct":       _get_percent(d["sugar_g"], sugar_limit),
            "sugar_status":    item_sugar_status,
            "sodium_mg":       round(d["sodium_mg"], 2),
            "sodium_pct":      _get_percent(d["sodium_mg"], sodium_limit),
            "sodium_status":   item_sodium_status,
        })

    # 지난주 대비 비교 (퍼센트포인트 차이, daily_average와 동일하게 기록이 있는 날 수 기준으로 계산)
    prev_monday = monday - timedelta(days=7)
    prev_sunday = sunday - timedelta(days=7)
    prev_week_days, prev_row_count = _aggregate_week(cursor, user_id, prev_monday, prev_sunday)

    unknown_caffeine_count_prev = sum(d["unknown_caffeine"] for d in prev_week_days)
    unknown_sugar_count_prev    = sum(d["unknown_sugar"]    for d in prev_week_days)
    unknown_sodium_count_prev   = sum(d["unknown_sodium"]   for d in prev_week_days)

    # nutrient별로 "확인된 값이 하나도 없음"을 따로 판정한다.
    # prev_row_count==0(기록 자체가 없음)과 prev_row_count>0인데 그 nutrient만 전부 NULL인 경우를
    # 모두 포괄한다 (두 경우 다 known_count == 0).
    prev_known_caffeine_count = prev_row_count - unknown_caffeine_count_prev
    prev_known_sugar_count    = prev_row_count - unknown_sugar_count_prev
    prev_known_sodium_count   = prev_row_count - unknown_sodium_count_prev

    prev_total_caffeine = sum(d["caffeine_mg"] for d in prev_week_days)
    prev_total_sugar    = sum(d["sugar_g"]     for d in prev_week_days)
    prev_total_sodium   = sum(d["sodium_mg"]   for d in prev_week_days)

    prev_days_with_data = sum(1 for d in prev_week_days if d["log_count"] > 0)
    prev_divisor = prev_days_with_data or 1

    if prev_known_caffeine_count == 0:
        caffeine_vs_previous_pct = None
    else:
        prev_avg_caffeine_pct = _get_percent(round(prev_total_caffeine / prev_divisor, 1), caffeine_limit)
        caffeine_vs_previous_pct = round(caffeine_avg_pct - prev_avg_caffeine_pct, 1)

    if prev_known_sugar_count == 0:
        sugar_vs_previous_pct = None
    else:
        prev_avg_sugar_pct = _get_percent(round(prev_total_sugar / prev_divisor, 1), sugar_limit)
        sugar_vs_previous_pct = round(sugar_avg_pct - prev_avg_sugar_pct, 1)

    if prev_known_sodium_count == 0:
        sodium_vs_previous_pct = None
    else:
        prev_avg_sodium_pct = _get_percent(round(prev_total_sodium / prev_divisor, 1), sodium_limit)
        sodium_vs_previous_pct = round(sodium_avg_pct - prev_avg_sodium_pct, 1)

    extra_totals = _compute_extra_nutrient_totals(cursor, user_id, monday.isoformat(), sunday.isoformat())
    extra_block = _build_extra_nutrient_report_block(extra_totals, limits, divisor=divisor)

    date_range_str = f"{monday.strftime('%Y.%m.%d.')} ~ {sunday.strftime('%m.%d.')}"
    return {
        "user_id":        user_id,
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
            **extra_block["totals"],
        },
        "daily_average": {
            "caffeine_mg": avg_caffeine,
            "sugar_g":     avg_sugar,
            "sodium_mg":   avg_sodium,
            **extra_block["daily_average"],
        },
        "limits": {
            "daily_caffeine_mg": caffeine_limit,
            "daily_sugar_g":     sugar_limit,
            "daily_sodium_mg":   sodium_limit,
            **extra_block["limits"],
        },
        "percentages": {
            "caffeine": caffeine_avg_pct,
            "sugar":    sugar_avg_pct,
            "sodium":   sodium_avg_pct,
            **extra_block["percentages"],
        },
        "status": {
            "overall_status":  overall_status,
            "caffeine_status": caffeine_status,
            "sugar_status":    sugar_status,
            "sodium_status":   sodium_status,
            **extra_block["status"],
        },
        "comparison": {
            "previous_period": {
                "start": prev_monday.isoformat(),
                "end":   prev_sunday.isoformat(),
            },
            "caffeine_vs_previous_pct": caffeine_vs_previous_pct,
            "sugar_vs_previous_pct":    sugar_vs_previous_pct,
            "sodium_vs_previous_pct":   sodium_vs_previous_pct,
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
