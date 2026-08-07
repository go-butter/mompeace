import os
import sqlite3
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from backend.alternative_food_query import determine_trigger_nutrient, find_subcategory_alternatives
from backend.database import get_db
from backend.gemini_vision import (
    GeminiDailyLimitExceededError,
    GeminiNotConfiguredError,
    LabelNotDetectedError,
    call_gemini_vision,
)
from backend.intake_totals import build_item_nutrient_statuses, get_trimester_limits, resolve_user_nutrition_context
from backend.ocr_category_classifier import classify_food
from backend.ocr_nutrition_parser import resolve_ocr_nutrients
from backend.ocr_view import build_ocr_status_view

router = APIRouter()

# 실제 Gemini 호출을 건너뛰고 고정된 목 데이터를 쓸지 여부. 기본값은 False(실제 호출)이며,
# 오프라인으로 화면을 만지거나 테스트를 돌릴 때만 OCR_USE_MOCK_GEMINI=true로 켠다.
# 소스 상수가 아니라 환경변수인 이유: 상수였을 때 "실제 키가 확인되면 되돌리기"가
# 코드 수정에 묶여 있어, 켜둔 채로 잊히면 모든 스캔이 조용히 같은 과자 하나를
# 돌려준다 — 그 상태가 실제로 한동안 지속됐다.
USE_MOCK_GEMINI = os.getenv("OCR_USE_MOCK_GEMINI", "false").lower() == "true"


