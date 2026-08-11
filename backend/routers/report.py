import sqlite3
from datetime import date as date_type, timedelta

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel

from backend.ai_report_summary import get_ai_report_analysis
from backend.database import get_db
from backend.nutrition_constants import (
    DAILY_WATER_TARGET_ML,
    IRON_RECOMMENDED_MG,
    IRON_UPPER_LIMIT_MG,
    KCAL_PER_GRAM_FAT,
)
from backend.nutrition_constants import parse_selected_nutrients
from backend.intake_totals import (
    _is_data_unresolved,
    _summary_percent as _get_percent,
    build_nutrient_summary_item,
    compute_overall_status,
    get_fat_status,
    get_floor_status,
    get_iron_status,
    get_status,
    get_trimester_limits,
    resolve_user_nutrition_context,
    simplified_status_label,
    NUTRIENT_SUMMARY_FIELDS,
    tier_of_status,
)
from backend.routers.water_log import fetch_water_totals_by_day

router = APIRouter()

WEEKDAY_LABELS = ["월", "화", "수", "목", "금", "토", "일"]

# chart_keys(["caffeine"] + selected_keys) → food_log 컬럼명. 화이트리스트로만 인덱싱한다
# (selected_keys는 저장 시 validate_selected_nutrients()가 SELECTABLE_NUTRIENT_KEYS로 이미
# 검증했으므로, 여기서 원본 문자열을 SQL에 직접 꽂는 일은 없다).
_NUTRIENT_TO_COLUMN = {
    "caffeine": "caffeine_mg",
    "sugar": "sugar_g",
    "sodium": "sodium_mg",
    "energy": "calories_kcal",
    "carbohydrate": "carbohydrate_g",
    "protein": "protein_g",
    "fat": "fat_g",
    "iron": "iron_mg",
}

