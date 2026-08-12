import calendar
import sqlite3
from datetime import date

from fastapi import APIRouter, HTTPException, Depends

from backend.database import get_db
from backend.nutrition_constants import (
    IRON_RECOMMENDED_MG,
    IRON_UPPER_LIMIT_MG,
    KCAL_PER_GRAM_FAT,
    NUTRIENT_LABELS_KO,
    parse_selected_nutrients,
)
from backend.risk import calculate_current_pregnancy_age, calculate_days_until_due
from backend.intake_totals import (
    TRIMESTER_LABELS,
    compute_overall_status,
    fetch_daily_nutrient_totals,
    get_fat_status,
    get_floor_status,
    get_iron_status,
    get_status,
    get_trimester_limits,
    build_nutrient_summary_item,
    resolve_user_nutrition_context,
    simplified_status_label,
)
from backend.routers.water_log import fetch_water_summary_for_date

router = APIRouter()


def _get_percent(value, standard):
    if standard is None or standard <= 0:
        return 0
    return round(value / standard * 100, 1)


# 집계 컬럼명 → build_nutrient_summary_item()에 넘길 (값, known 개수).
# 판정 방식/단위/라벨은 intake_totals.NUTRIENT_SUMMARY_FIELDS가 들고 있고, 여기서는
# 이 엔드포인트의 집계 쿼리 컬럼명만 매핑한다.
_SUMMARY_TOTAL_KEYS = {
    "carbohydrate": ("total_carbohydrate", "known_carbohydrate_count"),
    "sugar":        ("total_sugar", "known_sugar_count"),
    "energy":       ("total_calories", "known_energy_count"),
    "fat":          ("total_fat", "known_fat_count"),
    "iron":         ("total_iron", "known_iron_count"),
    "protein":      ("total_protein", "known_protein_count"),
    "sodium":       ("total_sodium", "known_sodium_count"),
    "caffeine":     ("total_caffeine", "known_caffeine_count"),
}


def _build_nutrient_summary_item(key: str, totals: dict, limits: dict) -> dict:
    total_key, known_key = _SUMMARY_TOTAL_KEYS[key]
    return build_nutrient_summary_item(
        key, totals[total_key], limits, totals[known_key], totals["logged_count"]
    )


