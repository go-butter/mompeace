from fastapi import FastAPI, HTTPException, Depends
import sqlite3
from datetime import date, datetime
from backend.food_repository import save_food_item
from backend.food_search_api import search_food_nutrition
from backend.database import get_db, init_db, cleanup_expired_food_logs, DB_PATH
from backend.models import (
    RegisterRequest,
    LoginRequest,
    UserCreate,
    PregnancyUpdate,
    AllergyUpdate,
    FoodLogCreate,
    FoodLogFromFood,
    RecommendationRequest,
    PremiumUpgradeRequest,
    FeedbackRequest,
    PremiumStatusResponse,
)
from backend.recommendation_model import recommend_food
from backend.data_confidence import calculate_data_confidence
from backend.auth import register_user, login_user
from backend.foodqr import get_food_info, simplify_food_info
from backend.risk import evaluate_food_risk


app = FastAPI(title="맘편하게 API", version="1.0.0")


# ── 앱 시작 시 DB 초기화 및 만료 로그 정리 ──────────────
init_db()
with sqlite3.connect(DB_PATH) as _startup_db:
    cleanup_expired_food_logs(_startup_db)


# ── 기본 확인 ─────────────────────────────────────────

@app.get("/")
def root():
    return {"message": "맘편하게 API 서버 정상 작동 중 🤱"}


# ── 회원가입 / 로그인 ─────────────────────────────────

@app.post("/auth/register")
def register(
    user: RegisterRequest,
    db: sqlite3.Connection = Depends(get_db)
):
    """회원가입"""
    return register_user(user, db)


@app.post("/auth/login")
def login(
    user: LoginRequest,
    db: sqlite3.Connection = Depends(get_db)
):
    """로그인"""
    return login_user(user, db)


# ── 사용자 정보 ───────────────────────────────────────

@app.post("/users")
def create_user(
    user: UserCreate,
    db: sqlite3.Connection = Depends(get_db)
):
    """사용자 임신 정보 저장"""

    cursor = db.cursor()

    pregnancy_week = user.pregnancy_week

    # 예정일 기반 임신 주차 자동 계산
    if user.due_date and not pregnancy_week:
        due = datetime.strptime(user.due_date, "%Y-%m-%d").date()
        today = date.today()
        days_remaining = (due - today).days
        days_pregnant = 280 - days_remaining
        pregnancy_week = max(1, days_pregnant // 7)

    cursor.execute("""
        INSERT INTO users (
            nickname,
            pregnancy_week,
            due_date,
            allergy_info,
            interest_ingredients
        )
        VALUES (?, ?, ?, ?, ?)
    """, (
        user.nickname,
        pregnancy_week,
        user.due_date,
        user.allergy_info,
        user.interest_ingredients
    ))

    db.commit()

    return {
        "user_id": cursor.lastrowid,
        "nickname": user.nickname,
        "pregnancy_week": pregnancy_week,
        "due_date": user.due_date,
        "message": "사용자 등록 완료"
    }


@app.get("/users/{user_id}")
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


@app.put("/users/{user_id}/pregnancy")
def update_pregnancy_info(
    user_id: int,
    info: PregnancyUpdate,
    db: sqlite3.Connection = Depends(get_db)
):
    """임신 주차 및 출산 예정일 수정"""

    cursor = db.cursor()

    cursor.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
    user = cursor.fetchone()

    if not user:
        raise HTTPException(status_code=404, detail="사용자를 찾을 수 없습니다.")

    cursor.execute("""
        UPDATE users
        SET pregnancy_week = ?, due_date = ?
        WHERE user_id = ?
    """, (
        info.pregnancy_week,
        info.due_date,
        user_id
    ))

    db.commit()

    return {
        "user_id": user_id,
        "pregnancy_week": info.pregnancy_week,
        "due_date": info.due_date,
        "message": "임신 정보 수정 완료"
    }


@app.put("/users/{user_id}/allergy")
def update_allergy_info(
    user_id: int,
    info: AllergyUpdate,
    db: sqlite3.Connection = Depends(get_db)
):
    """알레르기 정보 수정"""

    cursor = db.cursor()

    cursor.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
    user = cursor.fetchone()

    if not user:
        raise HTTPException(status_code=404, detail="사용자를 찾을 수 없습니다.")

    cursor.execute("""
        UPDATE users
        SET allergy_info = ?
        WHERE user_id = ?
    """, (
        info.allergy_info,
        user_id
    ))

    db.commit()

    return {
        "user_id": user_id,
        "allergy_info": info.allergy_info,
        "message": "알레르기 정보 수정 완료"
    }


# ── 식품 정보 ─────────────────────────────────────────

@app.get("/foods/barcode/{barcode}")
def get_food_by_barcode(
    barcode: str,
    pregnancy_week: int = 20,
    db: sqlite3.Connection = Depends(get_db)
):
    """
    바코드 기반 식품 정보 조회

    1. 푸드QR API에서 먼저 조회
    2. 제품 정보가 없으면 404
    3. 제품 정보가 있으면 앱용 데이터로 정리
    4. food_items 테이블에 저장/업데이트 후 food_id 반환
    5. 임신 주차 기준 위험도 판단 결과 포함
    """

    try:
        api_data = get_food_info(barcode)
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"푸드QR API 호출 실패: {str(e)}"
        )

    if not api_data:
        raise HTTPException(
            status_code=404,
            detail="푸드QR에서 해당 바코드 제품을 찾을 수 없습니다."
        )

    simplified_data = simplify_food_info(api_data)

    if not simplified_data:
        raise HTTPException(
            status_code=404,
            detail="푸드QR에서 해당 바코드 제품의 기본정보를 찾을 수 없습니다."
        )

    food_id = save_food_item(
        food_data=simplified_data,
        source="food_qr_api",
        db=db
    )

    risk_result = evaluate_food_risk(
        food_data=simplified_data,
        pregnancy_week=pregnancy_week
    )

    return {
        "source": "food_qr_api",
        "food_id": food_id,
        "data": simplified_data,
        "risk": risk_result
    }


