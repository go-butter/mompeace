import sqlite3
from datetime import date

from fastapi import APIRouter, HTTPException, Depends

from backend.database import get_db
from backend.models import RecommendationRequest
from backend.recommendation_model import recommend_food
from backend.data_confidence import calculate_data_confidence
from backend.risk import calculate_current_pregnancy_age, get_trimester
from backend.sensitivity import get_user_adj
from backend.intake_totals import compute_today_intake_totals

router = APIRouter()


@router.post("/recommendations")
def get_recommendations(
    req: RecommendationRequest,
    db: sqlite3.Connection = Depends(get_db)
):
    """
    규칙 엔진 기반 임신 중 식품 추천

    오늘 누적 섭취량, 임신 주차별 섭취 기준,
    카페인 정보 신뢰도 등을 함께 고려해 possible/caution/avoid를 판정한다.
    현재 경로는 ML 모델을 사용하지 않으며, 알고리즘은 변경하지 않는다.
    """

    cursor = db.cursor()

    # 1. 사용자 확인
    cursor.execute("SELECT * FROM users WHERE user_id = ?", (req.user_id,))
    user = cursor.fetchone()
    if not user:
        raise HTTPException(status_code=404, detail="사용자를 찾을 수 없습니다.")
    user = dict(user)

    computed_age = calculate_current_pregnancy_age(
        user.get("pregnancy_week"), user.get("pregnancy_day"), user.get("pregnancy_entered_at")
    )
    week = computed_age["week"] or 20
    user_adj = get_user_adj(user)

    # 2. 오늘 누적 섭취량
    today = date.today().isoformat()
    today_intake = compute_today_intake_totals(req.user_id, db)

    # 2b. 최근 7일 일별 평균 섭취량
    cursor.execute("""
        SELECT
            DATE(eaten_at)   AS day,
            COALESCE(SUM(caffeine_mg), 0) AS day_caffeine,
            SUM(CASE WHEN caffeine_mg IS NULL THEN 1 ELSE 0 END) AS day_unknown_caffeine,
            COALESCE(SUM(sugar_g), 0)     AS day_sugar,
            SUM(CASE WHEN sugar_g IS NULL THEN 1 ELSE 0 END) AS day_unknown_sugar,
            COALESCE(SUM(sodium_mg), 0)   AS day_sodium,
            SUM(CASE WHEN sodium_mg IS NULL THEN 1 ELSE 0 END) AS day_unknown_sodium
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
            "unknown_caffeine_days": sum(r["day_unknown_caffeine"] for r in week_rows),
            "unknown_sugar_days":    sum(r["day_unknown_sugar"]    for r in week_rows),
            "unknown_sodium_days":   sum(r["day_unknown_sodium"]   for r in week_rows),
        }
    else:
        week_pattern = {
            "avg_caffeine_mg": 0.0, "avg_sugar_g": 0.0, "avg_sodium_mg": 0.0,
            "unknown_caffeine_days": 0, "unknown_sugar_days": 0, "unknown_sodium_days": 0,
        }

    # 3. 후보 식품 조회 (허용 소스만 사용)
    _ALLOWED_SOURCE = "dish_db_download"
    _CANDIDATE_POOL_LIMIT = 500
    if req.query and req.category:
        cursor.execute(
            "SELECT * FROM food_items "
            "WHERE food_name LIKE ? AND category = ? "
            "AND data_source = ? ORDER BY RANDOM() LIMIT ?",
            (f"%{req.query}%", req.category, _ALLOWED_SOURCE, _CANDIDATE_POOL_LIMIT)
        )
    elif req.query:
        cursor.execute(
            "SELECT * FROM food_items "
            "WHERE food_name LIKE ? AND data_source = ? ORDER BY RANDOM() LIMIT ?",
            (f"%{req.query}%", _ALLOWED_SOURCE, _CANDIDATE_POOL_LIMIT)
        )
    elif req.category:
        cursor.execute(
            "SELECT * FROM food_items "
            "WHERE category = ? AND data_source = ? ORDER BY RANDOM() LIMIT ?",
            (req.category, _ALLOWED_SOURCE, _CANDIDATE_POOL_LIMIT)
        )
    else:
        cursor.execute(
            "SELECT * FROM food_items "
            "WHERE data_source = ? ORDER BY RANDOM() LIMIT ?",
            (_ALLOWED_SOURCE, _CANDIDATE_POOL_LIMIT)
        )
    foods = [dict(f) for f in cursor.fetchall()]

    if not foods:
        return {
            "user_id": req.user_id,
            "pregnancy_week": week,
            "trimester": get_trimester(week),
            "today_intake": today_intake,
            "week_pattern": week_pattern,
            "recommendations": [],
            "message": "해당 조건의 식품 데이터가 없습니다. 바코드 스캔 또는 음식 검색으로 데이터를 먼저 추가해 주세요."
        }

    # 4. 각 식품 추천 판정
    results = []
    for food in foods:
        result = recommend_food(
            food=food,
            pregnancy_week=week,
            today_intake=today_intake,
            user_adj=user_adj,
        )

        results.append({
            "food_id": food["food_id"],
            "food_name": food["food_name"],
            "source": food.get("data_source"),
            "category": food.get("category"),
            "status": result["status"],
            "label": result["label"],
            "reason": result["reason"],
            "reason_nutrient": result["reason_nutrient"],
            "nutrients": {
                "caffeine_mg": food.get("caffeine_mg"),
                "sugar_g": food.get("sugar_g"),
                "sodium_mg": food.get("sodium_mg"),
                "carbohydrate_g": food.get("carbohydrate_g"),
                "protein_g": food.get("protein_g"),
            },
            "data_confidence": calculate_data_confidence(food),
        })

    # 5. 정렬: possible → caution → avoid, 같은 status 내 data_confidence.score 내림차순
    STATUS_ORDER = {"possible": 0, "caution": 1, "avoid": 2}
    results.sort(key=lambda x: (
        STATUS_ORDER.get(x["status"], 99),
        -(x["data_confidence"]["score"] or 0)
    ))

    trimester = get_trimester(week)

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
        "recommendations": final_results
    }