def _fetch_intake_summary_for_date(user_id: int, target_date: str, db: sqlite3.Connection) -> dict:
    """주어진 날짜의 누적 섭취량 계산 + Food Diary 화면용 응답"""

    cursor = db.cursor()

    # 1. 사용자 확인
    cursor.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
    user = cursor.fetchone()

    if not user:
        raise HTTPException(status_code=404, detail="사용자를 찾을 수 없습니다.")

    # 2. 오늘 섭취량 합산
    cursor.execute("""
        SELECT
            COALESCE(SUM(caffeine_mg), 0) AS total_caffeine,
            COUNT(caffeine_mg) AS known_caffeine_count,
            COALESCE(SUM(sugar_g), 0) AS total_sugar,
            COUNT(sugar_g) AS known_sugar_count,
            COALESCE(SUM(sodium_mg), 0) AS total_sodium,
            COUNT(sodium_mg) AS known_sodium_count,
            COALESCE(SUM(calories_kcal), 0) AS total_calories,
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
        WHERE user_id = ? AND DATE(eaten_at) = ?
    """, (
        user_id,
        target_date
    ))

    intake = dict(cursor.fetchone())

    user = dict(user)
    week, age_bracket = resolve_user_nutrition_context(user)
    computed_day = calculate_current_pregnancy_age(
        user.get("pregnancy_week"), user.get("pregnancy_day"), user.get("pregnancy_entered_at")
    )["day"]
    days_until_due = calculate_days_until_due(user.get("due_date"))

    # 3. 임신 단계 판별 + 4. 주차별 기준값 조회
    trimester, limits = get_trimester_limits(week, age_bracket)
    trimester_label = TRIMESTER_LABELS[trimester]

    caffeine_limit = limits["caffeine_mg"]
    sugar_limit = limits["sugar_g"]
    sodium_limit = limits["sodium_mg"]
    carbohydrate_minimum = limits["carbohydrate_g"]
    protein_target = limits["protein_g"]
    energy_target = limits["energy_kcal"]
    fat_ratio_min = limits["fat_ratio_min"]
    fat_ratio_max = limits["fat_ratio_max"]
    saturated_fat_ratio_max = limits["saturated_fat_ratio_max"]
    trans_fat_ratio_max = limits["trans_fat_ratio_max"]

    total_caffeine = intake["total_caffeine"]
    total_sugar = intake["total_sugar"]
    total_sodium = intake["total_sodium"]
    total_calories = intake["total_calories"]
    total_carbohydrate = intake["total_carbohydrate"]
    total_protein = intake["total_protein"]
    total_fat = intake["total_fat"]
    total_saturated_fat = intake["total_saturated_fat"]
    total_trans_fat = intake["total_trans_fat"]
    total_iron = intake["total_iron"]
    known_caffeine_count = intake["known_caffeine_count"]
    known_sugar_count = intake["known_sugar_count"]
    known_sodium_count = intake["known_sodium_count"]
    known_energy_count = intake["known_energy_count"]
    known_carbohydrate_count = intake["known_carbohydrate_count"]
    known_protein_count = intake["known_protein_count"]
    known_fat_count = intake["known_fat_count"]
    known_saturated_fat_count = intake["known_saturated_fat_count"]
    known_trans_fat_count = intake["known_trans_fat_count"]
    known_iron_count = intake["known_iron_count"]
    logged_count = intake["logged_count"]

    # 5. 잔여 허용량 계산 (상한선 영양소) / 목표까지 남은 양 계산 (하한선 영양소)
    remaining_caffeine = round(max(0, caffeine_limit - total_caffeine), 2)
    remaining_sugar = round(max(0, sugar_limit - total_sugar), 2)
    remaining_sodium = round(max(0, sodium_limit - total_sodium), 2)
    remaining_carbohydrate = round(max(0, carbohydrate_minimum - total_carbohydrate), 2)
    remaining_protein = round(max(0, protein_target - total_protein), 2)
    remaining_energy = round(max(0, energy_target - total_calories), 2)

    # 6. 퍼센트 계산
    def get_percent(value, standard):
        if standard <= 0:
            return 0
        return round((value / standard) * 100, 1)

    caffeine_percent = get_percent(total_caffeine, caffeine_limit)
    sugar_percent = get_percent(total_sugar, sugar_limit)
    sodium_percent = get_percent(total_sodium, sodium_limit)
    carbohydrate_percent = get_percent(total_carbohydrate, carbohydrate_minimum)
    protein_percent = get_percent(total_protein, protein_target)
    energy_percent = get_percent(total_calories, energy_target)

    # 7. 상태 계산
    caffeine_status = get_status(total_caffeine, caffeine_limit, known_caffeine_count, logged_count)
    sugar_status = get_status(total_sugar, sugar_limit, known_sugar_count, logged_count)
    sodium_status = get_status(total_sodium, sodium_limit, known_sodium_count, logged_count)
    carbohydrate_status = get_floor_status(total_carbohydrate, carbohydrate_minimum, known_carbohydrate_count, logged_count)
    protein_status = get_floor_status(total_protein, protein_target, known_protein_count, logged_count)
    energy_status = get_floor_status(total_calories, energy_target, known_energy_count, logged_count)
    # 지방의 분모는 하루 에너지 목표(energy_target)다 — 누적 섭취량(total_calories)이
    # 아니다. 아래 포화지방/트랜스지방은 별개 영양소라 이번 변경 범위 밖이며 기존대로
    # 누적 에너지를 쓴다(같은 성격의 문제가 있으나 별도 결정 사항).
    fat_status = get_fat_status(total_fat, energy_target, fat_ratio_min, fat_ratio_max, known_fat_count, logged_count)
    # energy_total(kcal) * ratio는 kcal 단위이므로, 그램 단위인 total_saturated_fat/
    # total_trans_fat과 비교하려면 KCAL_PER_GRAM_FAT(9kcal/g)로 나눠 환산해야 한다
    # (get_fat_status()와 동일한 이유 — 환산 없이 비교하면 기준이 사실상 무의미해진다).
    saturated_fat_status = get_status(
        total_saturated_fat,
        total_calories * saturated_fat_ratio_max / KCAL_PER_GRAM_FAT,
        known_saturated_fat_count,
        logged_count,
    )
    trans_fat_status = get_status(
        total_trans_fat,
        total_calories * trans_fat_ratio_max / KCAL_PER_GRAM_FAT,
        known_trans_fat_count,
        logged_count,
    )
    iron_status = get_iron_status(total_iron, IRON_RECOMMENDED_MG, IRON_UPPER_LIMIT_MG, known_iron_count, logged_count)

    # overall_status는 기존과 동일하게 카페인/당류/나트륨만으로 계산한다.
    # 새로 추가된 영양소(탄수화물/단백질/에너지/지방류)는 아직 대부분의 food_log 행에
    # 값이 없어(NULL) 여기에 포함시키면 overall_status가 거의 항상 unknown으로
    # 뒤덮여버린다 — 각 영양소별 status는 개별 필드로만 노출한다.
    overall_status = compute_overall_status(caffeine_status, sugar_status, sodium_status)

    # 8. Food Diary 하단 분석 메시지 생성
    messages = []

    if total_caffeine == 0 and total_sugar == 0 and total_sodium == 0:
        summary_title = "아직 기록된 음식이 없어요 :)"
        messages.append("Food Diary 혹은 영양성분표 스캔을 통해 음식을 추가해 주세요.")
    else:
        if overall_status == "safe":
            summary_title = "오늘은 아직 기준 이내예요 :)"
        elif overall_status == "unknown":
            summary_title = "오늘은 일부 정보가 확인되지 않았어요"
        elif overall_status == "caution":
            summary_title = "오늘은 섭취량을 조금 조심하세요 :)"
        else:
            summary_title = "오늘은 추가 섭취를 주의하세요!"

        if caffeine_status == "unknown":
            messages.append("카페인 정보를 알 수 없는 음식이 있어요. 섭취량 확인이 어려워요.")
        elif caffeine_status == "caution":
            messages.append("카페인 섭취량이 기준에 가까워지고 있어요.")
        elif caffeine_status == "avoid":
            messages.append("카페인 섭취량이 기준을 넘었어요. 오늘은 추가 섭취를 피하는 것이 좋아요.")

        if sugar_status == "safe":
            messages.append("당류는 현재 기준 이내예요.")
        elif sugar_status == "unknown":
            messages.append("당류 정보를 알 수 없는 음식이 있어요. 섭취량 확인이 어려워요.")
        elif sugar_status == "caution":
            messages.append("당류 수치가 높아지고 있어요. 달콤한 간식은 조금 조절해 주세요.")
        elif sugar_status == "avoid":
            messages.append("당류 섭취량이 기준을 넘었어요. 오늘은 단 음식 섭취를 줄여 주세요.")

        if sodium_status == "safe":
            messages.append("나트륨은 현재 기준 이내예요.")
        elif sodium_status == "unknown":
            messages.append("나트륨 정보를 알 수 없는 음식이 있어요. 섭취량 확인이 어려워요.")
        elif sodium_status == "caution":
            messages.append("나트륨 수치가 높아지고 있어요. 짠 음식은 조금 조심해 주세요.")
        elif sodium_status == "avoid":
            messages.append("나트륨 섭취량이 기준을 넘었어요. 오늘은 짠 음식 섭취를 줄여 주세요.")

        if trimester == "early":
            messages.append("임신 초기에는 카페인과 하루 영양소 기준을 꼼꼼히 확인해 주세요.")
        elif trimester == "middle":
            messages.append("임신 중기에는 당류와 카페인 섭취 흐름을 함께 확인해 주세요.")
        else:
            messages.append("임신 후기에는 나트륨 섭취가 누적되지 않도록 확인해 주세요.")

    # 9. 프론트 카드용 응답
    return {
        "user_id": user_id,
        "date": target_date,
        "pregnancy_week": week,
        "pregnancy_day": computed_day,
        "due_date": user.get("due_date"),
        "days_until_due": days_until_due,
        "trimester": trimester,
        "trimester_label": trimester_label,

        "intake": {
            "total_caffeine": total_caffeine,
            "total_sugar": total_sugar,
            "total_sodium": total_sodium,
            "total_calories": total_calories,
            "total_carbohydrate": total_carbohydrate,
            "total_protein": total_protein,
            "total_fat": total_fat,
            "total_saturated_fat": total_saturated_fat,
            "total_trans_fat": total_trans_fat,
            "total_iron": total_iron,
            "known_caffeine_count": known_caffeine_count,
            "known_sugar_count": known_sugar_count,
            "known_sodium_count": known_sodium_count,
            "known_energy_count": known_energy_count,
            "known_carbohydrate_count": known_carbohydrate_count,
            "known_protein_count": known_protein_count,
            "known_fat_count": known_fat_count,
            "known_saturated_fat_count": known_saturated_fat_count,
            "known_trans_fat_count": known_trans_fat_count,
            "known_iron_count": known_iron_count,
            "logged_count": logged_count
        },

        "limits": {
            "caffeine_limit_mg": caffeine_limit,
            "sugar_limit_g": sugar_limit,
            "sodium_limit_mg": sodium_limit,
            "carbohydrate_minimum_g": carbohydrate_minimum,
            "protein_target_g": protein_target,
            "energy_target_kcal": energy_target,
            "fat_ratio_min": fat_ratio_min,
            "fat_ratio_max": fat_ratio_max,
            "saturated_fat_ratio_max": saturated_fat_ratio_max,
            "trans_fat_ratio_max": trans_fat_ratio_max
        },

        "remaining": {
            "remaining_caffeine": remaining_caffeine,
            "remaining_sugar": remaining_sugar,
            "remaining_sodium": remaining_sodium,
            "remaining_carbohydrate": remaining_carbohydrate,
            "remaining_protein": remaining_protein,
            "remaining_energy": remaining_energy
        },

        "progress": {
            "caffeine_percent": caffeine_percent,
            "sugar_percent": sugar_percent,
            "sodium_percent": sodium_percent,
            "carbohydrate_percent": carbohydrate_percent,
            "protein_percent": protein_percent,
            "energy_percent": energy_percent
        },

        "status": {
            "overall_status": overall_status,
            "caffeine_status": caffeine_status,
            "sugar_status": sugar_status,
            "sodium_status": sodium_status,
            "carbohydrate_status": carbohydrate_status,
            "protein_status": protein_status,
            "energy_status": energy_status,
            "fat_status": fat_status,
            "saturated_fat_status": saturated_fat_status,
            "trans_fat_status": trans_fat_status,
            "iron_status": iron_status
        },

        # 홈 화면(/intake/summary)과 동일한 어휘(simplified_status_label)를 재사용한다 —
        # 같은 상태 코드가 화면마다 다른 단어로 보이면 사용자가 혼란스러워할 수 있다.
        # overall/caffeine/sugar/sodium/saturated_fat/trans_fat은 get_status()(ceiling)
        # 결과이고, carbohydrate/protein/energy는 get_floor_status()(floor), fat/iron은
        # band(get_fat_status()/get_iron_status())다 — NUTRIENT_SUMMARY_FIELDS의 type 매핑과 동일하다.
        "status_label": {
            "overall": simplified_status_label("ceiling", overall_status),
            "caffeine": simplified_status_label("ceiling", caffeine_status),
            "sugar": simplified_status_label("ceiling", sugar_status),
            "sodium": simplified_status_label("ceiling", sodium_status),
            "carbohydrate": simplified_status_label("floor", carbohydrate_status),
            "protein": simplified_status_label("floor", protein_status),
            "energy": simplified_status_label("floor", energy_status),
            "fat": simplified_status_label("band", fat_status),
            "saturated_fat": simplified_status_label("ceiling", saturated_fat_status),
            "trans_fat": simplified_status_label("ceiling", trans_fat_status),
            "iron": simplified_status_label("band", iron_status)
        },

        "summary": {
            "title": summary_title,
            "messages": messages
        },

        "note": limits["note"]
    }


