import sqlite3
from typing import Optional

from fastapi import APIRouter, HTTPException, Depends

from backend.database import get_db
from backend.food_repository import save_food_item
from backend.food_search_api import search_food_nutrition
from backend.foodqr import get_food_info, simplify_food_info
from backend.models import UserFoodItemCreate
from backend.risk import evaluate_food_risk

router = APIRouter()

# TEMPORARY: foodqr.kr is currently unresponsive with the real FOOD_QR_API_KEY
# (invalid keys get an immediate 401, but the real key silently times out after
# 10s with no response — a third-party/account issue pending resolution via the
# operating agency, not a code bug). Set this back to False once foodqr.kr is
# confirmed working again.
USE_MOCK_FOODQR = True


@router.get("/foods/barcode/{barcode}")
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

    if USE_MOCK_FOODQR:
        # Mock path: skip the foodqr.kr round-trip entirely and build a
        # simplified_data dict in the exact shape simplify_food_info() returns,
        # so save_food_item()/evaluate_food_risk() below run unchanged.
        # Use the last 3 digits of the scanned barcode in food_name so different
        # barcodes are visibly distinguishable while testing.
        barcode_suffix = barcode[-3:] if len(barcode) >= 3 else barcode

        # --- Tweak these to test safe / caution / avoid outcomes ---
        # calories_kcal / sodium_mg / sugar_g / allergens feed directly into
        # evaluate_food_risk() and drive overall_status (safe/caution/avoid).
        mock_calories_kcal = 120
        mock_sodium_mg = 95
        mock_sugar_g = 8
        mock_allergens = ["우유"]
        # -------------------------------------------------------------

        simplified_data = {
            "barcode": barcode,
            "food_name": f"목 테스트 식품 {barcode_suffix}",
            "food_category": "가공식품",
            "food_type": "일반식품",
            "serving_size": "100g",
            "calories_kcal": mock_calories_kcal,
            "sodium_mg": mock_sodium_mg,
            "sugar_g": mock_sugar_g,
            "carbohydrate_g": 20,
            "protein_g": 5,
            "allergens": mock_allergens,
            "warnings": [],
        }
    else:
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


@router.get("/foods/search")
def search_food(
    query: str,
    pregnancy_week: int = 20,
    page_no: int = 1,
    num_of_rows: int = 10,
    user_id: Optional[int] = None,
    db: sqlite3.Connection = Depends(get_db)
):
    """
    음식명 검색

    1. (user_id가 주어진 경우) user_food_items에서 개인 기록 먼저 검색
    2. 식품영양성분DB API에서 음식명으로 검색
    3. 검색 결과를 앱용 데이터로 정리
    4. food_items 테이블에 저장/업데이트
    5. 임신 주차 기준 위험도 판단 결과 포함
    """

    if not query or query.strip() == "":
        raise HTTPException(
            status_code=400,
            detail="검색어를 입력해 주세요."
        )

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
                "risk": None,
            })

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

    신뢰 가능한 출처(dish_db_download, food_qr_api)의 food_items에 실제로
    존재하는 category 값만 반환한다.
    """
    cursor = db.cursor()
    cursor.execute(
        "SELECT DISTINCT category FROM food_items "
        "WHERE category IS NOT NULL AND data_source IN (?,?) "
        "ORDER BY category",
        ("dish_db_download", "food_qr_api")
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