def _mock_extraction() -> dict:
    """call_gemini_vision()이 돌려주는 것과 정확히 같은 모양의 고정 추출 결과.

    resolve_ocr_nutrients() 이후 경로를 실제 호출과 동일하게 통과시키기 위한 것이라,
    필드를 빼거나 더하지 않는다.

    --- 스케일 방식별 케이스를 시험할 때 여기를 바꾼다 ---
    serving_size_value를 None으로 두면(reference_amount_display_method는 계속
    "per_basis_with_total") "기준량은 알지만 1회 제공량은 모름" needs_review 경로를
    탈 수 있다 — 라벨에 "100g당"만 있고 "1회 제공량" 표기가 따로 없는 경우라,
    확인 화면은 인분수를 가정하지 말고 섭취 그램을 직접 받아야 한다.
    """
    return {
        "product_name": "목 테스트 과자",
        "nutrition_table_found": True,
        "reference_amount_display_method": "per_basis_with_total",
        "basis_amount_value": 100.0,
        "basis_amount_unit": "g",
        "total_content_value": 355.0,
        "total_content_unit": "g",
        "servings_per_container": None,
        "serving_size_value": 30.0,
        "serving_size_unit": "g",
        "carbohydrate_g_per_basis": 70.0,
        "sugar_g_per_basis": 12.0,
        "energy_kcal_per_basis": 450.0,
        "fat_g_per_basis": 18.0,
        "iron_mg_per_basis": 1.2,
        "protein_g_per_basis": 6.0,
        "sodium_mg_per_basis": 178.0,
    }


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
        extraction = _mock_extraction()
    else:
        try:
            extraction = call_gemini_vision(req.image)
        except LabelNotDetectedError as e:
            raise HTTPException(
                status_code=422,
                detail=str(e) or "영양성분표를 인식하지 못했어요. 라벨이 잘 보이도록 다시 촬영해주세요.",
            )
        except GeminiNotConfiguredError:
            # 502(호출 실패)와 구분한다 — 서버 설정 문제라 다시 촬영해도 해결되지
            # 않으므로, 화면이 "다시 촬영" 대신 다른 안내를 보여줄 수 있어야 한다.
            raise HTTPException(
                status_code=503,
                detail={
                    "error_code": "OCR_UNAVAILABLE",
                    "message": "OCR 기능을 지금 사용할 수 없어요. 검색이나 직접 입력으로 등록해주세요.",
                },
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

    serving_values = {key: data["serving_value"] for key, data in resolved["nutrients"].items()}
    # needs_review=True면 scale_factor가 없어 serving_value가 실제로는 스케일되지
    # 않은 기준량(예: 100g당) 값 그대로다 — 1회 제공량 기준인 것처럼 상태를 판정하면
    # 착시(예: 100g가 1회 제공량보다 훨씬 큰 경우 거짓 "위험")가 생길 수 있으므로,
    # 이 경우 전부 None으로 넘겨 전부 "정보없음"으로 처리한다.
    pending_values = serving_values if not resolved["needs_review"] else {key: None for key in serving_values}
    # 카페인은 한국 영양성분표에 인쇄되지 않아 OCR이 절대 추출할 수 없다. 그래도
    # 오늘 이미 마신 카페인이 있으면 그 누적 상태는 보여야 하므로, None으로 넣어
    # 일일 투영에 포함시킨다 (빼면 앱에서 가장 엄격한 기준이 화면에서 사라진다).
    pending_values["caffeine"] = None

    # /ocr/recompute와 동일한 뷰 모델 조립기를 쓴다 — 스캔 직후와 편집 직후가
    # 다른 규칙으로 판정되지 않도록 두 엔드포인트가 같은 함수를 공유한다.
    view = build_ocr_status_view(pending_values, user, db)
    resolved["nutrient_statuses"] = view["nutrient_statuses"]
    resolved["headline"] = view["headline"]

    return resolved


class OcrRecomputeNutrientInput(BaseModel):
    """확인 화면에 현재 떠 있는 영양소 한 칸의 상태.

    value: 비어 있으면 None (정보 없음 ≠ 0). 0은 "확정된 0"이라는 뜻이다.
    source: 이 값이 OCR 추출에서 온 것인지 사용자가 직접 입력한 것인지.
      판정에는 전혀 쓰이지 않는다 — 나중에 원본 라벨 스냅샷을 저장할 때 둘을
      구분할 수 있도록 지금부터 요청 형식에 포함해 둘 뿐이다(스냅샷 테이블 자체는
      이번 범위 밖이라 저장하지도, 응답에 되돌려주지도 않는다).
    """
    value: Optional[float] = None
    source: Literal["ocr", "manual"] = "manual"


class OcrRecomputeRequest(BaseModel):
    user_id: int
    # 키: carbohydrate/sugar/energy/fat/iron/protein/sodium/caffeine.
    # 화면에 보이는 8칸 전부를 보낸다 — 사용자가 직접 입력한 철분/카페인도 판정
    # 대상이고, 비워둔 칸은 None으로 보내야 unknown으로 남는다.
    nutrients: dict[str, OcrRecomputeNutrientInput]


@router.post("/ocr/recompute")
def recompute_ocr_statuses(req: OcrRecomputeRequest, db: sqlite3.Connection = Depends(get_db)) -> dict:
    """확인 화면에서 사용자가 값을 고칠 때마다 판정을 다시 계산한다.

    /ocr/scan의 nutrient_statuses는 스캔 시점 스냅샷이라, 사용자가 수치를 고치면
    화면의 판정과 실제 저장될 값이 어긋난다. 이 엔드포인트는 "지금 화면에 있는
    값 + 오늘 이미 저장된 누적분"으로 다시 판정해 그 간극을 없앤다.

    /ocr/scan과 달리 needs_review 개념이 없다 — 이 시점의 값은 전부 사용자가
    눈으로 확인한 값이기 때문이다.
    """
    cursor = db.cursor()
    cursor.execute("SELECT * FROM users WHERE user_id = ?", (req.user_id,))
    user = cursor.fetchone()
    if not user:
        raise HTTPException(status_code=404, detail="사용자를 찾을 수 없습니다.")
    user = dict(user)

    pending_values = {key: item.value for key, item in req.nutrients.items()}
    return build_ocr_status_view(pending_values, user, db)


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
        # 목 경로: 실제 분류 호출(최대 2회)을 건너뛴다. /ocr/scan과 같은 플래그를
        # 공유하므로 오프라인 작업 시 두 엔드포인트가 함께 목으로 동작한다.
        # --- 매칭/미매칭 경로를 시험할 때 여기를 바꾼다 ---
        # (None, None)으로 두면 실제로 분류 불가능한 제품을 찾지 않고도
        # "분류 실패 -> available=false" 경로를 탈 수 있다.
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
