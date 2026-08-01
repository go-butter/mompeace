import sqlite3
from datetime import date

from fastapi import APIRouter, HTTPException, Depends

from backend.database import get_db
from backend.models import FoodLogCreate, FoodLogFromFood, FeedbackRequest
from backend.recommendation_model import recommend_food
from backend.risk import calculate_current_pregnancy_age
from backend.sensitivity import get_user_adj, recalculate_sensitivity
from backend.intake_totals import compute_today_intake_totals

router = APIRouter()


def _multiply(value, factor):
    if value is None:
        return None
    return round(value * factor, 4)


def _judge_food_log_from_food_item(food: dict, amount: float, user: dict, db: sqlite3.Connection) -> dict:
    """
    food_items 행 + amount로 실제 섭취량을 계산하고, 그 섭취량 기준으로
    recommend_food()를 호출한다. 1회 서빙이 아닌 실제 먹는 양을 판정해야
    누적 섭취 체크가 의미를 갖기 때문에, multiply 이후 값으로 판정한다.

    Returns: {"nutrients": {...multiplied...}, "recommendation": recommend_food() 결과}
    """
    caffeine_mg = _multiply(food.get("caffeine_mg"), amount)
    sugar_g = _multiply(food.get("sugar_g"), amount)
    sodium_mg = _multiply(food.get("sodium_mg"), amount)
    carbohydrate_g = _multiply(food.get("carbohydrate_g"), amount)
    protein_g = _multiply(food.get("protein_g"), amount)

    # today_intake는 이번에 기록할 항목을 제외한, 지금까지 누적된 양이어야 한다 (INSERT 이전 호출)
    today_intake = compute_today_intake_totals(user["user_id"], db)
    computed_age = calculate_current_pregnancy_age(
        user.get("pregnancy_week"), user.get("pregnancy_day"), user.get("pregnancy_entered_at")
    )
    week = computed_age["week"] or 20
    user_adj = get_user_adj(user)

    food_for_judgment = dict(food)
    food_for_judgment.update({
        "caffeine_mg": caffeine_mg,
        "sugar_g": sugar_g,
        "sodium_mg": sodium_mg,
        "carbohydrate_g": carbohydrate_g,
        "protein_g": protein_g,
    })

    recommendation = recommend_food(
        food=food_for_judgment,
        pregnancy_week=week,
        today_intake=today_intake,
        user_adj=user_adj,
    )

    return {
        "nutrients": {
            "caffeine_mg": caffeine_mg,
            "sugar_g": sugar_g,
            "sodium_mg": sodium_mg,
            "carbohydrate_g": carbohydrate_g,
            "protein_g": protein_g,
        },
        "recommendation": recommendation,
    }