# 응답의 status 키 → 판정 방식. tier_of_status()/simplified_status_label()가 요구하는
# nutrient_type이며, /intake/today의 status_label 블록과 같은 배정을 쓴다.
# "status"는 chart 항목의 종합 판정 키다(compute_overall_status 결과 = ceiling 어휘).
_REPORT_STATUS_TYPES = {
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

    _REPORT_STATUS_TYPES에 없는 키, 알 수 없는 nutrient_type, 문자열이 아닌 값은
    건너뛴다 — 최상위 응답의 "status"는 dict(컨테이너)이고 chart 항목의 "status"는
    판정 문자열이라 같은 이름이 두 가지 뜻으로 쓰이기 때문이다.
    """
    added = {}
    for key, status in list(source.items()):
        nutrient_type = _REPORT_STATUS_TYPES.get(key)
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


def _aggregate_week(
    cursor, user_id: int, monday: date_type, sunday: date_type, keys: list[str]
) -> tuple[list[dict], int]:
    """월요일~일요일 7일간 요일별로 keys에 담긴 영양소들의 합계 + known 카운트를 집계한다.

    keys는 호출부가 필요한 영양소만 골라 넘긴다 — 총합/지난주 비교용 호출은 고정
    카페인/당류/나트륨 3개만, 차트용 호출은 그 3개와 chart_keys(카페인 + 선택 영양소)의
    합집합을 넘겨 한 번의 쿼리로 두 용도를 함께 커버한다.

    반환: (week_days, row_count). row_count는 해당 기간에 존재하는 food_log 행 수로,
    "기록이 아예 없음"과 "기록은 있지만 합계가 0"을 구분하는 데 쓰인다.
    """
    columns = [_NUTRIENT_TO_COLUMN[k] for k in keys]
    column_sql = ", ".join(columns)
    cursor.execute(f"""
        SELECT {column_sql}, DATE(eaten_at) AS log_date
        FROM food_log
        WHERE user_id = ? AND DATE(eaten_at) BETWEEN ? AND ?
    """, (user_id, monday.isoformat(), sunday.isoformat()))
    rows = [dict(r) for r in cursor.fetchall()]

    week_days = []
    for i in range(7):
        d = monday + timedelta(days=i)
        week_days.append({
            "label":  WEEKDAY_LABELS[i],
            "date":   d.isoformat(),
            "values": {k: 0.0 for k in keys},
            "known":  {k: 0 for k in keys},
            "log_count": 0,
        })

    for r in rows:
        for day in week_days:
            if day["date"] == r["log_date"]:
                day["log_count"] += 1
                for k in keys:
                    val = r.get(_NUTRIENT_TO_COLUMN[k])
                    day["values"][k] += (val or 0.0)
                    if val is not None:
                        day["known"][k] += 1
                break

    return week_days, len(rows)


# 하루를 4개 시간대로 나누는 경계. get_report()의 일간 분기와 여기서 같은 값을 쓴다.
DAY_SLOTS = ["새벽", "오전", "오후", "저녁"]


def _slot_for_hour(hour: int) -> str:
    if hour < 6:
        return "새벽"
    if hour < 12:
        return "오전"
    if hour < 18:
        return "오후"
    return "저녁"


def _aggregate_day_slots(cursor, user_id: int, date_str: str, keys: list[str]) -> tuple[dict, int]:
    """하루를 4개 시간대(새벽/오전/오후/저녁)로 나눠 keys에 담긴 영양소들의 합계 +
    known 카운트를 집계한다. _aggregate_week()의 일간 버전 — keys를 받는 이유,
    values/known 중첩 구조인 이유 모두 동일하다.

    반환: (slot_data, row_count). slot_data는 DAY_SLOTS 순서 그대로 삽입되므로
    (Python dict는 삽입 순서를 보존한다) 호출부가 순서를 다시 정하지 않아도 된다.
    """
    columns = [_NUTRIENT_TO_COLUMN[k] for k in keys]
    column_sql = ", ".join(columns)
    cursor.execute(f"""
        SELECT {column_sql}, eaten_at
        FROM food_log
        WHERE user_id = ? AND DATE(eaten_at) = ?
    """, (user_id, date_str))
    rows = [dict(r) for r in cursor.fetchall()]

    slot_data = {
        s: {"values": {k: 0.0 for k in keys}, "known": {k: 0 for k in keys}, "log_count": 0}
        for s in DAY_SLOTS
    }

    for r in rows:
        try:
            hour = int(r["eaten_at"][11:13])
        except (TypeError, ValueError, IndexError):
            hour = 12
        bucket = slot_data[_slot_for_hour(hour)]
        bucket["log_count"] += 1
        for k in keys:
            val = r.get(_NUTRIENT_TO_COLUMN[k])
            bucket["values"][k] += (val or 0.0)
            if val is not None:
                bucket["known"][k] += 1

    return slot_data, len(rows)


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

    def _exposed(known_count, raw_total):
        return None if _is_data_unresolved(known_count, logged_count) else round(raw_total, 2)

    return {
        "totals": {
            "energy_kcal": _exposed(totals["known_energy_count"], total_energy),
            "carbohydrate_g": _exposed(totals["known_carbohydrate_count"], total_carb),
            "protein_g": _exposed(totals["known_protein_count"], total_protein),
            "fat_g": _exposed(totals["known_fat_count"], total_fat),
            "saturated_fat_g": _exposed(totals["known_saturated_fat_count"], total_saturated_fat),
            "trans_fat_g": _exposed(totals["known_trans_fat_count"], total_trans_fat),
            "iron_mg": _exposed(totals["known_iron_count"], total_iron),
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


def _chart_item_status(nutrients: dict, chart_keys: list[str]) -> str:
    """차트 항목(시간대/요일 버킷) 하나의 종합 status.

    compute_overall_status()는 원래 하루 전체 합계용으로 설계되어 있어, floor형
    (탄수화물/에너지/단백질)의 "미달"이 의미 있는 신호다 — 하루가 다 지나야 채워지는
    값이니까. 하지만 버킷 단위에서는 "이 새벽 시간대에 하루치 탄수화물 최소량을 못
    채웠다"가 사실상 항상 참이라 아무 의미가 없다(mompeace_ocr_design.md §7:
    "neutral은 경고로 렌더하면 안 됩니다 — 아침에 탄수화물이 부족으로 뜨는 것은
    의도된 정상 동작"). 그래서 버킷 롤업에는 ceiling/band형만 넣는다 — "이 버킷에서
    상한을 넘었는가"만 판정하고, floor형의 미달은 nutrients[key] 안에 그대로 남아
    있으니 화면이 원하면 개별적으로 볼 수 있다.

    ceiling/band형이 하나도 없으면(현재는 카페인이 항상 chart_keys 맨 앞에 있어
    도달 불가능하지만 방어적으로 대비한다) compute_overall_status()를 빈 인자로
    호출하지 않는다 — 그 경우 기본값이 "safe"인데, 아무것도 판정하지 않고 "안전"
    이라고 말하는 것은 과장이다. 대신 "unknown"을 쓴다 — 데이터가 없어서가 아니라
    판정할 ceiling/band 대상 자체가 없다는 뜻이지만, "정보없음"이 이 상황을 가장
    정직하게 표현하는 기존 어휘이기 때문이다.
    """
    rollup_statuses = [
        nutrients[k]["status"] for k in chart_keys
        if NUTRIENT_SUMMARY_FIELDS[k]["type"] != "floor"
    ]
    if not rollup_statuses:
        return "unknown"
    return compute_overall_status(*rollup_statuses)


def _build_nutrient_items(
    selected_keys: list[str], values: dict, known_counts: dict, logged_count: int, limits: dict
) -> dict:
    """/intake/summary와 같은 형태로 미리 해석된 영양소 블록.

    화면이 키→라벨/단위/색을 스스로 매핑하지 않아도 되도록 label/unit/status_label까지
    서버가 채운다. 카페인은 항상 포함하고, nutrients는 users.selected_nutrients에
    저장된 순서를 그대로 따른다. 물은 이 블록에 넣지 않는다(리포트 화면에 없음).

    ── 알려진 불일치 ──
    주간 리포트에서 이 블록의 status는 flat status.*_status와 다를 수 있다:
    여기서는 일평균을 판정하지만 flat 쪽의 caffeine/sugar/sodium/iron은 기간 합계를
    하루치 기준과 비교하기 때문이다. 별도로 정리할 사안이며, 이번 변경에서 기존 flat
    필드의 값은 건드리지 않는다.
    """
    def item(key: str) -> dict:
        return build_nutrient_summary_item(
            key, values[key], limits, known_counts[key], logged_count
        )

    return {
        "caffeine": item("caffeine"),
        "nutrients": [item(key) for key in selected_keys],
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


## AI 요약 문구 ─────────────────────────────────────────
# chart_keys(카페인 + 선택 영양소)를 그대로 훑어 tier별 문구를 고른다. 판정은
# nutrient_items(build_nutrient_summary_item 결과)에 이미 끝나 있으므로 여기서 하는
# 일은 tier_of_status() 조회와 문구 선택뿐이다 — 새 판정 로직이 아니다.
#
# 일간/주간 문구를 별도 표로 두는 이유: 주간 카드의 수치는 "그 날의 합계"가 아니라
# "기록이 있는 날들의 하루 평균"이다(§chart_keys 주석 참고). "카페인 섭취량이
# 기준을 넘었어요"를 주간 탭에 그대로 쓰면 "어느 하루 초과했다"로 읽히지만 실제
# 의미는 "이번 주 하루 평균이 하루 기준을 넘었다"로, 훨씬 무거운 진술이다. 방금
# 차트에서 고친 일간/평균 혼동을 문구에서 다시 만들지 않기 위해 두 벌을 유지한다.
_CEILING_AVOID_MESSAGES_DAILY = {
    "caffeine": "카페인 섭취량이 기준을 넘었어요. 오늘은 추가 섭취를 피하는 것이 좋아요.",
    "sugar":    "당류 섭취량이 기준을 넘었어요. 오늘은 단 음식 섭취를 줄여 주세요.",
    "sodium":   "나트륨 섭취량이 기준을 넘었어요. 오늘은 짠 음식 섭취를 줄여 주세요.",
}
_CEILING_CAUTION_MESSAGES_DAILY = {
    "caffeine": "카페인 섭취량이 기준에 가까워지고 있어요.",
    "sugar":    "당류 수치가 높아지고 있어요. 달콤한 간식은 조금 조절해 주세요.",
    "sodium":   "나트륨 수치가 높아지고 있어요. 짠 음식은 조금 조심해 주세요.",
}
_CEILING_AVOID_MESSAGES_WEEKLY = {
    "caffeine": "이번 주 카페인 평균 섭취량이 기준을 넘었어요. 오늘부터는 추가 섭취를 피하는 것이 좋아요.",
    "sugar":    "이번 주 당류 평균 섭취량이 기준을 넘었어요. 단 음식 섭취를 줄여보세요.",
    "sodium":   "이번 주 나트륨 평균 섭취량이 기준을 넘었어요. 짠 음식 섭취를 줄여보세요.",
}
_CEILING_CAUTION_MESSAGES_WEEKLY = {
    "caffeine": "이번 주 카페인 평균 섭취량이 기준에 가까워요.",
    "sugar":    "이번 주 당류 평균 섭취량이 기준에 가까워요.",
    "sodium":   "이번 주 나트륨 평균 섭취량이 높은 편이에요.",
}

# floor(에너지/탄수화물/단백질)는 이진 판정(충분/부족)뿐이라 tier만으로는 "얼마나
# 부족한지"를 못 나눈다. 이미 계산된 percent로만 문구를 고르며(새 판정 아님), 50%를
# 기준으로 두 단계로 나눈다. §7: 부족은 경고가 아니므로 두 문구 모두 다그치지 않는다.
def _floor_message(label: str, percent: float | None, *, weekly: bool) -> str:
    prefix = "이번 주 " if weekly else ""
    suffix = " 평균" if weekly else ""
    if percent is not None and percent >= 50:
        return f"{prefix}{label}{suffix} 섭취가 목표에 거의 다 왔어요. 조금만 더 신경 써주세요."
    verb = "늘려보세요" if weekly else "채워보세요"
    return f"{prefix}{label}{suffix} 섭취가 아직 많이 부족해요. 조금씩 {verb}."


# band(지방/철분)는 percent가 항상 None이라(단일 퍼센트 개념이 없음) tier/status_label로만
# 문구를 고른다. avoid/caution은 ceiling과 같은 어휘(상한 초과), neutral(low)은 floor와
# 같은 비경고 톤을 쓴다.
def _band_message(label: str, tier: str, *, weekly: bool) -> str | None:
    prefix = "이번 주 " if weekly else ""
    suffix = " 평균" if weekly else ""
    if tier == "avoid":
        action = "오늘부터는 섭취를 줄여보세요." if weekly else "오늘은 섭취를 줄이는 것이 좋아요."
        return f"{prefix}{label}{suffix} 섭취량이 상한을 넘었어요. {action}"
    if tier == "caution":
        ending = "가까워요." if weekly else "가까워지고 있어요."
        return f"{prefix}{label}{suffix} 섭취량이 상한에 {ending}"
    if tier == "neutral":
        return f"{prefix}{label}{suffix} 섭취가 부족해요. 조금 더 신경 써주세요."
    return None


_SEVERITY_RANK = {"avoid": 0, "caution": 1, "neutral": 2}
# chart_keys는 최대 4개(카페인 + 선택 최대 3개)라 이론상 4개가 한꺼번에 경고를 낼 수
# 있다. 카드가 무한히 길어지지 않도록 상한을 둔다 — 가장 심각한 tier부터, 동률이면
# chart_keys 순서(카페인 → 사용자가 저장한 선택 순서)를 그대로 유지한다.
_MAX_NUTRIENT_WARNINGS = 3


def _nutrient_warning_message(item: dict, nutrient_type: str, tier: str, *, weekly: bool) -> str | None:
    if nutrient_type == "ceiling":
        avoid_messages = _CEILING_AVOID_MESSAGES_WEEKLY if weekly else _CEILING_AVOID_MESSAGES_DAILY
        caution_messages = _CEILING_CAUTION_MESSAGES_WEEKLY if weekly else _CEILING_CAUTION_MESSAGES_DAILY
        if tier == "avoid":
            return avoid_messages[item["key"]]
        if tier == "caution":
            return caution_messages[item["key"]]
        return None
    if nutrient_type == "floor":
        if tier != "neutral":
            return None
        return _floor_message(item["label"], item["percent"], weekly=weekly)
    if nutrient_type == "band":
        return _band_message(item["label"], tier, weekly=weekly)
    return None


def _build_nutrient_warning_messages(nutrient_items: dict, *, weekly: bool) -> list[str]:
    items = [nutrient_items["caffeine"], *nutrient_items["nutrients"]]
    candidates = []
    for index, item in enumerate(items):
        nutrient_type = NUTRIENT_SUMMARY_FIELDS[item["key"]]["type"]
        tier = tier_of_status(nutrient_type, item["status"])
        if tier not in _SEVERITY_RANK:
            continue
        message = _nutrient_warning_message(item, nutrient_type, tier, weekly=weekly)
        if message is None:
            continue
        candidates.append((_SEVERITY_RANK[tier], index, message))
    candidates.sort(key=lambda c: (c[0], c[1]))
    return [message for _, _, message in candidates[:_MAX_NUTRIENT_WARNINGS]]


def _build_daily_ai_summary(
    nutrient_items: dict,
    slot_scores: dict,   # {"새벽": score, "오전": score, ...}
) -> dict:
    warning_messages = _build_nutrient_warning_messages(nutrient_items, weekly=False)
    messages = list(warning_messages)

    # 최다 섭취 시간대 (정규화 점수 기준)
    best_slot = max(slot_scores, key=lambda k: slot_scores[k])
    if slot_scores[best_slot] > 0:
        messages.append(f"{best_slot} 시간대에 섭취가 가장 많았어요.")

    if not warning_messages:
        messages.append("오늘은 전반적으로 기준 이내에서 섭취했어요.")

    return {"title": "AI 분석 요약", "messages": messages}


def _build_weekly_ai_summary(
    nutrient_items: dict,
    day_scores: list,   # [{"label": "월", "score": float}, ...]
) -> dict:
    warning_messages = _build_nutrient_warning_messages(nutrient_items, weekly=True)
    messages = list(warning_messages)

    # 최다 섭취 요일 (정규화 점수 합산 기준)
    data_days = [d for d in day_scores if d["score"] > 0]
    if len(data_days) >= 2:
        best_day = max(data_days, key=lambda d: d["score"])
        messages.append(f"이번 주는 {best_day['label']}요일에 섭취량이 가장 높았어요.")
    else:
        messages.append("이번 주는 아직 기록된 날이 적어요. 기록이 쌓이면 요일별 흐름을 더 정확히 볼 수 있어요.")

    if not warning_messages:
        messages.append("이번 주는 전반적으로 안정적인 섭취 흐름을 보였어요.")

    return {"title": "AI 분석 요약", "messages": messages}


@router.get("/report/{user_id}")
def get_report(
    user_id: int,
    period: str,
    date: str = None,
    db: sqlite3.Connection = Depends(get_db)
):
    """
    일간/주간 섭취 리포트.
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

    selected_keys = parse_selected_nutrients(user.get("selected_nutrients"))
    # chart(추이 그래프)와 nutrient_items(하단 목록)이 같은 영양소 집합을 보도록 하는
    # 단일 소스. 카페인은 항상 포함, 나머지는 사용자가 고른 최대 3개.
    chart_keys = ["caffeine"] + selected_keys
    week, age_bracket = resolve_user_nutrition_context(user)
    trimester, limits = get_trimester_limits(week, age_bracket)
    caffeine_limit = limits["caffeine_mg"]
    sugar_limit    = limits["sugar_g"]
    sodium_limit   = limits["sodium_mg"]

    # ── 일간 리포트 ──────────────────────────────────────
    if period == "daily":
        date_str = target_date.isoformat()
        # 총합(카페인/당류/나트륨 고정 3개)과 차트(카페인 + 선택 영양소)가 같은 쿼리
        # 결과를 공유하도록 합집합으로 한 번만 집계한다.
        day_keys = sorted(set(["caffeine", "sugar", "sodium"]) | set(chart_keys))
        slot_data, logged_count = _aggregate_day_slots(cursor, user_id, date_str, day_keys)

        total_caffeine = sum(b["values"]["caffeine"] for b in slot_data.values())
        total_sugar    = sum(b["values"]["sugar"]    for b in slot_data.values())
        total_sodium   = sum(b["values"]["sodium"]   for b in slot_data.values())
        known_caffeine_count = sum(b["known"]["caffeine"] for b in slot_data.values())
        known_sugar_count    = sum(b["known"]["sugar"]    for b in slot_data.values())
        known_sodium_count   = sum(b["known"]["sodium"]   for b in slot_data.values())

        caffeine_pct = _get_percent(total_caffeine, caffeine_limit)
        sugar_pct    = _get_percent(total_sugar,    sugar_limit)
        sodium_pct   = _get_percent(total_sodium,   sodium_limit)

        caffeine_status = get_status(total_caffeine, caffeine_limit, known_caffeine_count, logged_count)
        sugar_status    = get_status(total_sugar,    sugar_limit,    known_sugar_count, logged_count)
        sodium_status   = get_status(total_sodium,   sodium_limit,   known_sodium_count, logged_count)
        overall_status  = compute_overall_status(caffeine_status, sugar_status, sodium_status)

        # 시간대별 정규화 점수 (AI 요약용)
        slot_scores = {
            label: (
                _get_percent(bucket["values"]["caffeine"], caffeine_limit)
                + _get_percent(bucket["values"]["sugar"],  sugar_limit)
                + _get_percent(bucket["values"]["sodium"], sodium_limit)
            )
            for label, bucket in slot_data.items()
        }

        # 차트 항목 — 판정은 전부 build_nutrient_summary_item()을 그대로 재사용한다
        # (원칙 ④: 판정은 intake_totals.py 경유만). 여기서 하는 일은 nutrient_type
        # 조회(NUTRIENT_SUMMARY_FIELDS)와 tier_of_status() 호출뿐, 새 판정 로직이 아니다.
        chart_items = []
        for label, bucket in slot_data.items():
            nutrients = {}
            for key in chart_keys:
                item = build_nutrient_summary_item(
                    key, bucket["values"][key], limits, bucket["known"][key], bucket["log_count"]
                )
                nutrient_type = NUTRIENT_SUMMARY_FIELDS[key]["type"]
                nutrients[key] = {
                    "label":         item["label"],
                    "value":         item["total"],
                    "pct":           item["percent"],
                    "status":        item["status"],
                    "tier":          tier_of_status(nutrient_type, item["status"]),
                    "status_label":  item["status_label"],
                }
            chart_items.append({
                "label":     label,
                "status":    _chart_item_status(nutrients, chart_keys),
                "nutrients": nutrients,
            })

        extra_totals = _compute_extra_nutrient_totals(cursor, user_id, date_str, date_str)
        extra_block = _build_extra_nutrient_report_block(extra_totals, limits, divisor=1)
        water_block = _build_water_report_block(user_id, target_date, target_date, db)

        # divisor가 1이므로 일간 리포트의 판정 대상 수치는 그날의 합계 그대로다.
        nutrient_items = _build_nutrient_items(
            selected_keys,
            {
                "caffeine":     total_caffeine,
                "sugar":        total_sugar,
                "sodium":       total_sodium,
                "energy":       extra_totals["total_energy"],
                "carbohydrate": extra_totals["total_carbohydrate"],
                "protein":      extra_totals["total_protein"],
                "fat":          extra_totals["total_fat"],
                "iron":         extra_totals["total_iron"],
            },
            {
                "caffeine":     known_caffeine_count,
                "sugar":        known_sugar_count,
                "sodium":       known_sodium_count,
                "energy":       extra_totals["known_energy_count"],
                "carbohydrate": extra_totals["known_carbohydrate_count"],
                "protein":      extra_totals["known_protein_count"],
                "fat":          extra_totals["known_fat_count"],
                "iron":         extra_totals["known_iron_count"],
            },
            logged_count,
            limits,
        )

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
                "caffeine_mg": None if _is_data_unresolved(known_caffeine_count, logged_count) else round(total_caffeine, 2),
                "sugar_g":     None if _is_data_unresolved(known_sugar_count, logged_count) else round(total_sugar, 2),
                "sodium_mg":   None if _is_data_unresolved(known_sodium_count, logged_count) else round(total_sodium, 2),
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
            "nutrient_items": nutrient_items,
            "chart": {
                "type":  "time_slot",
                "title": "일간 섭취 추이",
                "items": chart_items,
            },
            "ai_summary": _build_daily_ai_summary(
                nutrient_items, slot_scores
            ),
        })

    # ── 주간 리포트 ──────────────────────────────────────
    monday = target_date - timedelta(days=target_date.weekday())
    sunday = monday + timedelta(days=6)

    # 총합(카페인/당류/나트륨 고정 3개)과 차트(카페인 + 선택 영양소)가 같은 쿼리 결과를
    # 공유하도록 합집합으로 한 번만 집계한다.
    week_keys = sorted(set(["caffeine", "sugar", "sodium"]) | set(chart_keys))
    week_days, week_row_count = _aggregate_week(cursor, user_id, monday, sunday, week_keys)

    # 주간 합계
    total_caffeine = sum(d["values"]["caffeine"] for d in week_days)
    total_sugar    = sum(d["values"]["sugar"]     for d in week_days)
    total_sodium   = sum(d["values"]["sodium"]   for d in week_days)

    known_caffeine_count = sum(d["known"]["caffeine"] for d in week_days)
    known_sugar_count    = sum(d["known"]["sugar"]    for d in week_days)
    known_sodium_count   = sum(d["known"]["sodium"]   for d in week_days)

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
                _get_percent(d["values"]["caffeine"], caffeine_limit)
                + _get_percent(d["values"]["sugar"],  sugar_limit)
                + _get_percent(d["values"]["sodium"], sodium_limit)
            ),
        }
        for d in week_days
    ]

    # 차트 항목 — 판정은 전부 build_nutrient_summary_item()을 그대로 재사용한다
    # (원칙 ④: 판정은 intake_totals.py 경유만). 일간 분기와 동일한 패턴.
    chart_items = []
    for d in week_days:
        nutrients = {}
        for key in chart_keys:
            item = build_nutrient_summary_item(
                key, d["values"][key], limits, d["known"][key], d["log_count"]
            )
            nutrient_type = NUTRIENT_SUMMARY_FIELDS[key]["type"]
            nutrients[key] = {
                "label":        item["label"],
                "value":        item["total"],
                "pct":          item["percent"],
                "status":       item["status"],
                "tier":         tier_of_status(nutrient_type, item["status"]),
                "status_label": item["status_label"],
            }
        chart_items.append({
            "label":     d["label"],
            "date":      d["date"],
            "status":    _chart_item_status(nutrients, chart_keys),
            "nutrients": nutrients,
        })

    # 지난주 대비 비교 (퍼센트포인트 차이, daily_average와 동일하게 기록이 있는 날 수 기준으로 계산)
    prev_monday = monday - timedelta(days=7)
    prev_sunday = sunday - timedelta(days=7)
    # 지난주 비교는 카페인/당류/나트륨 고정 3개만 대상이라(ReportComparison 타입 참고)
    # chart_keys 전체를 가져올 필요가 없다.
    prev_week_days, _ = _aggregate_week(cursor, user_id, prev_monday, prev_sunday, ["caffeine", "sugar", "sodium"])

    # nutrient별로 "확인된 값이 하나도 없음"을 따로 판정한다.
    # 지난 주 기록 자체가 없는 경우와, 기록은 있는데 그 nutrient만 전부 NULL인 경우를
    # 모두 포괄한다 (두 경우 다 known_count == 0).
    prev_known_caffeine_count = sum(d["known"]["caffeine"] for d in prev_week_days)
    prev_known_sugar_count    = sum(d["known"]["sugar"]    for d in prev_week_days)
    prev_known_sodium_count   = sum(d["known"]["sodium"]   for d in prev_week_days)

    prev_total_caffeine = sum(d["values"]["caffeine"] for d in prev_week_days)
    prev_total_sugar    = sum(d["values"]["sugar"]     for d in prev_week_days)
    prev_total_sodium   = sum(d["values"]["sodium"]   for d in prev_week_days)

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

    # 이 블록은 기간 합계가 아니라 일평균을 판정한다 — 하루치 기준(200mg/50g/45mg 등)과
    # 비교하려면 분자도 하루치여야 한다. 철분은 일평균을 쓰는 곳이 여기뿐이라
    # avg_iron을 여기서 처음 계산한다.
    avg_iron = round(extra_totals["total_iron"] / divisor, 1)
    nutrient_items = _build_nutrient_items(
        selected_keys,
        {
            "caffeine":     avg_caffeine,
            "sugar":        avg_sugar,
            "sodium":       avg_sodium,
            "energy":       round(extra_totals["total_energy"] / divisor, 1),
            "carbohydrate": round(extra_totals["total_carbohydrate"] / divisor, 1),
            "protein":      round(extra_totals["total_protein"] / divisor, 1),
            "fat":          round(extra_totals["total_fat"] / divisor, 1),
            "iron":         avg_iron,
        },
        {
            "caffeine":     known_caffeine_count,
            "sugar":        known_sugar_count,
            "sodium":       known_sodium_count,
            "energy":       extra_totals["known_energy_count"],
            "carbohydrate": extra_totals["known_carbohydrate_count"],
            "protein":      extra_totals["known_protein_count"],
            "fat":          extra_totals["known_fat_count"],
            "iron":         extra_totals["known_iron_count"],
        },
        week_row_count,
        limits,
    )

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
            "caffeine_mg": None if _is_data_unresolved(known_caffeine_count, week_row_count) else round(total_caffeine, 2),
            "sugar_g":     None if _is_data_unresolved(known_sugar_count, week_row_count) else round(total_sugar, 2),
            "sodium_mg":   None if _is_data_unresolved(known_sodium_count, week_row_count) else round(total_sodium, 2),
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
        "nutrient_items": nutrient_items,
        "chart": {
            "type":  "weekday",
            "title": "주간 섭취 추이",
            "items": chart_items,
        },
        # chart.items[]는 화면이 그리는 값이라 건드리지 않는다 — 이 필드는 그 옆에
        # 별도로 얹은, 화면이 읽지 않는 요일별 log_count다. get_report_ai_analysis()가
        # weekday_pattern(§AI 요약 문구)을 만들 때 "그 요일에 기록이 있었는가"를
        # 판정하는 용도로만 쓴다 — week_days는 이 함수 안의 지역 변수라 여기서 흘려
        # 보내지 않으면 호출부가 새로 쿼리해야 한다. 이미 계산된 값을 재사용할 뿐,
        # 새 쿼리는 없다.
        "weekday_log_counts": [
            {"label": d["label"], "date": d["date"], "log_count": d["log_count"]}
            for d in week_days
        ],
        "ai_summary": _build_weekly_ai_summary(
            nutrient_items, day_scores
        ),
    })