@router.get("/intake/today/{user_id}")
def get_today_intake(
    user_id: int,
    db: sqlite3.Connection = Depends(get_db)
):
    """오늘 누적 섭취량 계산 + Food Diary 화면용 응답"""
    today = date.today().isoformat()
    return _fetch_intake_summary_for_date(user_id, today, db)


@router.get("/intake/by-date/{user_id}")
def get_intake_by_date(
    user_id: int,
    date: str = None,
    db: sqlite3.Connection = Depends(get_db)
):
    """임의 날짜의 누적 섭취량 조회: 캘린더 기반 Food Diary 화면용. date 미지정 시 오늘."""
    from datetime import date as date_type
    if date:
        try:
            target_date = date_type.fromisoformat(date)
        except ValueError:
            raise HTTPException(status_code=400, detail="날짜 형식이 올바르지 않습니다. YYYY-MM-DD 형식을 사용해 주세요.")
    else:
        target_date = date_type.today()

    return _fetch_intake_summary_for_date(user_id, target_date.isoformat(), db)


@router.get("/intake/summary/{user_id}")
def get_intake_summary(
    user_id: int,
    date: str = None,
    db: sqlite3.Connection = Depends(get_db)
):
    """홈/Food Diary 요약 카드용 응답: 카페인 + 물(항상 표시) + 사용자가 선택한 영양소,
    date로 지정한 하루 기준 (미지정 시 오늘).

    users.selected_nutrients를 서버에서 직접 조회한다 — 클라이언트가 어떤 영양소를
    요청할지 지정하지 않고, DB에 저장된 선택을 그대로 신뢰한다(단일 소스 오브 트루스).
    Food Diary/리포트용 전체 응답(_fetch_intake_summary_for_date, 리포트의 자체
    집계)과는 완전히 별개이며 서로의 응답 형태에 영향을 주지 않는다.
    """
    from datetime import date as date_type

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
    today = target_date.isoformat()

    # 집계 쿼리는 intake_totals.py로 옮겨 OCR 확인 화면의 일일 투영 판정과 공유한다 —
    # 같은 쿼리를 두 벌 두면 하루 경계나 known_count 규칙이 서로 어긋날 수 있고,
    # 그러면 요약 화면과 확인 화면이 같은 날에 다른 숫자를 보여주게 된다.
    totals = fetch_daily_nutrient_totals(user_id, today, db)

    week, age_bracket = resolve_user_nutrition_context(user)
    _, limits = get_trimester_limits(week, age_bracket)

    caffeine_item = _build_nutrient_summary_item("caffeine", totals, limits)

    water = fetch_water_summary_for_date(user_id, today, db)
    # water_log.amount_ml은 NOT NULL이므로 항상 known으로 취급한다.
    water_status = get_floor_status(water["total_ml"], water["target_ml"], known_count=1, logged_count=1)
    water_item = {
        "key": "water",
        "label": NUTRIENT_LABELS_KO["water"],
        "total": water["total_ml"],
        "unit": "mL",
        "limit": water["target_ml"],
        "percent": water["percent"],
        "status": water_status,
        "status_label": simplified_status_label("floor", water_status),
    }

    selected_keys = parse_selected_nutrients(user.get("selected_nutrients"))
    selected_items = [_build_nutrient_summary_item(key, totals, limits) for key in selected_keys]

    return {
        "user_id": user_id,
        "date": today,
        "caffeine": caffeine_item,
        "water": water_item,
        "selected_nutrients": selected_items,
    }