@app.get("/foods/search")
def search_food(
    query: str,
    pregnancy_week: int = 20,
    page_no: int = 1,
    num_of_rows: int = 10,
    db: sqlite3.Connection = Depends(get_db)
):
    """
    음식명 검색

    1. 식품영양성분DB API에서 음식명으로 검색
    2. 검색 결과를 앱용 데이터로 정리
    3. food_items 테이블에 저장/업데이트
    4. 임신 주차 기준 위험도 판단 결과 포함
    """

    if not query or query.strip() == "":
        raise HTTPException(
            status_code=400,
            detail="검색어를 입력해 주세요."
        )

    try:
        foods = search_food_nutrition(
            query=query,
            page_no=page_no,
            num_of_rows=num_of_rows
        )
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"음식명 검색 API 호출 실패: {str(e)}"
        )

    results = []

    for food_data in foods:
        food_id = save_food_item(
            food_data=food_data,
            source="food_nutrition_api",
            db=db
        )

        risk_result = evaluate_food_risk(
            food_data=food_data,
            pregnancy_week=pregnancy_week
        )

        results.append({
            "source": "food_nutrition_api",
            "food_id": food_id,
            "data": food_data,
            "risk": risk_result
        })

    return {
        "query": query,
        "count": len(results),
        "page_no": page_no,
        "num_of_rows": num_of_rows,
        "results": results
    }

# ── 음식 기록 ─────────────────────────────────────────