@router.post("/food-log")
def create_food_log(
    log: FoodLogCreate,
    db: sqlite3.Connection = Depends(get_db)
):
    """음식 섭취 기록 저장"""

    cursor = db.cursor()

    # 사용자 존재 확인
    cursor.execute("SELECT * FROM users WHERE user_id = ?", (log.user_id,))
    user = cursor.fetchone()

    if not user:
        raise HTTPException(status_code=404, detail="사용자를 찾을 수 없습니다.")
    user = dict(user)

    food_name = log.food_name
    category = log.category
    caffeine_mg = log.caffeine_mg
    sugar_g = log.sugar_g
    sodium_mg = log.sodium_mg
    calories_kcal = log.calories_kcal
    carbohydrate_g = log.carbohydrate_g
    protein_g = log.protein_g
    recommendation_status = None
    reason_nutrient = None

    # food_id가 함께 전달된 경우, 직접 입력값 대신 food_items 기준 실제 섭취량으로
    # 판정한다 (create_food_log_from_food와 동일한 처리 경로).
    if log.food_id is not None:
        cursor.execute("SELECT * FROM food_items WHERE food_id = ?", (log.food_id,))
        food_row = cursor.fetchone()
        if not food_row:
            raise HTTPException(status_code=404, detail="해당 식품 정보를 찾을 수 없습니다.")
        food_row = dict(food_row)

        judged = _judge_food_log_from_food_item(food_row, log.amount, user, db)
        food_name = food_row["food_name"]
        category = food_row.get("category")
        caffeine_mg = judged["nutrients"]["caffeine_mg"]
        sugar_g = judged["nutrients"]["sugar_g"]
        sodium_mg = judged["nutrients"]["sodium_mg"]
        carbohydrate_g = judged["nutrients"]["carbohydrate_g"]
        protein_g = judged["nutrients"]["protein_g"]
        recommendation_status = judged["recommendation"]["status"]
        reason_nutrient = judged["recommendation"]["reason_nutrient"]
    elif log.serving_multiplier is not None:
        # OCR 스캔 결과(1회 제공량 기준 값)에 사용자가 확인 화면에서 입력한
        # 인분수/그램 비율을 곱한다. food_id 경로의 _multiply()와 동일한
        # None-preserving 곱셈 — food_id가 없으므로 추천 판정은 호출하지 않는다.
        caffeine_mg = _multiply(caffeine_mg, log.serving_multiplier)
        sugar_g = _multiply(sugar_g, log.serving_multiplier)
        sodium_mg = _multiply(sodium_mg, log.serving_multiplier)
    # food_id가 없는 순수 직접 입력은 recommend_food()가 기대하는 food_items
    # 행 형태(data_source 등)를 갖추지 못하므로 추천 판정을 호출하지 않는다.
    # recommendation_status/reason_nutrient는 NULL로 남는다.

    if log.eaten_at is not None:
        cursor.execute("""
            INSERT INTO food_log
            (user_id, food_id, food_name, category, input_type, amount, unit,
             caffeine_mg, sugar_g, sodium_mg, calories_kcal, carbohydrate_g, protein_g,
             recommendation_status, reason_nutrient, needs_review, eaten_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            log.user_id,
            log.food_id,
            food_name,
            category,
            log.input_type,
            log.amount,
            log.unit,
            caffeine_mg,
            sugar_g,
            sodium_mg,
            calories_kcal,
            carbohydrate_g,
            protein_g,
            recommendation_status,
            reason_nutrient,
            log.needs_review,
            log.eaten_at,
        ))
    else:
        cursor.execute("""
            INSERT INTO food_log
            (user_id, food_id, food_name, category, input_type, amount, unit,
             caffeine_mg, sugar_g, sodium_mg, calories_kcal, carbohydrate_g, protein_g,
             recommendation_status, reason_nutrient, needs_review)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            log.user_id,
            log.food_id,
            food_name,
            category,
            log.input_type,
            log.amount,
            log.unit,
            caffeine_mg,
            sugar_g,
            sodium_mg,
            calories_kcal,
            carbohydrate_g,
            protein_g,
            recommendation_status,
            reason_nutrient,
            log.needs_review,
        ))

    new_log_id = cursor.lastrowid
    if log.extra_nutrients:
        try:
            for en in log.extra_nutrients:
                cursor.execute(
                    "INSERT INTO food_log_extra_nutrients (food_log_id, name, value, unit) VALUES (?,?,?,?)",
                    (new_log_id, en.name, en.value, en.unit),
                )
        except sqlite3.IntegrityError:
            db.rollback()
            raise HTTPException(status_code=400, detail="추가 성분 정보를 저장할 수 없습니다.")
    db.commit()

    return {
        "log_id": new_log_id,
        "message": "음식 기록 완료"
    }


