import sqlite3
from typing import Optional

from fastapi import APIRouter, HTTPException, Depends

from backend.database import get_db
from backend.models import UserFoodItemCreate
from backend.risk import calculate_current_pregnancy_age

router = APIRouter()


def _resolve_pregnancy_week(user_id: Optional[int], db: sqlite3.Connection) -> int:
    """user_id로 사용자를 조회해 pregnancy_entered_at 기준 현재 임신 주차를 계산한다.
    user_id가 없으면 기본값 20을 반환한다."""
    if user_id is None:
        return 20

    cursor = db.cursor()
    cursor.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
    user = cursor.fetchone()
    if not user:
        raise HTTPException(status_code=404, detail="사용자를 찾을 수 없습니다.")

    user = dict(user)
    computed_age = calculate_current_pregnancy_age(
        user.get("pregnancy_week"), user.get("pregnancy_day"), user.get("pregnancy_entered_at")
    )
    return computed_age["week"] or 20


@router.get("/foods/search")
def search_food(
    query: str,
    page_no: int = 1,
    num_of_rows: int = 10,
    user_id: Optional[int] = None,
    db: sqlite3.Connection = Depends(get_db)
):
    """
    음식명 검색

    1. (user_id가 주어진 경우) user_food_items에서 개인 기록 먼저 검색
    2. food_items 테이블의 dish_db_download 카탈로그에서 음식명으로 검색
    """

    if not query or query.strip() == "":
        raise HTTPException(
            status_code=400,
            detail="검색어를 입력해 주세요."
        )

    # 결과에 위험도 판정을 싣던 시절의 주차 계산은 제거됐지만, 알 수 없는 user_id에
    # 404를 반환하는 검증 동작은 유지한다.
    _resolve_pregnancy_week(user_id, db)

    personal_results = []
    if user_id is not None:
        cursor = db.cursor()
        cursor.execute(
            "SELECT * FROM user_food_items WHERE user_id = ? AND food_name LIKE ?",
            (user_id, f"%{query}%"),
        )
        for row in cursor.fetchall():
            row = dict(row)
            personal_results.append({
                "source": "personal",
                "food_id": row["user_food_item_id"],
                "data": row,
            })

    _ALLOWED_SOURCE = "dish_db_download"
    _SEARCH_LIMIT = min(num_of_rows, 50)
    cursor = db.cursor()
    cursor.execute(
        "SELECT * FROM food_items WHERE food_name LIKE ? AND data_source = ? "
        "ORDER BY food_name LIMIT ?",
        (f"%{query}%", _ALLOWED_SOURCE, _SEARCH_LIMIT)
    )

    results = []

    for row in cursor.fetchall():
        row = dict(row)
        food_data = {
            "food_id": row["food_id"],
            "food_code": row.get("food_code"),
            "food_name": row["food_name"],
            "category": row.get("category"),
            "subcategory": row.get("subcategory"),
            "serving_label": row.get("serving_label"),
            "caffeine_mg": row.get("caffeine_mg"),
            "sugar_g": row.get("sugar_g"),
            "sodium_mg": row.get("sodium_mg"),
            "carbohydrate_g": row.get("carbohydrate_g"),
            "protein_g": row.get("protein_g"),
            "fat_g": row.get("fat_g"),
            "calories_kcal": row.get("calories_kcal"),
        }

        results.append({
            "source": "dish_db_download",
            "food_id": row["food_id"],
            "data": food_data,
        })

    results = personal_results + results

    return {
        "query": query,
        "count": len(results),
        "page_no": page_no,
        "num_of_rows": num_of_rows,
        "results": results
    }


@router.get("/categories")
def get_food_categories(db: sqlite3.Connection = Depends(get_db)):
    """
    추천 후보로 사용 가능한 식품의 카테고리 목록 (오늘의 추천 화면 필터용)

    신뢰 가능한 출처(dish_db_download)의 food_items에 실제로
    존재하는 category 값만 반환한다.
    """
    cursor = db.cursor()
    cursor.execute(
        "SELECT DISTINCT category FROM food_items "
        "WHERE category IS NOT NULL AND data_source = ? "
        "ORDER BY category",
        ("dish_db_download",)
    )
    categories = [row["category"] for row in cursor.fetchall()]
    return {"categories": categories}


@router.post("/foods/personal")
def create_personal_food_item(
    item: UserFoodItemCreate,
    db: sqlite3.Connection = Depends(get_db)
):
    """
    개인 음식 정보 저장 (직접 입력/검색 화면에서 사용)

    동일 사용자가 같은 food_name으로 이미 저장한 적이 있으면 중복 생성하지 않고
    기존 항목을 그대로 반환한다.
    """
    cursor = db.cursor()

    cursor.execute("SELECT * FROM users WHERE user_id = ?", (item.user_id,))
    if not cursor.fetchone():
        raise HTTPException(status_code=404, detail="사용자를 찾을 수 없습니다.")

    cursor.execute(
        "SELECT user_food_item_id FROM user_food_items WHERE user_id = ? AND food_name = ?",
        (item.user_id, item.food_name),
    )
    existing = cursor.fetchone()
    if existing:
        return {
            "user_food_item_id": existing["user_food_item_id"],
            "message": "이미 저장된 음식 정보입니다."
        }

    cursor.execute("""
        INSERT INTO user_food_items
        (user_id, food_name, caffeine_mg, sugar_g, sodium_mg, calories_kcal, carbohydrate_g, protein_g)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        item.user_id,
        item.food_name,
        item.caffeine_mg,
        item.sugar_g,
        item.sodium_mg,
        item.calories_kcal,
        item.carbohydrate_g,
        item.protein_g,
    ))
    db.commit()

    return {
        "user_food_item_id": cursor.lastrowid,
        "message": "음식 정보 저장 완료"
    }