@router.get("/food-log/calendar/{user_id}")
def get_food_log_calendar(
    user_id: int,
    year: int,
    month: int,
    db: sqlite3.Connection = Depends(get_db)
):
    """월 단위로 음식 기록이 있는 날짜 목록 조회: 캘린더 점 표시용"""
    from datetime import date as date_type

    if not (1 <= month <= 12):
        raise HTTPException(status_code=400, detail="month는 1에서 12 사이여야 합니다.")

    cursor = db.cursor()

    cursor.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
    user_row = cursor.fetchone()
    if not user_row:
        raise HTTPException(status_code=404, detail="사용자를 찾을 수 없습니다.")
    user = dict(user_row)

    _, last_day_num = calendar.monthrange(year, month)
    first_day = date_type(year, month, 1)
    last_day = date_type(year, month, last_day_num)

    week, age_bracket = resolve_user_nutrition_context(user)
    _, limits = get_trimester_limits(week, age_bracket)
    caffeine_limit = limits["caffeine_mg"]
    sugar_limit = limits["sugar_g"]
    sodium_limit = limits["sodium_mg"]

    cursor.execute("""
        SELECT
            DATE(eaten_at) AS log_date,
            COALESCE(SUM(caffeine_mg), 0) AS total_caffeine,
            COUNT(caffeine_mg) AS known_caffeine_count,
            COALESCE(SUM(sugar_g), 0) AS total_sugar,
            COUNT(sugar_g) AS known_sugar_count,
            COALESCE(SUM(sodium_mg), 0) AS total_sodium,
            COUNT(sodium_mg) AS known_sodium_count,
            COUNT(*) AS logged_count
        FROM food_log
        WHERE user_id = ? AND DATE(eaten_at) BETWEEN ? AND ?
        GROUP BY DATE(eaten_at)
        ORDER BY log_date
    """, (
        user_id,
        first_day.isoformat(),
        last_day.isoformat()
    ))

    days = []
    for row in cursor.fetchall():
        row = dict(row)
        caffeine_status = get_status(row["total_caffeine"], caffeine_limit, row["known_caffeine_count"], row["logged_count"])
        sugar_status = get_status(row["total_sugar"], sugar_limit, row["known_sugar_count"], row["logged_count"])
        sodium_status = get_status(row["total_sodium"], sodium_limit, row["known_sodium_count"], row["logged_count"])
        overall_status = compute_overall_status(caffeine_status, sugar_status, sodium_status)
        days.append({"date": row["log_date"], "overall_status": overall_status})

    return {
        "user_id": user_id,
        "year": year,
        "month": month,
        "days": days
    }
