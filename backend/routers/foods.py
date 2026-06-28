import sqlite3

from fastapi import APIRouter, HTTPException, Depends

from backend.database import get_db
from backend.food_repository import save_food_item
from backend.food_search_api import search_food_nutrition
from backend.foodqr import get_food_info, simplify_food_info
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
