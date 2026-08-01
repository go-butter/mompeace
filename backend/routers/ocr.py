from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from backend.gemini_vision import LabelNotDetectedError, call_gemini_vision
from backend.ocr_nutrition_parser import resolve_ocr_nutrients

router = APIRouter()

# TEMPORARY: no Gemini API key has been confirmed working yet, and frontend
# work on the capture/confirm/failure screens shouldn't block on that.
# Set this back to False once GEMINI_API_KEY is confirmed working.
USE_MOCK_GEMINI = True


class OcrScanRequest(BaseModel):
    image: str  # base64, no data-URI prefix


@router.post("/ocr/scan")
def scan_nutrition_label(req: OcrScanRequest):
    """
    영양성분표 이미지 OCR 인식

    1. Gemini Vision으로 이미지에서 필드 추출 (판정 없음, 추출만)
    2. 기준량/총 내용량/1회 제공량 스케일 적용
    3. 결과만 반환 — 저장은 하지 않음 (확정은 확인 화면 → 기존 /food-log POST)

    이미지 바이트는 이 요청 처리 동안만 메모리에 존재하며, 디스크에 쓰거나
    로그/에러 메시지에 포함하지 않는다.
    """

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
            "sugar_g_per_basis": 12.0,
            "sodium_mg_per_basis": 178.0,
        }
        # ---------------------------------------------------------------
        extraction = mock_extraction
    else:
        try:
            extraction = call_gemini_vision(req.image)
        except LabelNotDetectedError as e:
            raise HTTPException(status_code=422, detail=str(e) or "영양성분표를 인식하지 못했어요. 라벨이 잘 보이도록 다시 촬영해주세요.")
        except Exception:
            import traceback
            traceback.print_exc()
            raise HTTPException(status_code=500, detail="OCR 처리 중 오류가 발생했어요.")

    return resolve_ocr_nutrients(extraction)
