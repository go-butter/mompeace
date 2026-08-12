import sqlite3
from datetime import date

from fastapi import APIRouter, HTTPException, Depends

from backend.database import get_db
from backend.models import RecommendationRequest
from backend.recommendation_model import (
    NUTRIENT_TO_FOOD_KEY,
    STATUS_RANK,
    compute_nutrient_budget,
    format_exceeded_label,
    recommend_food,
)
from backend.data_confidence import calculate_data_confidence
from backend.risk import calculate_current_pregnancy_age, get_trimester
from backend.sensitivity import get_user_adj
from backend.intake_totals import (
    NUTRIENT_SUMMARY_FIELDS,
    build_panel_nutrients,
    compute_today_intake_totals,
    fetch_daily_nutrient_totals,
    get_trimester_limits,
    resolve_user_nutrition_context,
)
from backend.nutrition_constants import parse_selected_nutrients

router = APIRouter()

# 패널 8개 영양소 -> food_items 컬럼명. 판정 대상 3개는 recommendation_model의 맵을
# 그대로 펼쳐 쓴다 — 같은 키를 두 곳에 따로 적으면 언젠가 서로 어긋난다.
PANEL_NUTRIENT_TO_FOOD_KEY = {
    **NUTRIENT_TO_FOOD_KEY,
    "carbohydrate": "carbohydrate_g",
    "protein": "protein_g",
    "fat": "fat_g",
    "iron": "iron_mg",
    "energy": "calories_kcal",
}

_ALLOWED_SOURCE = "dish_db_download"
_CANDIDATE_POOL_LIMIT = 500
# 등급 순서(possible < caution < avoid)는 recommendation_model.STATUS_RANK 하나만
# 정본으로 두고 여기서는 파생시킨다 — 같은 순서를 두 곳에 적으면 언젠가 어긋난다.
_STATUS_TIERS = tuple(sorted(STATUS_RANK, key=STATUS_RANK.get))


def _build_nutrient_where(budget: dict) -> tuple[list, list]:
    """이미 초과한 영양소(remaining == 0)는 조건을 만들지 않는다 — `sugar_g <= 0`을
    걸면 후보 풀이 통째로 비는, 판정 게이트에서 고친 것과 똑같은 버그의 SQL 버전이
    된다. NULL은 `OR ... IS NULL`로 반드시 살려둔다 — 값이 없다는 것은 큰 값이라는
    뜻이 아니다. 단일 쿼리 경로와 카테고리별 분할 쿼리 경로가 이 조건절을 공유한다."""
    clauses, params = [], []
    for nutrient, column in (("sugar", "sugar_g"), ("sodium", "sodium_mg"), ("caffeine", "caffeine_mg")):
        remaining = budget["remaining"][nutrient]
        if remaining > 0:
            clauses.append(f"({column} <= ? OR {column} IS NULL)")
            params.append(remaining)
    return clauses, params


def _fetch_candidates(
    cursor: sqlite3.Cursor,
    categories: list,
    query,
    budget: dict,
    pool_limit: int,
) -> list:
    """후보 식품 조회. 조건절과 파라미터를 항상 같은 문장에서 함께 append한다 —
    두 리스트를 따로 쌓으면 IN 절처럼 플레이스홀더 개수가 가변인 경우에 개수가
    어긋나기 쉽고, 이 저장소에서 실제로 겪은 문제다.

    카테고리 2개 이상(다중 선택)은 하나의 쿼리로 합쳐 RANDOM() LIMIT을 공유하지
    않는다. 필터링된 풀 안에서 한 카테고리가 차지하는 비율이 그대로 pool_limit행
    샘플에 반영되면(예: 빵+밥류 조합에서 빵이 필터링된 풀의 95.3%), 작은
    카테고리는 라운드로빈이 배분을 시작하기도 전에 후보 풀 단계에서 밀려날 수
    있다. 카테고리마다 독립된 쿼리로 뽑아 합치면 이 위험이 구조적으로 사라진다
    (각 카테고리가 자기 몫의 LIMIT을 항상 확보한다).

    카테고리 0개(전체) 또는 1개는 나눌 대상이 없으므로 기존처럼 단일 쿼리를 쓴다
    — `category IN (...)`은 다중 카테고리에서 더 이상 쓰이지 않으므로(그 경로는
    항상 카테고리별 분할 쿼리를 탄다), 동등한 `category = ?`로 단순화한다.
    """
    nutrient_clauses, nutrient_params = _build_nutrient_where(budget)

    if len(categories) >= 2:
        per_category_limit = pool_limit // len(categories)
        foods = []
        for category in categories:
            where = ["data_source = ?", "category = ?"]
            params = [_ALLOWED_SOURCE, category]
            if query:
                where.append("food_name LIKE ?")
                params.append(f"%{query}%")
            where.extend(nutrient_clauses)
            params.extend(nutrient_params)
            params.append(per_category_limit)
            cursor.execute(
                f"SELECT * FROM food_items WHERE {' AND '.join(where)} "
                f"ORDER BY RANDOM() LIMIT ?",
                params,
            )
            foods.extend(dict(f) for f in cursor.fetchall())
        return foods

    where = ["data_source = ?"]
    params = [_ALLOWED_SOURCE]
    if query:
        where.append("food_name LIKE ?")
        params.append(f"%{query}%")
    if categories:
        where.append("category = ?")
        params.append(categories[0])
    where.extend(nutrient_clauses)
    params.extend(nutrient_params)
    params.append(pool_limit)
    cursor.execute(
        f"SELECT * FROM food_items WHERE {' AND '.join(where)} "
        f"ORDER BY RANDOM() LIMIT ?",
        params,
    )
    return [dict(f) for f in cursor.fetchall()]


