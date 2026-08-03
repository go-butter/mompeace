import calendar
import sqlite3
from datetime import date

from fastapi import APIRouter, HTTPException, Depends

from backend.database import get_db
from backend.risk import calculate_current_pregnancy_age, calculate_days_until_due
from backend.intake_totals import (
    compute_overall_status,
    get_fat_status,
    get_floor_status,
    get_informational_status,
    get_status,
    get_trimester_limits,
)

router = APIRouter()


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
            COALESCE(SUM(CASE WHEN caffeine_mg IS NULL THEN 1 ELSE 0 END), 0) AS unknown_caffeine_count,
            COALESCE(SUM(sugar_g), 0) AS total_sugar,
            COALESCE(SUM(CASE WHEN sugar_g IS NULL THEN 1 ELSE 0 END), 0) AS unknown_sugar_count,
            COALESCE(SUM(sodium_mg), 0) AS total_sodium,
            COALESCE(SUM(CASE WHEN sodium_mg IS NULL THEN 1 ELSE 0 END), 0) AS unknown_sodium_count,
            COALESCE(SUM(calories_kcal), 0) AS total_calories,
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
            COALESCE(SUM(cholesterol_mg), 0) AS total_cholesterol,
            COALESCE(SUM(CASE WHEN cholesterol_mg IS NULL THEN 1 ELSE 0 END), 0) AS unknown_cholesterol_count,
            COALESCE(SUM(CASE WHEN category = 'water' THEN 1 ELSE 0 END), 0) AS water_cups
        FROM food_log
        WHERE user_id = ? AND DATE(eaten_at) = ?
    """, (
        user_id,
        target_date
    ))

    intake = dict(cursor.fetchone())

    user = dict(user)
    computed_age = calculate_current_pregnancy_age(
        user.get("pregnancy_week"), user.get("pregnancy_day"), user.get("pregnancy_entered_at")
    )
    week = computed_age["week"] or 20
    days_until_due = calculate_days_until_due(user.get("due_date"))

    # 3. 임신 단계 판별 + 4. 주차별 기준값 조회
    trimester, limits = get_trimester_limits(week)
    trimester_label = {
        "early": "임신 초기",
        "middle": "임신 중기",
        "late": "임신 후기",
    }[trimester]

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
    total_cholesterol = intake["total_cholesterol"]
    water_cups = intake["water_cups"]
    unknown_caffeine_count = intake["unknown_caffeine_count"]
    unknown_sugar_count = intake["unknown_sugar_count"]
    unknown_sodium_count = intake["unknown_sodium_count"]
    unknown_energy_count = intake["unknown_energy_count"]
    unknown_carbohydrate_count = intake["unknown_carbohydrate_count"]
    unknown_protein_count = intake["unknown_protein_count"]
    unknown_fat_count = intake["unknown_fat_count"]
    unknown_saturated_fat_count = intake["unknown_saturated_fat_count"]
    unknown_trans_fat_count = intake["unknown_trans_fat_count"]
    unknown_cholesterol_count = intake["unknown_cholesterol_count"]

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
    caffeine_status = get_status(total_caffeine, caffeine_limit, unknown_caffeine_count)
    sugar_status = get_status(total_sugar, sugar_limit, unknown_sugar_count)
    sodium_status = get_status(total_sodium, sodium_limit, unknown_sodium_count)
    carbohydrate_status = get_floor_status(total_carbohydrate, carbohydrate_minimum, unknown_carbohydrate_count)
    protein_status = get_floor_status(total_protein, protein_target, unknown_protein_count)
    energy_status = get_floor_status(total_calories, energy_target, unknown_energy_count)
    fat_status = get_fat_status(total_fat, total_calories, fat_ratio_min, fat_ratio_max, unknown_fat_count)
    saturated_fat_status = get_status(
        total_saturated_fat, total_calories * saturated_fat_ratio_max, unknown_saturated_fat_count
    )
    trans_fat_status = get_status(
        total_trans_fat, total_calories * trans_fat_ratio_max, unknown_trans_fat_count
    )
    cholesterol_status = get_informational_status(
        None if unknown_cholesterol_count > 0 else total_cholesterol
    )

    # overall_status는 기존과 동일하게 카페인/당류/나트륨만으로 계산한다.
    # 새로 추가된 영양소(탄수화물/단백질/에너지/지방류)는 아직 대부분의 food_log 행에
    # 값이 없어(NULL) 여기에 포함시키면 overall_status가 거의 항상 unknown으로
    # 뒤덮여버린다 — 각 영양소별 status는 개별 필드로만 노출한다.
    overall_status = compute_overall_status(caffeine_status, sugar_status, sodium_status)

    # 8. 화면용 한글 라벨
    def status_label(status):
        labels = {
            "safe": "여유",
            "caution": "주의",
            "avoid": "초과",
            "sufficient": "충분",
            "low": "부족 주의",
            "insufficient": "부족",
            "info": "참고",
        }
        return labels.get(status, "정보없음")

    # 9. Food Diary 하단 분석 메시지 생성
    messages = []

    if total_caffeine == 0 and total_sugar == 0 and total_sodium == 0:
        summary_title = "아직 기록된 음식이 없어요 :)"
        messages.append("Food Diary 혹은 바코드 스캔을 통해 음식을 추가해 주세요.")
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
            messages.append("임신 초기에는 카페인과 알레르기 정보를 꼼꼼히 확인해 주세요.")
        elif trimester == "middle":
            messages.append("임신 중기에는 당류와 카페인 섭취 흐름을 함께 확인해 주세요.")
        else:
            messages.append("임신 후기에는 나트륨 섭취가 누적되지 않도록 확인해 주세요.")

    # 10. 프론트 카드용 응답
    return {
        "user_id": user_id,
        "date": target_date,
        "pregnancy_week": week,
        "pregnancy_day": computed_age["day"],
        "due_date": user.get("due_date"),
        "days_until_due": days_until_due,
        "trimester": trimester,
        "trimester_label": trimester_label,
        "water_cups": water_cups,

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
            "total_cholesterol": total_cholesterol,
            "unknown_caffeine_count": unknown_caffeine_count,
            "unknown_sugar_count": unknown_sugar_count,
            "unknown_sodium_count": unknown_sodium_count,
            "unknown_energy_count": unknown_energy_count,
            "unknown_carbohydrate_count": unknown_carbohydrate_count,
            "unknown_protein_count": unknown_protein_count,
            "unknown_fat_count": unknown_fat_count,
            "unknown_saturated_fat_count": unknown_saturated_fat_count,
            "unknown_trans_fat_count": unknown_trans_fat_count,
            "unknown_cholesterol_count": unknown_cholesterol_count
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
            "cholesterol_status": cholesterol_status
        },

        "status_label": {
            "overall": status_label(overall_status),
            "caffeine": status_label(caffeine_status),
            "sugar": status_label(sugar_status),
            "sodium": status_label(sodium_status),
            "carbohydrate": status_label(carbohydrate_status),
            "protein": status_label(protein_status),
            "energy": status_label(energy_status),
            "fat": status_label(fat_status),
            "saturated_fat": status_label(saturated_fat_status),
            "trans_fat": status_label(trans_fat_status),
            "cholesterol": status_label(cholesterol_status)
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

    computed_age = calculate_current_pregnancy_age(
        user.get("pregnancy_week"), user.get("pregnancy_day"), user.get("pregnancy_entered_at")
    )
    week = computed_age["week"] or 20
    _, limits = get_trimester_limits(week)
    caffeine_limit = limits["caffeine_mg"]
    sugar_limit = limits["sugar_g"]
    sodium_limit = limits["sodium_mg"]

    cursor.execute("""
        SELECT
            DATE(eaten_at) AS log_date,
            COALESCE(SUM(caffeine_mg), 0) AS total_caffeine,
            COALESCE(SUM(CASE WHEN caffeine_mg IS NULL THEN 1 ELSE 0 END), 0) AS unknown_caffeine_count,
            COALESCE(SUM(sugar_g), 0) AS total_sugar,
            COALESCE(SUM(CASE WHEN sugar_g IS NULL THEN 1 ELSE 0 END), 0) AS unknown_sugar_count,
            COALESCE(SUM(sodium_mg), 0) AS total_sodium,
            COALESCE(SUM(CASE WHEN sodium_mg IS NULL THEN 1 ELSE 0 END), 0) AS unknown_sodium_count
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
        caffeine_status = get_status(row["total_caffeine"], caffeine_limit, row["unknown_caffeine_count"])
        sugar_status = get_status(row["total_sugar"], sugar_limit, row["unknown_sugar_count"])
        sodium_status = get_status(row["total_sodium"], sodium_limit, row["unknown_sodium_count"])
        overall_status = compute_overall_status(caffeine_status, sugar_status, sodium_status)
        days.append({"date": row["log_date"], "overall_status": overall_status})

    return {
        "user_id": user_id,
        "year": year,
        "month": month,
        "days": days
    }
