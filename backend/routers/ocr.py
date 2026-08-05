import sqlite3
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from backend.alternative_food_query import determine_trigger_nutrient, find_subcategory_alternatives
from backend.database import get_db
from backend.gemini_vision import GeminiDailyLimitExceededError, LabelNotDetectedError, call_gemini_vision
from backend.intake_totals import build_item_nutrient_statuses, get_trimester_limits, resolve_user_nutrition_context
from backend.ocr_category_classifier import classify_food
from backend.ocr_nutrition_parser import resolve_ocr_nutrients

router = APIRouter()

# TEMPORARY: no Gemini API key has been confirmed working yet, and frontend
# work on the capture/confirm/failure screens shouldn't block on that.
# Set this back to False once GEMINI_API_KEY is confirmed working.
USE_MOCK_GEMINI = True


class OcrScanRequest(BaseModel):
    image: str  # base64, no data-URI prefix
    user_id: int  # 품목 단위 상태 판정(get_trimester_limits)에 필요한 사용자 컨텍스트


@router.post("/ocr/scan")
def scan_nutrition_label(req: OcrScanRequest, db: sqlite3.Connection = Depends(get_db)):
    """
    영양성분표 이미지 OCR 인식

    1. Gemini Vision으로 이미지에서 필드 추출 (판정 없음, 추출만)
    2. 기준량/총 내용량/1회 제공량 스케일 적용
    3. 추적 대상 7개 영양소에 대해 이 품목 단위 상태(여유/안전/위험/정보없음) 판정
    4. 결과만 반환 — 저장은 하지 않음 (확정은 확인 화면 → 기존 /food-log POST)

    이미지 바이트는 이 요청 처리 동안만 메모리에 존재하며, 디스크에 쓰거나
    로그/에러 메시지에 포함하지 않는다.
    """
    cursor = db.cursor()
    cursor.execute("SELECT * FROM users WHERE user_id = ?", (req.user_id,))
    user = cursor.fetchone()
    if not user:
        raise HTTPException(status_code=404, detail="사용자를 찾을 수 없습니다.")
    user = dict(user)

    if USE_MOCK_GEMINI:
        # Mock path: skip the real Gemini Vision call entirely and build an
        # extraction dict in the exact shape call_gemini_vision() returns, so
        # resolve_ocr_nutrients() below runs unchanged.
        # --- Tweak these to test the scale-method cases ---
        # Set serving_size_g to None (with reference_amount_display_method still
        # "per_basis_with_total") to exercise the "basis known, serving size
        # unknown" needs_review path — the label has "100g당" but no separate
        # "1회 제공량" breakdown, so the confirm screen should fall back to
        # asking for grams eaten directly instead of assuming a serving size.
        mock_extraction = {
            "product_name": "목 테스트 과자",
            "nutrition_table_found": True,
            "reference_amount_display_method": "per_basis_with_total",
            "basis_amount_value": 100.0,
            "total_content_value": 355.0,
            "servings_per_container": None,
            "serving_size_g": 30.0,
            "carbohydrate_g_per_basis": 70.0,
            "sugar_g_per_basis": 12.0,
            "energy_kcal_per_basis": 450.0,
            "fat_g_per_basis": 18.0,
            "iron_mg_per_basis": 1.2,
            "protein_g_per_basis": 6.0,
            "sodium_mg_per_basis": 178.0,
        }
        # ---------------------------------------------------------------
        extraction = mock_extraction
    else:
        try:
            extraction = call_gemini_vision(req.image)
        except LabelNotDetectedError as e:
            raise HTTPException(
                status_code=422,
                detail=str(e) or "영양성분표를 인식하지 못했어요. 라벨이 잘 보이도록 다시 촬영해주세요.",
            )
        except GeminiDailyLimitExceededError:
            raise HTTPException(
                status_code=429,
                detail={
                    "error_code": "DAILY_LIMIT_REACHED",
                    "message": "오늘의 OCR 인식 횟수를 모두 사용했어요. 내일 다시 시도해주세요.",
                },
            )
        except Exception:
            import traceback
            traceback.print_exc()
            raise HTTPException(
                status_code=502,
                detail={
                    "error_code": "GEMINI_CALL_FAILED",
                    "message": "OCR 처리 중 오류가 발생했어요. 다시 시도해주세요.",
                },
            )

    resolved = resolve_ocr_nutrients(extraction)

    week, age_bracket = resolve_user_nutrition_context(user)
    _, limits = get_trimester_limits(week, age_bracket)

    serving_values = {key: data["serving_value"] for key, data in resolved["nutrients"].items()}
    # needs_review=True면 scale_factor가 없어 serving_value가 실제로는 스케일되지
    # 않은 기준량(예: 100g당) 값 그대로다 — 1회 제공량 기준인 것처럼 상태를 판정하면
    # 착시(예: 100g가 1회 제공량보다 훨씬 큰 경우 거짓 "위험")가 생길 수 있으므로,
    # 이 경우 전부 None으로 넘겨 7개 전부 "정보없음"으로 처리한다.
    status_input = serving_values if not resolved["needs_review"] else {key: None for key in serving_values}
    resolved["nutrient_statuses"] = build_item_nutrient_statuses(status_input, limits)

    return resolved