@app.post("/food-log")
def create_food_log(
    log: FoodLogCreate,
    db: sqlite3.Connection = Depends(get_db)
):
    """음식 섭취 기록 저장"""

    cursor = db.cursor()

    # 사용자 존재 확인
    cursor.execute("SELECT user_id FROM users WHERE user_id = ?", (log.user_id,))
    user = cursor.fetchone()

    if not user:
        raise HTTPException(status_code=404, detail="사용자를 찾을 수 없습니다.")

    cursor.execute("""
        INSERT INTO food_log
        (user_id, food_id, food_name, category, input_type, amount, unit,
         caffeine_mg, sugar_g, sodium_mg, calories_kcal, carbohydrate_g, protein_g)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        log.user_id,
        log.food_id,
        log.food_name,
        log.category,
        log.input_type,
        log.amount,
        log.unit,
        log.caffeine_mg,
        log.sugar_g,
        log.sodium_mg,
        log.calories_kcal,
        log.carbohydrate_g,
        log.protein_g
    ))

    db.commit()

    return {
        "log_id": cursor.lastrowid,
        "message": "음식 기록 완료"
    }


@app.post("/food-log/from-food")
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
    cursor.execute("SELECT user_id FROM users WHERE user_id = ?", (log.user_id,))
    if not cursor.fetchone():
        raise HTTPException(status_code=404, detail="사용자를 찾을 수 없습니다.")

    # 식품 존재 확인
    cursor.execute("SELECT * FROM food_items WHERE food_id = ?", (log.food_id,))
    food = cursor.fetchone()
    if not food:
        raise HTTPException(status_code=404, detail="해당 식품 정보를 찾을 수 없습니다.")

    food = dict(food)
    amount = log.amount

    def multiply(value, factor):
        if value is None:
            return None
        return round(value * factor, 4)

    caffeine_mg = multiply(food.get("caffeine_mg"), amount)
    sugar_g = multiply(food.get("sugar_g") or 0, amount)
    sodium_mg = multiply(food.get("sodium_mg") or 0, amount)
    carbohydrate_g = multiply(food.get("carbohydrate_g"), amount)
    protein_g = multiply(food.get("protein_g"), amount)

    cursor.execute("""
        INSERT INTO food_log
        (user_id, food_id, food_name, category, input_type, amount, unit,
         caffeine_mg, sugar_g, sodium_mg, carbohydrate_g, protein_g)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        log.user_id,
        log.food_id,
        food["food_name"],
        food.get("category"),
        "food_id",
        amount,
        log.unit,
        caffeine_mg,
        sugar_g,
        sodium_mg,
        carbohydrate_g,
        protein_g
    ))

    db.commit()

    return {
        "log_id": cursor.lastrowid,
        "food_name": food["food_name"],
        "amount": amount,
        "unit": log.unit,
        "nutrients": {
            "caffeine_mg": caffeine_mg,
            "sugar_g": sugar_g,
            "sodium_mg": sodium_mg,
            "carbohydrate_g": carbohydrate_g,
            "protein_g": protein_g
        },
        "message": "음식 기록 완료"
    }


@app.get("/food-log/today/{user_id}")
def get_today_food_log(
    user_id: int,
    db: sqlite3.Connection = Depends(get_db)
):
    """오늘 먹은 음식 목록 조회: Food Diary 전체 보기 화면용"""

    cleanup_expired_food_logs(db)
    cursor = db.cursor()
    today = date.today().isoformat()

    # 사용자 확인
    cursor.execute("SELECT user_id FROM users WHERE user_id = ?", (user_id,))
    user = cursor.fetchone()

    if not user:
        raise HTTPException(status_code=404, detail="사용자를 찾을 수 없습니다.")

    cursor.execute("""
        SELECT *
        FROM food_log
        WHERE user_id = ? AND DATE(eaten_at) = ?
        ORDER BY eaten_at ASC
    """, (
        user_id,
        today
    ))

    logs = cursor.fetchall()

    result = []

    for log in logs:
        log = dict(log)

        eaten_at = log.get("eaten_at") or ""
        time_text = ""

        # eaten_at 예시: "2026-05-24 15:10:00"
        if len(eaten_at) >= 16:
            time_text = eaten_at[11:16]

        caffeine = log.get("caffeine_mg")
        sugar = log.get("sugar_g") or 0
        sodium = log.get("sodium_mg") or 0

        # 카페인 상태: None이면 unknown
        if caffeine is None:
            caffeine_status = "unknown"
        else:
            caffeine_status = "safe" if caffeine <= 70 else "caution" if caffeine <= 200 else "avoid"

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
                "status": "safe" if sugar <= 10 else "caution" if sugar <= 30 else "avoid"
            },
            {
                "name": "나트륨",
                "value": sodium,
                "unit": "mg",
                "status": "safe" if sodium <= 500 else "caution" if sodium <= 1500 else "avoid"
            }
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
                    "carbohydrate_g": log.get("carbohydrate_g"),
                    "protein_g": log.get("protein_g")
                },
                "nutrition_items": nutrition_items
            }
        })

    return {
        "user_id": user_id,
        "date": today,
        "count": len(result),
        "logs": result
    }


