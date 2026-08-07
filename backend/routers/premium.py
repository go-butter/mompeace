import sqlite3
from datetime import date as date_type, timedelta

from fastapi import APIRouter, HTTPException, Depends

from backend.database import get_db
from backend.nutrition_constants import (
    DAILY_WATER_TARGET_ML,
    IRON_RECOMMENDED_MG,
    IRON_UPPER_LIMIT_MG,
    KCAL_PER_GRAM_FAT,
)
from backend.intake_totals import (
    compute_overall_status,
    get_fat_status,
    get_floor_status,
    get_iron_status,
    get_status,
    get_trimester_limits,
    resolve_user_nutrition_context,
    simplified_status_label,
    tier_of_status,
)
from backend.routers.water_log import fetch_water_totals_by_day

router = APIRouter()

WEEKDAY_LABELS = ["월", "화", "수", "목", "금", "토", "일"]

# 응답의 status 키 → 판정 방식. tier_of_status()/simplified_status_label()가 요구하는
# nutrient_type이며, /intake/today의 status_label 블록과 같은 배정을 쓴다.
# "status"는 chart 항목의 종합 판정 키다(compute_overall_status 결과 = ceiling 어휘).
_PREMIUM_STATUS_TYPES = {
    "overall_status":       "ceiling",
    "caffeine_status":      "ceiling",
    "sugar_status":         "ceiling",
    "sodium_status":        "ceiling",
    "saturated_fat_status": "ceiling",
    "trans_fat_status":     "ceiling",
    "energy_status":        "floor",
    "carbohydrate_status":  "floor",
    "protein_status":       "floor",
    "fat_status":           "band",
    "iron_status":          "band",
    "water_status":         "floor",
    "status":               "ceiling",
}

# tier_of_status()는 nutrient_type을 bare 조회하고 simplified_status_label()은
# 알 수 없는 값에 ValueError를 던지므로, 둘 다 이 셋 안의 값으로만 호출한다.
_MAPPABLE_STATUS_TYPES = ("ceiling", "floor", "band")


def _tier_fields(source: dict) -> dict:
    """source의 status 키들에 대응하는 tier/status_label 형제 키를 계산해 돌려준다.

    _PREMIUM_STATUS_TYPES에 없는 키, 알 수 없는 nutrient_type, 문자열이 아닌 값은
    건너뛴다 — 최상위 응답의 "status"는 dict(컨테이너)이고 chart 항목의 "status"는
    판정 문자열이라 같은 이름이 두 가지 뜻으로 쓰이기 때문이다.
    """
    added = {}
    for key, status in list(source.items()):
        nutrient_type = _PREMIUM_STATUS_TYPES.get(key)
        if nutrient_type not in _MAPPABLE_STATUS_TYPES:
            continue
        if not isinstance(status, str):
            continue
        prefix = "" if key == "status" else f"{key[:-len('_status')]}_"
        added[f"{prefix}tier"] = tier_of_status(nutrient_type, status)
        added[f"{prefix}status_label"] = simplified_status_label(nutrient_type, status)
    return added


def _attach_tiers(response: dict) -> dict:
    """조립이 끝난 응답에 tier/status_label을 덧붙인다(기존 status 값은 그대로 둔다).

    status 블록과 chart.items[]만 대상으로 하며 재귀하지 않는다.
    """
    status_block = response.get("status")
    if isinstance(status_block, dict):
        status_block.update(_tier_fields(status_block))

    chart = response.get("chart")
    items = chart.get("items") if isinstance(chart, dict) else None
    for item in items or ():
        if isinstance(item, dict):
            item.update(_tier_fields(item))

    return response


