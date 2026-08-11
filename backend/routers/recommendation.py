import sqlite3
from datetime import date

from fastapi import APIRouter, HTTPException, Depends

from backend.database import get_db
from backend.models import RecommendationRequest
from backend.recommendation_model import (
    NUTRIENT_TO_FOOD_KEY,
    compute_nutrient_budget,
    format_exceeded_label,
    recommend_food,
)
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

    # 후보 조회 조건과 판정이 같은 "남은 허용량"을 보도록 한 번만 계산해서 공유한다.
    budget = compute_nutrient_budget(today_intake, user_adj)
    exceeded_nutrients = budget["exceeded"]

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
    #
    # 조건절과 파라미터를 항상 같은 문장에서 함께 append한다. 두 리스트를 따로 쌓으면
    # IN 절처럼 플레이스홀더 개수가 가변인 경우에 개수가 어긋나기 쉽고, 이 저장소에서
    # 실제로 겪은 문제다.
    _ALLOWED_SOURCE = "dish_db_download"
    _CANDIDATE_POOL_LIMIT = 500

    where = ["data_source = ?"]
    params = [_ALLOWED_SOURCE]

    if req.query:
        where.append("food_name LIKE ?")
        params.append(f"%{req.query}%")

    # 선택한 카테고리들은 OR로 묶인다(IN = category = A OR category = B).
    # 빈 리스트면 절을 아예 추가하지 않으므로 "전체 카테고리"가 된다.
    if req.category:
        where.append(f"category IN ({','.join('?' * len(req.category))})")
        params.extend(req.category)

    # 명백히 탈락할 행은 랜덤 샘플링 *전에* 걸러낸다. 그렇지 않으면 19,495행 중 뽑은
    # 500행 안에 살아남을 후보가 몇 개나 들어오는지가 매번 운에 좌우된다.
    #
    # - 이미 초과한 영양소(remaining == 0)는 조건을 만들지 않는다. `sugar_g <= 0`을
    #   걸면 후보 풀이 통째로 비는데, 이는 판정 게이트에서 고친 것과 똑같은 버그다.
    # - NULL은 반드시 살아남아야 한다(`OR col IS NULL`). 값이 없다는 것은 큰 값이라는
    #   뜻이 아니다 — 실제로 이 테이블의 카페인 81.8%가 NULL이라, 이 가드가 없으면
    #   카페인 조건 하나로 후보의 대부분이 사라진다. 통과한 NULL 행은 판정 단계에서
    #   caution으로 올라간다.
    for nutrient, column in (("sugar", "sugar_g"), ("sodium", "sodium_mg"), ("caffeine", "caffeine_mg")):
        remaining = budget["remaining"][nutrient]
        if remaining > 0:
            where.append(f"({column} <= ? OR {column} IS NULL)")
            params.append(remaining)

    params.append(_CANDIDATE_POOL_LIMIT)
    cursor.execute(
        f"SELECT * FROM food_items WHERE {' AND '.join(where)} "
        f"ORDER BY RANDOM() LIMIT ?",
        params,
    )
    foods = [dict(f) for f in cursor.fetchall()]

    if not foods:
        return {
            "user_id": req.user_id,
            "pregnancy_week": week,
            "trimester": get_trimester(week),
            "today_intake": today_intake,
            "week_pattern": week_pattern,
            "exceeded_nutrients": exceeded_nutrients,
            "exceeded_label": format_exceeded_label(exceeded_nutrients),
            "recommendations": [],
            "message": "해당 조건의 식품 데이터가 없습니다. 바코드 스캔 또는 음식 검색으로 데이터를 먼저 추가해 주세요."
        }

    # 4. 각 식품 추천 판정
    results = []
    for food in foods:
        result = recommend_food(
            food=food,
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

    # 5. 정렬: possible → caution → avoid, 같은 status 내 data_confidence.score 내림차순.
    #
    # 이미 초과한 영양소가 있으면 그 영양소 오름차순이 status 다음 순위로 들어간다 —
    # 초과분을 되돌릴 수는 없어도, 부담이 가장 작은 선택지를 먼저 보여줄 수는 있다.
    # 초과 영양소가 여러 개면 EXCEEDED_PRIORITY(카페인·나트륨·당류) 첫 번째를 쓴다.
    # 이 순서는 alternative_food_query.determine_trigger_nutrient()(당류 우선)와 다른데,
    # 의도된 차이다: 저쪽은 "무엇을 대신 먹을까"를, 이쪽은 "목록을 어떤 순서로 보여줄까"를
    # 답한다. 표시 순서 문제라 헤드라인 순서(HEADLINE_TIEBREAK_ORDER)를 따른다.
    STATUS_ORDER = {"possible": 0, "caution": 1, "avoid": 2}
    sort_nutrient = exceeded_nutrients[0] if exceeded_nutrients else None
    sort_key = NUTRIENT_TO_FOOD_KEY[sort_nutrient] if sort_nutrient else None

    def _burden(item):
        """(NULL 여부, 값) — NULL은 항상 맨 뒤로. 0으로 간주하면 정보가 없는 음식이
        '가장 부담 없는 선택지'로 올라온다."""
        if sort_key is None:
            return (0, 0.0)
        value = item["nutrients"].get(sort_key)
        return (1, 0.0) if value is None else (0, value)

    results.sort(key=lambda x: (
        STATUS_ORDER.get(x["status"], 99),
        _burden(x),
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
        # 하루 단위 사실이라 응답 루트에 둔다. 음식마다 붙는 reason/reason_nutrient은
        # 기존 계약 그대로이며 여기 문구가 섞이지 않는다.
        "exceeded_nutrients": exceeded_nutrients,
        "exceeded_label": format_exceeded_label(exceeded_nutrients),
        "recommendations": final_results
    }