@app.post("/food-log/{log_id}/feedback")
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
    return {"log_id": log_id, "feedback": req.feedback, "message": "피드백이 저장되었습니다."}


@app.get("/food-log/feedback/summary/{user_id}")
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


# ── 오늘 누적 섭취량 ───────────────────────────────────

@app.get("/intake/today/{user_id}")
def get_today_intake(
    user_id: int,
    db: sqlite3.Connection = Depends(get_db)
):
    """오늘 누적 섭취량 계산 + Food Diary 화면용 응답"""

    cleanup_expired_food_logs(db)
    cursor = db.cursor()
    today = date.today().isoformat()

    # 1. 사용자 확인
    cursor.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
    user = cursor.fetchone()

    if not user:
        raise HTTPException(status_code=404, detail="사용자를 찾을 수 없습니다.")

    # 2. 오늘 섭취량 합산
    cursor.execute("""
        SELECT
            COALESCE(SUM(caffeine_mg), 0) AS total_caffeine,
            COALESCE(SUM(sugar_g), 0) AS total_sugar,
            COALESCE(SUM(sodium_mg), 0) AS total_sodium,
            COALESCE(SUM(calories_kcal), 0) AS total_calories
        FROM food_log
        WHERE user_id = ? AND DATE(eaten_at) = ?
    """, (
        user_id,
        today
    ))

    intake = dict(cursor.fetchone())

    week = user["pregnancy_week"] or 20

    # 3. 임신 단계 판별
    if week <= 12:
        trimester = "early"
        trimester_label = "임신 초기"
    elif week <= 27:
        trimester = "middle"
        trimester_label = "임신 중기"
    else:
        trimester = "late"
        trimester_label = "임신 후기"

    # 4. 주차별 기준값 조회
    cursor.execute("""
        SELECT *
        FROM pregnancy_limits
        WHERE trimester = ?
    """, (trimester,))

    limit = cursor.fetchone()

    if not limit:
        raise HTTPException(
            status_code=500,
            detail="임신 주차별 기준 정보를 찾을 수 없습니다."
        )

    limit = dict(limit)

    caffeine_limit = limit["caffeine_limit_mg"]
    sugar_limit = limit["sugar_caution_g"]
    sodium_limit = limit["sodium_caution_mg"]

    total_caffeine = intake["total_caffeine"]
    total_sugar = intake["total_sugar"]
    total_sodium = intake["total_sodium"]
    total_calories = intake["total_calories"]

    # 5. 잔여 허용량 계산
    remaining_caffeine = max(0, caffeine_limit - total_caffeine)
    remaining_sugar = max(0, sugar_limit - total_sugar)
    remaining_sodium = max(0, sodium_limit - total_sodium)

    # 6. 퍼센트 계산
    def get_percent(value, standard):
        if standard <= 0:
            return 0
        return round((value / standard) * 100, 1)

    caffeine_percent = get_percent(total_caffeine, caffeine_limit)
    sugar_percent = get_percent(total_sugar, sugar_limit)
    sodium_percent = get_percent(total_sodium, sodium_limit)

    # 7. 상태 계산
    def get_status(value, standard):
        if standard <= 0:
            return "unknown"

        ratio = value / standard

        if ratio <= 0.7:
            return "safe"
        elif ratio <= 1.0:
            return "caution"
        else:
            return "avoid"

    caffeine_status = get_status(total_caffeine, caffeine_limit)
    sugar_status = get_status(total_sugar, sugar_limit)
    sodium_status = get_status(total_sodium, sodium_limit)

    statuses = [caffeine_status, sugar_status, sodium_status]

    if "avoid" in statuses:
        overall_status = "avoid"
    elif "caution" in statuses:
        overall_status = "caution"
    else:
        overall_status = "safe"

    # 8. 화면용 한글 라벨
    def status_label(status):
        if status == "safe":
            return "충분"
        elif status == "caution":
            return "주의"
        elif status == "avoid":
            return "초과"
        return "확인"

    # 9. Food Diary 하단 분석 메시지 생성
    messages = []

    if total_caffeine == 0 and total_sugar == 0 and total_sodium == 0:
        summary_title = "아직 기록된 음식이 없어요 :)"
        messages.append("Food Diary 혹은 바코드 스캔을 통해 음식을 추가해 주세요.")
    else:
        if overall_status == "safe":
            summary_title = "오늘은 아직 기준 이내예요 :)"
        elif overall_status == "caution":
            summary_title = "오늘은 섭취량을 조금 조심하세요 :)"
        else:
            summary_title = "오늘은 추가 섭취를 주의하세요!"

        if caffeine_status == "caution":
            messages.append("카페인 섭취량이 기준에 가까워지고 있어요.")
        elif caffeine_status == "avoid":
            messages.append("카페인 섭취량이 기준을 넘었어요. 오늘은 추가 섭취를 피하는 것이 좋아요.")

        if sugar_status == "safe":
            messages.append("당류는 현재 기준 이내예요.")
        elif sugar_status == "caution":
            messages.append("당류 수치가 높아지고 있어요. 달콤한 간식은 조금 조절해 주세요.")
        elif sugar_status == "avoid":
            messages.append("당류 섭취량이 기준을 넘었어요. 오늘은 단 음식 섭취를 줄여 주세요.")

        if sodium_status == "safe":
            messages.append("나트륨은 현재 기준 이내예요.")
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
        "date": today,
        "pregnancy_week": week,
        "trimester": trimester,
        "trimester_label": trimester_label,

        "intake": {
            "total_caffeine": total_caffeine,
            "total_sugar": total_sugar,
            "total_sodium": total_sodium,
            "total_calories": total_calories
        },

        "limits": {
            "caffeine_limit_mg": caffeine_limit,
            "sugar_limit_g": sugar_limit,
            "sodium_limit_mg": sodium_limit
        },

        "remaining": {
            "remaining_caffeine": remaining_caffeine,
            "remaining_sugar": remaining_sugar,
            "remaining_sodium": remaining_sodium
        },

        "progress": {
            "caffeine_percent": caffeine_percent,
            "sugar_percent": sugar_percent,
            "sodium_percent": sodium_percent
        },

        "status": {
            "overall_status": overall_status,
            "caffeine_status": caffeine_status,
            "sugar_status": sugar_status,
            "sodium_status": sodium_status
        },

        "status_label": {
            "overall": status_label(overall_status),
            "caffeine": status_label(caffeine_status),
            "sugar": status_label(sugar_status),
            "sodium": status_label(sodium_status)
        },

        "summary": {
            "title": summary_title,
            "messages": messages
        },

        "note": limit["note"]
    }