def _balance_by_category(results: list, categories: list, limit: int) -> list:
    """카테고리 다중 선택 시 결과를 카테고리별로 라운드로빈으로 채운다.

    results는 이미 (status, burden, confidence) 순으로 정렬되어 있다. 등급(tier)이
    바깥 루프이고 카테고리 라운드로빈이 안쪽 루프다 — 그래서 이 함수가 avoid
    항목을 possible 항목보다, 또는 caution을 possible보다 앞에 놓는 일은 구조적으로
    불가능하다(등급 경계를 절대 넘지 않는다). 카테고리 하나의 큐가 먼저 바닥나면
    그 카테고리는 로테이션에서 빠지고 나머지가 계속 채운다 — 쿼터를 못 채웠다고
    응답 전체를 짧게 반환하지 않는다. 선택한 카테고리를 다 합쳐도 limit보다 적은
    후보만 있을 때만(기존과 동일하게) 응답이 limit보다 짧아진다.

    각 카테고리 큐 안의 상대 순서는 원래 정렬(부담/신뢰도)을 그대로 유지한다 —
    이 함수는 카테고리 간 배분 순서만 바꾸고, 카테고리 안의 순서는 건드리지 않는다.
    """
    selected = []
    for tier in _STATUS_TIERS:
        if len(selected) >= limit:
            break
        queues = {category: [] for category in categories}
        for r in results:
            if r["status"] == tier and r.get("category") in queues:
                queues[r["category"]].append(r)
        while len(selected) < limit and any(queues[c] for c in categories):
            for category in categories:
                if len(selected) >= limit:
                    break
                if queues[category]:
                    selected.append(queues[category].pop(0))
    return selected