class OcrAlternativesRequest(BaseModel):
    user_id: int
    product_name: Optional[str] = None
    # 키: carbohydrate/sugar/energy/fat/iron/protein/sodium (/ocr/scan 응답의
    # nutrients.<key>.serving_value와 동일한 값을 그대로 전달하면 된다).
    nutrients: dict[str, Optional[float]]


def _empty_alternatives_response(trigger_nutrient: Optional[str] = None) -> dict:
    return {
        "available": False,
        "trigger_nutrient": trigger_nutrient,
        "category": None,
        "subcategory": None,
        "alternatives": [],
    }


@router.post("/ocr/alternatives")
def get_ocr_alternatives(req: OcrAlternativesRequest, db: sqlite3.Connection = Depends(get_db)) -> dict:
    """
    OCR 스캔 품목이 위험(avoid) 판정을 받았을 때 같은 subcategory 안에서 그 원인이
    된 특정 영양소 기준으로 정렬한 대체 후보를 찾는다.

    분류/조회 실패는 전부 동일하게 "available: false"로 수렴한다 (아래 4가지 모두):
    - avoid 상태인 영양소가 아예 없음 (Gemini 호출 없음)
    - product_name이 비어있음 (Gemini 호출 없음)
    - Gemini 분류 실패(스키마 불일치/일일 상한 초과/API 오류 등 — 절대 500/429로
      올리지 않는다. /ocr/scan과 달리 이 기능은 부가 기능이라 실패가 스캔 흐름을
      막아서는 안 된다)
    - 분류엔 성공했지만 그 subcategory에 후보가 하나도 없음(포장 과자/음료류처럼
      dish_nutrition_db가 원래 커버하지 않는 경우 — 조사에서 확인된 정상 케이스)
    """
    cursor = db.cursor()
    cursor.execute("SELECT * FROM users WHERE user_id = ?", (req.user_id,))
    user = cursor.fetchone()
    if not user:
        raise HTTPException(status_code=404, detail="사용자를 찾을 수 없습니다.")
    user = dict(user)

    week, age_bracket = resolve_user_nutrition_context(user)
    _, limits = get_trimester_limits(week, age_bracket)
    nutrient_statuses = build_item_nutrient_statuses(req.nutrients, limits)

    trigger_nutrient = determine_trigger_nutrient(nutrient_statuses)
    if trigger_nutrient is None:
        return _empty_alternatives_response()

    if not req.product_name or not req.product_name.strip():
        return _empty_alternatives_response(trigger_nutrient)

    if USE_MOCK_GEMINI:
        # Mock path: skip the real Gemini classification calls entirely, same
        # reasoning as /ocr/scan's mock block above (no confirmed-working key yet).
        # --- Tweak this to test the match / no-match paths ---
        # Set to (None, None) to exercise the "classification failed" ->
        # available=false path without needing a real product Gemini can't classify.
        category, subcategory = ("면 및 만두류", "라면")
        # ---------------------------------------------------------------
    else:
        category, subcategory = classify_food(req.product_name, db)
    if category is None or subcategory is None:
        return _empty_alternatives_response(trigger_nutrient)

    alternatives = find_subcategory_alternatives(db, subcategory, trigger_nutrient)
    if not alternatives:
        return _empty_alternatives_response(trigger_nutrient)

    return {
        "available": True,
        "trigger_nutrient": trigger_nutrient,
        "category": category,
        "subcategory": subcategory,
        "alternatives": alternatives,
    }