def _aggregate_week(cursor, user_id: int, monday: date_type, sunday: date_type) -> tuple[list[dict], int]:
    """월요일~일요일 7일간 요일별 영양소 합계 + known 카운트 집계.

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
            "known_caffeine": 0,
            "known_sugar":    0,
            "known_sodium":   0,
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
                if caffeine_val is not None:
                    day["known_caffeine"] += 1
                if sugar_val is not None:
                    day["known_sugar"] += 1
                if sodium_val is not None:
                    day["known_sodium"] += 1
                break

    return week_days, len(rows)


def _get_percent(value: float, standard: float) -> float:
    if standard <= 0:
        return 0.0
    return round(value / standard * 100, 1)


def _compute_extra_nutrient_totals(cursor, user_id: int, start_date: str, end_date: str) -> dict:
    """탄수화물/단백질/지방류/철분/에너지의 기간 합계 + known 카운트.

    카페인/당류/나트륨과 달리 시간대별(daily)/요일별(weekly) 차트에는 포함하지 않고
    리포트 상단 요약(totals/limits/percentages/status)에만 쓰인다.
    """
    cursor.execute("""
        SELECT
            COALESCE(SUM(calories_kcal), 0) AS total_energy,
            COUNT(calories_kcal) AS known_energy_count,
            COALESCE(SUM(carbohydrate_g), 0) AS total_carbohydrate,
            COUNT(carbohydrate_g) AS known_carbohydrate_count,
            COALESCE(SUM(protein_g), 0) AS total_protein,
            COUNT(protein_g) AS known_protein_count,
            COALESCE(SUM(fat_g), 0) AS total_fat,
            COUNT(fat_g) AS known_fat_count,
            COALESCE(SUM(saturated_fat_g), 0) AS total_saturated_fat,
            COUNT(saturated_fat_g) AS known_saturated_fat_count,
            COALESCE(SUM(trans_fat_g), 0) AS total_trans_fat,
            COUNT(trans_fat_g) AS known_trans_fat_count,
            COALESCE(SUM(iron_mg), 0) AS total_iron,
            COUNT(iron_mg) AS known_iron_count,
            COUNT(*) AS logged_count
        FROM food_log
        WHERE user_id = ? AND DATE(eaten_at) BETWEEN ? AND ?
    """, (user_id, start_date, end_date))
    return dict(cursor.fetchone())


def _build_extra_nutrient_report_block(totals: dict, limits: dict, divisor: int) -> dict:
    """새로 추가된 영양소(에너지/탄수화물/단백질/지방류/철분)의 totals/daily_average/
    limits/percentages/status 블록.

    divisor=1이면 daily 리포트(기간 합계 = 하루 값), weekly 리포트에서는 기록이 있는 날
    수로 나눠 일평균을 낸다.

    지방(fat_status)도 에너지/탄수화물/단백질과 마찬가지로 일평균으로 판정한다.
    예전에는 분모가 "기간 누적 에너지"라 합계/합계와 평균/평균이 수학적으로 같아서
    나누지 않아도 됐지만, 분모가 "하루 에너지 목표"라는 고정값으로 바뀌면서 그
    등가성이 깨졌다 — 이제 나누지 않으면 7일치 지방을 하루치 상한과 비교하게 된다.

    포화지방/트랜스지방은 이번 변경 대상이 아니라 여전히 기간 누적 에너지 대비
    비율을 쓴다(같은 성격의 문제가 있으나 별도 결정 사항).
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
    # 지방도 일평균으로 판정한다 — 분모가 "하루 에너지 목표"인 고정값이 되었으므로
    # 분자도 반드시 하루치여야 한다. 기간 합계를 그대로 쓰면 7일치 지방을 하루치
    # 상한과 비교하게 되어 정상적인 한 주가 영구적으로 avoid가 된다.
    avg_fat = round(total_fat / divisor, 1)

    logged_count = totals["logged_count"]
    energy_status = get_floor_status(avg_energy, energy_target, totals["known_energy_count"], logged_count)
    carb_status = get_floor_status(avg_carb, carb_min, totals["known_carbohydrate_count"], logged_count)
    protein_status = get_floor_status(avg_protein, protein_target, totals["known_protein_count"], logged_count)
    fat_status = get_fat_status(
        avg_fat, energy_target, fat_ratio_min, fat_ratio_max, totals["known_fat_count"], logged_count
    )
    # energy_total(kcal) * ratio는 kcal 단위이므로, 그램 단위인 total_saturated_fat/
    # total_trans_fat과 비교하려면 KCAL_PER_GRAM_FAT(9kcal/g)로 나눠 환산해야 한다
    # (get_fat_status()와 동일한 이유).
    saturated_fat_status = get_status(
        total_saturated_fat,
        total_energy * saturated_fat_ratio_max / KCAL_PER_GRAM_FAT,
        totals["known_saturated_fat_count"],
        logged_count,
    )
    trans_fat_status = get_status(
        total_trans_fat,
        total_energy * trans_fat_ratio_max / KCAL_PER_GRAM_FAT,
        totals["known_trans_fat_count"],
        logged_count,
    )
    iron_status = get_iron_status(
        total_iron, IRON_RECOMMENDED_MG, IRON_UPPER_LIMIT_MG, totals["known_iron_count"], logged_count
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


def _build_water_report_block(
    user_id: int, start: date_type, end: date_type, db: sqlite3.Connection
) -> dict:
    """수분의 totals/daily_average/limits/percentages/status 블록.

    분모(water_divisor)는 food_log가 아니라 water_log에 기록이 있는 날 수다. 다른
    영양소와 같은 규칙("기록이 있는 날 수로 나눈다")을 수분이 실제로 저장되는 테이블
    기준으로 적용한 것 — 물만 마시고 음식은 기록하지 않은 날이 있으면 food_log 기준
    분모(days_with_data)와 값이 달라진다.

    일간 리포트는 start == end이라 water_divisor가 항상 1이고, 따라서 일평균이 그날의
    합계와 같아진다(_build_extra_nutrient_report_block의 divisor=1과 같은 성질).

    water_log.amount_ml은 NOT NULL이라 수분은 unknown이 될 수 없으므로
    known_count/logged_count를 1로 고정한다 (routers/intake.py의 /intake/summary와 동일).
    """
    days = fetch_water_totals_by_day(user_id, start, end, db)
    total_ml = round(sum(d["amount_ml"] for d in days), 1)
    days_with_water = sum(1 for d in days if d["log_count"] > 0)
    water_divisor = days_with_water or 1
    avg_ml = round(total_ml / water_divisor, 1)
    water_status = get_floor_status(avg_ml, DAILY_WATER_TARGET_ML, known_count=1, logged_count=1)

    return {
        "totals":        {"water_ml": total_ml},
        "daily_average": {"water_ml": avg_ml},
        "limits":        {"water_target_ml": DAILY_WATER_TARGET_ML},
        "percentages":   {"water": _get_percent(avg_ml, DAILY_WATER_TARGET_ML)},
        "status":        {"water_status": water_status},
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
                "known_caffeine": 0, "known_sugar": 0, "known_sodium": 0,
                "log_count": 0,
            }
            for s in SLOTS
        }

        total_caffeine = total_sugar = total_sodium = 0.0
        known_caffeine_count = known_sugar_count = known_sodium_count = 0
        logged_count = len(rows)
        for r in rows:
            caffeine_val = r.get("caffeine_mg")
            sugar_val = r.get("sugar_g")
            sodium_val = r.get("sodium_mg")
            if caffeine_val is not None:
                known_caffeine_count += 1
            if sugar_val is not None:
                known_sugar_count += 1
            if sodium_val is not None:
                known_sodium_count += 1
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
            slot_data[slot]["log_count"]   += 1
            if caffeine_val is not None:
                slot_data[slot]["known_caffeine"] += 1
            if sugar_val is not None:
                slot_data[slot]["known_sugar"] += 1
            if sodium_val is not None:
                slot_data[slot]["known_sodium"] += 1

        caffeine_pct = _get_percent(total_caffeine, caffeine_limit)
        sugar_pct    = _get_percent(total_sugar,    sugar_limit)
        sodium_pct   = _get_percent(total_sodium,   sodium_limit)

        caffeine_status = get_status(total_caffeine, caffeine_limit, known_caffeine_count, logged_count)
        sugar_status    = get_status(total_sugar,    sugar_limit,    known_sugar_count, logged_count)
        sodium_status   = get_status(total_sodium,   sodium_limit,   known_sodium_count, logged_count)
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
            item_caffeine_status = get_status(d["caffeine_mg"], caffeine_limit, d["known_caffeine"], d["log_count"])
            item_sugar_status    = get_status(d["sugar_g"],     sugar_limit,    d["known_sugar"], d["log_count"])
            item_sodium_status   = get_status(d["sodium_mg"],   sodium_limit,   d["known_sodium"], d["log_count"])
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
        water_block = _build_water_report_block(user_id, target_date, target_date, db)

        formatted_date = target_date.strftime("%Y.%m.%d")
        return _attach_tiers({
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
                **water_block["totals"],
            },
            "limits": {
                "caffeine_mg": caffeine_limit,
                "sugar_g":     sugar_limit,
                "sodium_mg":   sodium_limit,
                **extra_block["limits"],
                **water_block["limits"],
            },
            "percentages": {
                "caffeine": caffeine_pct,
                "sugar":    sugar_pct,
                "sodium":   sodium_pct,
                **extra_block["percentages"],
                **water_block["percentages"],
            },
            "status": {
                "overall_status":  overall_status,
                "caffeine_status": caffeine_status,
                "sugar_status":    sugar_status,
                "sodium_status":   sodium_status,
                **extra_block["status"],
                **water_block["status"],
            },
            "chart": {
                "type":  "time_slot",
                "title": "일간 섭취 추이",
                "items": chart_items,
            },
            "ai_summary": _build_daily_ai_summary(
                caffeine_pct, sugar_pct, sodium_pct, slot_scores
            ),
        })

    # ── 주간 리포트 ──────────────────────────────────────
    monday = target_date - timedelta(days=target_date.weekday())
    sunday = monday + timedelta(days=6)

    week_days, week_row_count = _aggregate_week(cursor, user_id, monday, sunday)

    # 주간 합계
    total_caffeine = sum(d["caffeine_mg"] for d in week_days)
    total_sugar    = sum(d["sugar_g"]     for d in week_days)
    total_sodium   = sum(d["sodium_mg"]   for d in week_days)

    known_caffeine_count = sum(d["known_caffeine"] for d in week_days)
    known_sugar_count    = sum(d["known_sugar"]    for d in week_days)
    known_sodium_count   = sum(d["known_sodium"]   for d in week_days)

    caffeine_status = get_status(total_caffeine, caffeine_limit, known_caffeine_count, week_row_count)
    sugar_status    = get_status(total_sugar,    sugar_limit,    known_sugar_count, week_row_count)
    sodium_status   = get_status(total_sodium,   sodium_limit,   known_sodium_count, week_row_count)
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
        item_caffeine_status = get_status(d["caffeine_mg"], caffeine_limit, d["known_caffeine"], d["log_count"])
        item_sugar_status    = get_status(d["sugar_g"],     sugar_limit,    d["known_sugar"], d["log_count"])
        item_sodium_status   = get_status(d["sodium_mg"],   sodium_limit,   d["known_sodium"], d["log_count"])
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
    prev_week_days, _ = _aggregate_week(cursor, user_id, prev_monday, prev_sunday)

    # nutrient별로 "확인된 값이 하나도 없음"을 따로 판정한다.
    # 지난 주 기록 자체가 없는 경우와, 기록은 있는데 그 nutrient만 전부 NULL인 경우를
    # 모두 포괄한다 (두 경우 다 known_count == 0).
    prev_known_caffeine_count = sum(d["known_caffeine"] for d in prev_week_days)
    prev_known_sugar_count    = sum(d["known_sugar"]    for d in prev_week_days)
    prev_known_sodium_count   = sum(d["known_sodium"]   for d in prev_week_days)

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
    water_block = _build_water_report_block(user_id, monday, sunday, db)

    date_range_str =f"{monday.strftime('%Y.%m.%d.')} ~ {sunday.strftime('%m.%d.')}"
    return _attach_tiers({
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
            **water_block["totals"],
        },
        "daily_average": {
            "caffeine_mg": avg_caffeine,
            "sugar_g":     avg_sugar,
            "sodium_mg":   avg_sodium,
            **extra_block["daily_average"],
            **water_block["daily_average"],
        },
        "limits": {
            "daily_caffeine_mg": caffeine_limit,
            "daily_sugar_g":     sugar_limit,
            "daily_sodium_mg":   sodium_limit,
            **extra_block["limits"],
            **water_block["limits"],
        },
        "percentages": {
            "caffeine": caffeine_avg_pct,
            "sugar":    sugar_avg_pct,
            "sodium":   sodium_avg_pct,
            **extra_block["percentages"],
            **water_block["percentages"],
        },
        "status": {
            "overall_status":  overall_status,
            "caffeine_status": caffeine_status,
            "sugar_status":    sugar_status,
            "sodium_status":   sodium_status,
            **extra_block["status"],
            **water_block["status"],
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
    })