@router.post("/food-log/from-food")
def create_food_log_from_food(
    log: FoodLogFromFood,
    db: sqlite3.Connection = Depends(get_db)
):
    """
    food_id + amount로 Food Diary에 기록

    food_items에서 food_id로 식품 정보를 조회한 뒤,
    영양소 값에 amount를 곱해 food_log에 저장한다.
    """

    cursor = db.cursor()

    # 사용자 존재 확인
    cursor.execute("SELECT * FROM users WHERE user_id = ?", (log.user_id,))
    user = cursor.fetchone()
    if not user:
        raise HTTPException(status_code=404, detail="사용자를 찾을 수 없습니다.")
    user = dict(user)

    # 식품 존재 확인
    cursor.execute("SELECT * FROM food_items WHERE food_id = ?", (log.food_id,))
    food = cursor.fetchone()
    if not food:
        raise HTTPException(status_code=404, detail="해당 식품 정보를 찾을 수 없습니다.")

    food = dict(food)
    amount = log.amount

    judged = _judge_food_log_from_food_item(food, amount, user, db)
    nutrients = judged["nutrients"]
    recommendation = judged["recommendation"]

    cursor.execute("""
        INSERT INTO food_log
        (user_id, food_id, food_name, category, input_type, amount, unit,
         caffeine_mg, sugar_g, sodium_mg, carbohydrate_g, protein_g,
         recommendation_status, reason_nutrient)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        log.user_id,
        log.food_id,
        food["food_name"],
        food.get("category"),
        "food_id",
        amount,
        log.unit,
        nutrients["caffeine_mg"],
        nutrients["sugar_g"],
        nutrients["sodium_mg"],
        nutrients["carbohydrate_g"],
        nutrients["protein_g"],
        recommendation["status"],
        recommendation["reason_nutrient"],
    ))

    db.commit()

    return {
        "log_id": cursor.lastrowid,
        "food_name": food["food_name"],
        "amount": amount,
        "unit": log.unit,
        "nutrients": nutrients,
        "message": "음식 기록 완료"
    }


def _fetch_food_log_for_date(user_id: int, target_date: str, db: sqlite3.Connection) -> dict:
    """주어진 날짜에 먹은 음식 목록 조회: Food Diary 전체 보기 화면용"""

    cursor = db.cursor()

    # 사용자 확인
    cursor.execute("SELECT user_id FROM users WHERE user_id = ?", (user_id,))
    user = cursor.fetchone()

    if not user:
        raise HTTPException(status_code=404, detail="사용자를 찾을 수 없습니다.")

    cursor.execute("""
        SELECT * FROM food_log
        WHERE user_id = ? AND DATE(eaten_at) = ?
        ORDER BY eaten_at ASC
    """, (
        user_id,
        target_date
    ))

    logs = cursor.fetchall()

    extra_cursor = db.cursor()
    result = []

    for log in logs:
        log = dict(log)

        eaten_at = log.get("eaten_at") or ""
        time_text = ""

        # eaten_at 예시: "2026-05-24 15:10:00"
        if len(eaten_at) >= 16:
            time_text = eaten_at[11:16]

        caffeine = log.get("caffeine_mg")
        sugar = log.get("sugar_g")
        sodium = log.get("sodium_mg")

        # 각 영양소 상태: None이면 unknown
        if caffeine is None:
            caffeine_status = "unknown"
        else:
            caffeine_status = "safe" if caffeine <= 70 else "caution" if caffeine <= 200 else "avoid"

        if sugar is None:
            sugar_status = "unknown"
        else:
            sugar_status = "safe" if sugar <= 10 else "caution" if sugar <= 30 else "avoid"

        if sodium is None:
            sodium_status = "unknown"
        else:
            sodium_status = "safe" if sodium <= 500 else "caution" if sodium <= 1500 else "avoid"

        nutrition_items = [
            {
                "name": "카페인",
                "value": caffeine,
                "unit": "mg",
                "status": caffeine_status
            },
            {
                "name": "당류",
                "value": sugar,
                "unit": "g",
                "status": sugar_status
            },
            {
                "name": "나트륨",
                "value": sodium,
                "unit": "mg",
                "status": sodium_status
            }
        ]

        extra_cursor.execute(
            "SELECT name, value, unit FROM food_log_extra_nutrients WHERE food_log_id = ?",
            (log["log_id"],),
        )
        extra_nutrients = [
            {"name": r["name"], "value": r["value"], "unit": r["unit"]}
            for r in extra_cursor.fetchall()
        ]

        result.append({
            "log_id": log["log_id"],
            "user_id": log["user_id"],
            "food_id": log.get("food_id"),
            "food_name": log["food_name"],
            "category": log.get("category"),
            "input_type": log.get("input_type"),
            "amount": log.get("amount"),
            "unit": log.get("unit"),
            "eaten_at": eaten_at,
            "time": time_text,
            "risk_level": log.get("risk_level") or "safe",
            "calories_kcal": log.get("calories_kcal"),
            "sugar_g": log.get("sugar_g"),
            "sodium_mg": log.get("sodium_mg"),
            "caffeine_mg": log.get("caffeine_mg"),
            "protein_g": log.get("protein_g") or 0,
            "extra_nutrients": extra_nutrients,

            # 접힌 카드에서 바로 쓰는 값
            "summary": {
                "title": log["food_name"],
                "time": time_text
            },

            # 펼쳤을 때 쓰는 값
            "detail": {
                "title": f"{log['food_name']}의 주요 성분:",
                "nutrition": {
                    "caffeine_mg": caffeine,
                    "sugar_g": sugar,
                    "sodium_mg": sodium,
                    "calories_kcal": log.get("calories_kcal"),
                    "carbohydrate_g": log.get("carbohydrate_g"),
                    "protein_g": log.get("protein_g")
                },
                "nutrition_items": nutrition_items
            }
        })

    return {
        "user_id": user_id,
        "date": target_date,
        "count": len(result),
        "logs": result
    }


@router.get("/food-log/today/{user_id}")
def get_today_food_log(
    user_id: int,
    db: sqlite3.Connection = Depends(get_db)
):
    """오늘 먹은 음식 목록 조회: Food Diary 전체 보기 화면용"""
    today = date.today().isoformat()
    return _fetch_food_log_for_date(user_id, today, db)


@router.get("/food-log/by-date/{user_id}")
def get_food_log_by_date(
    user_id: int,
    date: str = None,
    db: sqlite3.Connection = Depends(get_db)
):
    """임의 날짜의 음식 기록 목록 조회: 캘린더 기반 Food Diary 화면용. date 미지정 시 오늘."""
    from datetime import date as date_type
    if date:
        try:
            target_date = date_type.fromisoformat(date)
        except ValueError:
            raise HTTPException(status_code=400, detail="날짜 형식이 올바르지 않습니다. YYYY-MM-DD 형식을 사용해 주세요.")
    else:
        target_date = date_type.today()

    return _fetch_food_log_for_date(user_id, target_date.isoformat(), db)


@router.delete("/food-log/{log_id}")
def delete_food_log(
    log_id: int,
    user_id: int,
    db: sqlite3.Connection = Depends(get_db)
):
    """음식 기록 삭제 (본인 기록만 삭제 가능)"""
    cursor = db.cursor()
    cursor.execute(
        "SELECT log_id FROM food_log WHERE log_id = ? AND user_id = ?",
        (log_id, user_id)
    )
    if not cursor.fetchone():
        raise HTTPException(status_code=404, detail="해당 기록을 찾을 수 없습니다.")

    cursor.execute("DELETE FROM food_log WHERE log_id = ? AND user_id = ?", (log_id, user_id))
    db.commit()

    return {"log_id": log_id, "message": "음식 기록이 삭제되었습니다."}


@router.post("/food-log/{log_id}/feedback")
def submit_feedback(
    log_id: int,
    req: FeedbackRequest,
    db: sqlite3.Connection = Depends(get_db)
):
    """음식 추천 피드백 저장 (1: 도움됨, -1: 도움 안 됨)"""
    if req.feedback not in (1, -1):
        raise HTTPException(status_code=400, detail="feedback 값은 1 또는 -1이어야 합니다.")

    cursor = db.cursor()
    cursor.execute(
        "SELECT log_id FROM food_log WHERE log_id = ? AND user_id = ?",
        (log_id, req.user_id)
    )
    if not cursor.fetchone():
        raise HTTPException(status_code=404, detail="해당 기록을 찾을 수 없습니다.")

    cursor.execute(
        "UPDATE food_log SET feedback = ? WHERE log_id = ?",
        (req.feedback, log_id)
    )
    db.commit()

    recalculate_sensitivity(req.user_id, db)

    return {"log_id": log_id, "feedback": req.feedback, "message": "피드백이 저장되었습니다."}


@router.get("/food-log/feedback/summary/{user_id}")
def get_feedback_summary(
    user_id: int,
    db: sqlite3.Connection = Depends(get_db)
):
    """사용자 피드백 요약 조회 (재학습 데이터용)"""
    cursor = db.cursor()
    cursor.execute(
        """
        SELECT log_id, food_name, feedback, risk_level, eaten_at
        FROM food_log
        WHERE user_id = ? AND feedback != 0
        ORDER BY eaten_at DESC
        """,
        (user_id,)
    )
    rows = [dict(r) for r in cursor.fetchall()]

    helpful     = sum(1 for r in rows if r["feedback"] == 1)
    not_helpful = sum(1 for r in rows if r["feedback"] == -1)

    return {
        "user_id": user_id,
        "total": len(rows),
        "helpful": helpful,
        "not_helpful": not_helpful,
        "records": rows,
    }