@router.post("/recommendations")
def get_recommendations(
    req: RecommendationRequest,
    db: sqlite3.Connection = Depends(get_db)
):
    """
    규칙 엔진 기반 임신 중 식품 추천

    판정(possible/caution/avoid)에 실제로 들어가는 것은 오늘 누적 섭취량, 사용자
    민감도로 스케일한 절대 기준(DAILY_LIMITS — 임신 시기와 무관하게 항상 동일),
    그리고 카페인 값을 믿을 수 있는지 여부(_is_caffeine_missing + caffeine_relevance
    티어)뿐이다 — recommend_food() 참고.

    아래에서 계산하는 임신 주차별 기준(panel_limits)과 data_confidence는 판정에
    쓰이지 않는다: 전자는 상단 패널 표시용이고, 후자는 응답 필드이자 같은 status
    안에서의 정렬 기준이다.

    현재 경로는 ML 모델을 사용하지 않으며, 알고리즘은 변경하지 않는다.
    """

    cursor = db.cursor()

    # category 필드는 검증기(mode="after")가 있어도 미지정 시 pydantic이 기본값
    # None을 그대로 통과시킨다(값이 실제로 들어올 때만 검증기가 돈다) — 그래서
    # req.category는 None일 수 있다. 이후 모든 카테고리 로직은 이 정규화된
    # categories(항상 list)만 쓴다.
    categories = req.category or []

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

    # 2c. 화면 상단 패널: 카페인 + 사용자가 고른 영양소.
    # compute_today_intake_totals(카페인/당류/나트륨 3개)는 그대로 둔다 — today_intake
    # 응답 필드와 판정 예산이 그걸 쓰고 있고, routers/food_log.py도 같은 함수를 쓴다.
    # 패널은 8개 영양소가 필요하므로 /intake/summary가 쓰는 것과 같은 쌍
    # (fetch_daily_nutrient_totals + get_trimester_limits)을 추가로 호출한다.
    panel_week, age_bracket = resolve_user_nutrition_context(user)
    _, panel_limits = get_trimester_limits(panel_week, age_bracket)
    daily_totals = fetch_daily_nutrient_totals(req.user_id, today, db)
    panel_nutrients = build_panel_nutrients(
        parse_selected_nutrients(user.get("selected_nutrients")), daily_totals, panel_limits
    )

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

    # 3. 후보 식품 조회 (허용 소스만 사용). 쿼리 구성/카테고리별 분할 규칙은
    # _fetch_candidates 주석 참고 — 명백히 탈락할 행은 랜덤 샘플링 *전에* 걸러낸다.
    foods = _fetch_candidates(cursor, categories, req.query, budget, _CANDIDATE_POOL_LIMIT)

    if not foods:
        return {
            "user_id": req.user_id,
            "pregnancy_week": week,
            "trimester": get_trimester(week),
            "today_intake": today_intake,
            "week_pattern": week_pattern,
            "exceeded_nutrients": exceeded_nutrients,
            "exceeded_label": format_exceeded_label(exceeded_nutrients),
            "panel_nutrients": panel_nutrients,
            "recommendations": [],
            "message": "해당 조건의 식품 데이터가 없습니다. 영양성분표 스캔이나 음식 검색으로 데이터를 먼저 추가해 주세요."
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
            # 패널 8개 영양소를 전부 노출한다 — 칩으로 고를 수 있는 영양소는 화면에서도
            # 값을 보여줄 수 있어야 하고, 정렬도 이 딕셔너리를 읽는다.
            "nutrients": {
                "caffeine_mg": food.get("caffeine_mg"),
                "sugar_g": food.get("sugar_g"),
                "sodium_mg": food.get("sodium_mg"),
                "carbohydrate_g": food.get("carbohydrate_g"),
                "protein_g": food.get("protein_g"),
                "fat_g": food.get("fat_g"),
                "iron_mg": food.get("iron_mg"),
                "calories_kcal": food.get("calories_kcal"),
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
    #
    # 영양소 칩(sort_nutrient)이 오면 방향에 따라 정렬 방향이 달라진다. 방향은 새로
    # 정하지 않고 NUTRIENT_SUMMARY_FIELDS의 type을 읽는다:
    #   ceiling(카페인/당류/나트륨) → 오름차순. 남은 허용량에 부담이 적은 것부터.
    #   floor(탄수화물/단백질/에너지) → 내림차순. 아직 채워야 하는 것이므로 많은 것부터.
    #   band(지방/철분) → 재정렬하지 않는다. 의도적인 선택이다: 경계가 둘이라 한 방향으로
    #     줄을 세우면 반드시 다른 쪽 경계를 무시하게 된다. 더 나은 답은 "상한을 넘기는
    #     행은 뒤로 보내고 나머지는 하한 기준 내림차순"이지만, 그건 이 저장소에서 유일하게
    #     두 경계로 정렬하는 규칙이 되므로 다시 다룰 때 도입한다.
    # 칩이 있으면 자동 초과 정렬보다 우선한다 — 사용자가 명시적으로 고른 기준이기 때문.
    sort_key = None
    sort_descending = False
    if req.sort_nutrient:
        chip_type = NUTRIENT_SUMMARY_FIELDS[req.sort_nutrient]["type"]
        if chip_type != "band":
            sort_key = PANEL_NUTRIENT_TO_FOOD_KEY[req.sort_nutrient]
            sort_descending = chip_type == "floor"
    elif exceeded_nutrients:
        sort_key = NUTRIENT_TO_FOOD_KEY[exceeded_nutrients[0]]

    def _burden(item):
        """(NULL 여부, 값) — NULL은 방향과 무관하게 항상 맨 뒤로. 0으로 간주하면 정보가
        없는 음식이 '가장 부담 없는 선택지'로 올라오고, 큰 값으로 간주하면 목록에서
        사라진다. 어느 쪽도 사실이 아니다: 값이 없다는 것은 값이 없다는 뜻이다.
        NULL을 걸러내지 않으므로, 65~78%가 NULL인 컬럼(탄수화물/지방/철분)으로 정렬해도
        목록 자체는 그대로 다 나온다 — 값이 있는 행이 앞에 오고 나머지가 뒤에 붙을 뿐이다."""
        if sort_key is None:
            return (0, 0.0)
        value = item["nutrients"].get(sort_key)
        if value is None:
            return (1, 0.0)
        return (0, -value if sort_descending else value)

    results.sort(key=lambda x: (
        STATUS_RANK.get(x["status"], 99),
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

    # 카테고리 다중 선택(2개 이상)일 때만 라운드로빈으로 배분한다 — 하나면 나눌
    # 대상이 없다. possible_by_category는 위에서 이미 전체 results로 계산했으므로
    # 아래의 카테고리 배분과 무관하게 그대로 유효하다.
    top_results = (
        _balance_by_category(results, categories, req.limit)
        if len(categories) >= 2 else results[:req.limit]
    )

    final_results = []
    for r in top_results:
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
        # 카페인 + 사용자가 고른 영양소. 각 항목이 자기 방향(ceiling/floor/band)을 들고
        # 다니므로 화면은 어떤 영양소가 어떤 종류인지 알 필요가 없다.
        "panel_nutrients": panel_nutrients,
        "recommendations": final_results
    }