def _flagged_nutrient_keys(nutrient_items: dict) -> list[str]:
    """weekday_pattern에 포함할 영양소 키. _build_nutrient_warning_messages()와 같은
    후보 기준(tier가 avoid/caution/neutral)을 그대로 재사용한다 — 규칙 메시지에 이미
    뜬 영양소만 요일별 패턴도 함께 보여준다는 뜻이라, 새 판정 기준을 만드는 것이
    아니다."""
    items = [nutrient_items["caffeine"], *nutrient_items["nutrients"]]
    keys = []
    for item in items:
        nutrient_type = NUTRIENT_SUMMARY_FIELDS[item["key"]]["type"]
        tier = tier_of_status(nutrient_type, item["status"])
        if tier in _SEVERITY_RANK:
            keys.append(item["key"])
    return keys


def _build_weekday_pattern(report: dict, nutrient_items: dict) -> dict[str, list[dict]] | None:
    """weekly AI 설명 프롬프트에 얹을 요일별 패턴. report["chart"]["items"]에 이미
    있는 값(value/pct/status/tier)만 재사용한다 — 새 쿼리도, chart_items 자체의 수정도
    없다. daily이거나 눈에 띄는(부족/초과) 영양소가 하나도 없으면 None이라 프롬프트에
    실리지 않는다.

    로그가 아예 없는 요일(log_count==0)은 값을 그대로 흘려보내지 않는다 —
    _aggregate_week()의 초기값이 0.0이고, build_nutrient_summary_item()은
    logged_count==0인 날을 "정보 없음"이 아니라 "실제로 0"으로 노출한다(NULL≠0 가드는
    logged_count>0인데 known_count==0일 때만 작동한다, intake_totals.py 참고) — 그래서
    이 0.0이 요일별 패턴에서는 "그날 적게 먹었다"로 오독되기 쉽다. 여기서는 그 요일을
    {"label":..., "logged": False}만 남기고 value/pct/status/tier를 아예 빼서, 시스템
    지시문이 "logged가 false인 요일은 건너뛰라"는 규칙을 명확히 적용할 수 있게 한다.
    """
    if report["period"] != "weekly":
        return None
    flagged_keys = _flagged_nutrient_keys(nutrient_items)
    if not flagged_keys:
        return None

    log_count_by_label = {d["label"]: d["log_count"] for d in report["weekday_log_counts"]}
    pattern: dict[str, list[dict]] = {}
    for key in flagged_keys:
        series = []
        for day in report["chart"]["items"]:
            nutrient = day["nutrients"].get(key)
            if nutrient is None:
                continue
            if log_count_by_label.get(day["label"], 0) <= 0:
                series.append({"label": day["label"], "logged": False})
                continue
            series.append({
                "label":  day["label"],
                "logged": True,
                "value":  nutrient["value"],
                "pct":    nutrient["pct"],
                "status": nutrient["status"],
                "tier":   nutrient["tier"],
            })
        pattern[key] = series
    return pattern