# ── ML 기반 추천 ──────────────────────────────────────────

@app.post("/recommendations")
def get_recommendations(
    req: RecommendationRequest,
    db: sqlite3.Connection = Depends(get_db)
):
    """
    ML 기반 임신 중 식품 추천

    규칙 기반 기준을 바탕으로 학습한 초기 ML 추천 모델 사용.
    모델 파일이 없을 경우 규칙 기반 안전장치로 폴백.
    공식 의학 기준 아님.
    """

    cleanup_expired_food_logs(db)
    cursor = db.cursor()

    # 1. 사용자 확인
    cursor.execute("SELECT * FROM users WHERE user_id = ?", (req.user_id,))
    user = cursor.fetchone()
    if not user:
        raise HTTPException(status_code=404, detail="사용자를 찾을 수 없습니다.")
    user = dict(user)

    week = user.get("pregnancy_week") or 20
    allergy_info = user.get("allergy_info") or ""
    allergy_list = [a.strip() for a in allergy_info.split(",") if a.strip()]

    # 2. 오늘 누적 섭취량
    today = date.today().isoformat()
    cursor.execute("""
        SELECT
            COALESCE(SUM(caffeine_mg), 0) AS total_caffeine,
            COALESCE(SUM(sugar_g), 0)    AS total_sugar,
            COALESCE(SUM(sodium_mg), 0)  AS total_sodium
        FROM food_log
        WHERE user_id = ? AND DATE(eaten_at) = ?
    """, (req.user_id, today))
    row = dict(cursor.fetchone())
    today_intake = {
        "caffeine_mg": row["total_caffeine"],
        "sugar_g":     row["total_sugar"],
        "sodium_mg":   row["total_sodium"],
    }

    # 2b. 최근 7일 일별 평균 섭취량
    cursor.execute("""
        SELECT
            DATE(eaten_at)   AS day,
            SUM(caffeine_mg) AS day_caffeine,
            SUM(sugar_g)     AS day_sugar,
            SUM(sodium_mg)   AS day_sodium
        FROM food_log
        WHERE user_id = ? AND DATE(eaten_at) >= DATE(?, '-6 days')
        GROUP BY DATE(eaten_at)
    """, (req.user_id, today))
    week_rows = cursor.fetchall()
    if week_rows:
        n = len(week_rows)
        week_pattern = {
            "avg_caffeine_mg": round(sum(r["day_caffeine"] for r in week_rows) / n, 2),
            "avg_sugar_g":     round(sum(r["day_sugar"]    for r in week_rows) / n, 2),
            "avg_sodium_mg":   round(sum(r["day_sodium"]   for r in week_rows) / n, 2),
        }
    else:
        week_pattern = {"avg_caffeine_mg": 0.0, "avg_sugar_g": 0.0, "avg_sodium_mg": 0.0}

    # 3. 후보 식품 조회 (허용 소스만 사용)
    _ALLOWED_SOURCES = ("dish_db_download", "food_qr_api")
    if req.query and req.category:
        cursor.execute(
            "SELECT * FROM food_items "
            "WHERE food_name LIKE ? AND category = ? "
            "AND data_source IN (?,?) LIMIT 50",
            (f"%{req.query}%", req.category, *_ALLOWED_SOURCES)
        )
    elif req.query:
        cursor.execute(
            "SELECT * FROM food_items "
            "WHERE food_name LIKE ? AND data_source IN (?,?) LIMIT 50",
            (f"%{req.query}%", *_ALLOWED_SOURCES)
        )
    elif req.category:
        cursor.execute(
            "SELECT * FROM food_items "
            "WHERE category = ? AND data_source IN (?,?) LIMIT 50",
            (req.category, *_ALLOWED_SOURCES)
        )
    else:
        cursor.execute(
            "SELECT * FROM food_items "
            "WHERE data_source IN (?,?) ORDER BY updated_at DESC LIMIT 50",
            _ALLOWED_SOURCES
        )
    foods = [dict(f) for f in cursor.fetchall()]

    if not foods:
        return {
            "user_id": req.user_id,
            "pregnancy_week": week,
            "trimester": "early" if week <= 12 else "middle" if week <= 27 else "late",
            "today_intake": today_intake,
            "week_pattern": week_pattern,
            "recommendations": [],
            "message": "해당 조건의 식품 데이터가 없습니다. 바코드 스캔 또는 음식 검색으로 데이터를 먼저 추가해 주세요."
        }

    # 4. 각 식품 추천 판정
    results = []
    for food in foods:
        allergen_info_str = food.get("allergen_info") or ""
        allergy_match = 1 if any(a in allergen_info_str for a in allergy_list) else 0

        result = recommend_food(
            food=food,
            pregnancy_week=week,
            today_intake=today_intake,
            allergy_match=allergy_match
        )

        results.append({
            "food_id": food["food_id"],
            "food_name": food["food_name"],
            "source": food.get("data_source"),
            "status": result["status"],
            "label": result["label"],
            "confidence": result["confidence"],
            "reason": result["reason"],
            "nutrients": {
                "caffeine_mg": food.get("caffeine_mg"),
                "sugar_g": food.get("sugar_g"),
                "sodium_mg": food.get("sodium_mg"),
                "carbohydrate_g": food.get("carbohydrate_g"),
                "protein_g": food.get("protein_g"),
            },
            "data_confidence": calculate_data_confidence(food),
        })

    # 5. 정렬: possible → caution → avoid, 같은 status 내 confidence 내림차순
    STATUS_ORDER = {"possible": 0, "caution": 1, "avoid": 2}
    results.sort(key=lambda x: (
        STATUS_ORDER.get(x["status"], 99),
        -(x["confidence"] or 0)
    ))

    trimester = "early" if week <= 12 else "middle" if week <= 27 else "late"

    # 6. 대체 식품 추천
    food_category_map = {f["food_id"]: f.get("category") for f in foods}

    possible_by_category: dict = {}
    for r in results:
        if r["status"] == "possible":
            cat = food_category_map.get(r["food_id"])
            if cat and cat not in possible_by_category:
                possible_by_category[cat] = r

    final_results = []
    for r in results[:req.limit]:
        if r["status"] in ("avoid", "caution"):
            cat = food_category_map.get(r["food_id"])
            alt = possible_by_category.get(cat) if cat else None
            if alt and alt["food_id"] != r["food_id"]:
                r["alternative"] = {
                    "food_id": alt["food_id"],
                    "food_name": alt["food_name"],
                    "reason": "비슷한 종류 중 현재 섭취 가능한 음식이에요.",
                }
            else:
                r["alternative"] = None
        else:
            r["alternative"] = None
        final_results.append(r)

    return {
        "user_id": req.user_id,
        "pregnancy_week": week,
        "trimester": trimester,
        "today_intake": today_intake,
        "week_pattern": week_pattern,
        "model_available": final_results[0]["confidence"] is not None if final_results else False,
        "recommendations": final_results
    }


# ── 프리미엄 회원 관리 ────────────────────────────────────

@app.get("/premium/status/{user_id}", response_model=PremiumStatusResponse)
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


@app.post("/premium/upgrade")
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


@app.post("/premium/cancel")
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


# ── 프리미엄 리포트 ───────────────────────────────────────

def _get_trimester_limits(cursor, pregnancy_week: int) -> tuple[str, dict]:
    """트라이메스터 판별 및 pregnancy_limits 조회"""
    if pregnancy_week <= 12:
        trimester = "early"
    elif pregnancy_week <= 27:
        trimester = "middle"
    else:
        trimester = "late"
    cursor.execute("SELECT * FROM pregnancy_limits WHERE trimester = ?", (trimester,))
    limit_row = cursor.fetchone()
    if not limit_row:
        raise HTTPException(status_code=500, detail="임신 주차별 기준 정보를 찾을 수 없습니다.")
    limits = dict(limit_row)
    return trimester, {
        "caffeine_mg": limits["caffeine_limit_mg"],
        "sugar_g":     limits["sugar_caution_g"],
        "sodium_mg":   limits["sodium_caution_mg"],
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


@app.get("/premium/report/{user_id}")
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

    week = user.get("pregnancy_week") or 20
    trimester, limits = _get_trimester_limits(cursor, week)
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