class AiAnalysisRequest(BaseModel):
    user_id: int
    period: str
    date: str | None = None


@router.post("/report/ai-analysis")
def get_report_ai_analysis(req: AiAnalysisRequest, db: sqlite3.Connection = Depends(get_db)):
    """리포트 카드가 펼쳐질 때만 호출되는 2단계 AI 설명. GET /report는 이 호출을
    기다리지 않는다 — 판정(nutrient_items)과 규칙 기반 문구는 get_report()를 그대로
    재사용해 얻는다(중복 계산도, pct/divisor/limits 판정 로직의 두 번째 사본도 만들지
    않기 위해서다). 404/400 검증은 get_report()가 이미 하므로 여기서 다시 하지 않는다.

    get_ai_report_analysis()는 무엇이 실패하든 예외를 올리지 않고 rule_based로
    내려가므로, 이 엔드포인트는 별도 try/except가 필요 없다 — 카드는 항상 200을
    받는다.
    """
    report = get_report(user_id=req.user_id, period=req.period, date=req.date, db=db)
    date_key = report["date"] if report["period"] == "daily" else report["date_range"]["start"]
    return get_ai_report_analysis(
        user_id=req.user_id,
        period=report["period"],
        date_key=date_key,
        nutrient_items=report["nutrient_items"],
        rule_messages=report["ai_summary"]["messages"],
        pregnancy_week=report["pregnancy_week"],
        trimester=report["trimester"],
        weekday_pattern=_build_weekday_pattern(report, report["nutrient_items"]),
    )
