"""
backend/routers/ocr.py::scan_nutrition_label() 테스트.

이 프로젝트의 다른 라우터 테스트(test_food_log_ocr.py 등)와 동일하게, FastAPI
TestClient/실제 HTTP 요청이 아니라 라우터 함수를 직접 호출한다 — backend/main.py를
임포트하면 모듈 최상단에서 init_db()가 실제 mompeace.db 파일에 대해 실행되어버려
conftest.py의 인메모리 DB 격리 원칙과 충돌하므로 그 경로를 피한다.

핵심 검증 대상:
- user_id가 유효하면(목 Gemini 경로) 응답에 기존 필드(sugar_g/sodium_mg/scale_method/...)와
  새 필드(nutrients/nutrient_statuses/total_content_value)가 모두 존재한다 (additive)
- needs_review=True인 경우 실제 값과 무관하게 7개 nutrient_statuses가 전부 정보없음이다
- 존재하지 않는 user_id는 404
- (실제 Gemini 경로, USE_MOCK_GEMINI=False로 monkeypatch) LabelNotDetectedError -> 422,
  GeminiDailyLimitExceededError -> 429(error_code=DAILY_LIMIT_REACHED),
  기타 예외 -> 502(error_code=GEMINI_CALL_FAILED) — 기존 라벨 미인식 422 경로는 그대로 유지
"""
import pytest
from fastapi import HTTPException

from backend.gemini_vision import GeminiDailyLimitExceededError, LabelNotDetectedError
from backend.routers import ocr as ocr_router
from backend.routers.ocr import OcrScanRequest, scan_nutrition_label

from .conftest import make_user


def test_scan_happy_path_returns_additive_fields(db):
    user_id = make_user(db)
    result = scan_nutrition_label(OcrScanRequest(image="ZmFrZQ==", user_id=user_id), db=db)

    # 기존 필드 — 하위 호환 확인 (기존 프론트엔드가 그대로 읽을 수 있어야 한다)
    for field in (
        "product_name", "sugar_g", "sodium_mg", "scale_method",
        "scale_factor_applied", "basis_amount_value", "needs_review",
    ):
        assert field in result

    # 새 필드
    assert set(result["nutrients"].keys()) == {
        "carbohydrate", "sugar", "energy", "fat", "iron", "protein", "sodium",
    }
    assert len(result["nutrient_statuses"]) == 7
    assert result["total_content_value"] == 355.0
    assert result["needs_review"] is False
    # 기존 sugar_g/sodium_mg는 nutrients 아래 값과 동일해야 한다
    assert result["sugar_g"] == result["nutrients"]["sugar"]["serving_value"]
    assert result["sodium_mg"] == result["nutrients"]["sodium"]["serving_value"]


def test_scan_missing_user_returns_404(db):
    with pytest.raises(HTTPException) as exc_info:
        scan_nutrition_label(OcrScanRequest(image="ZmFrZQ==", user_id=999999), db=db)
    assert exc_info.value.status_code == 404


def test_scan_needs_review_forces_all_statuses_unknown(db, monkeypatch):
    # needs_review=True인데도 값이 남아있으면(스케일 미확정 raw passthrough) 그대로
    # 판정에 흘려보내면 착시가 생긴다 — 라우터가 이 경우 전부 None으로 바꿔 넘기는지
    # 확인한다. resolve_ocr_nutrients 자체는 별도 파일에서 이미 검증되므로, 여기서는
    # 라우터의 오케스트레이션(needs_review일 때 상태 입력을 None으로 바꾸는지)만 격리해 본다.
    fake_resolved = {
        "product_name": "테스트",
        "sugar_g": 60.0,  # 그대로 판정하면 avoid가 나올 만큼 큰 값
        "sodium_mg": 60.0,
        "scale_method": "unknown",
        "scale_factor_applied": None,
        "basis_amount_value": None,
        "total_content_value": None,
        "needs_review": True,
        "nutrients": {
            key: {"basis_value": 60.0, "serving_value": 60.0, "total_value": None}
            for key in ("carbohydrate", "sugar", "energy", "fat", "iron", "protein", "sodium")
        },
    }
    monkeypatch.setattr(ocr_router, "resolve_ocr_nutrients", lambda extraction: fake_resolved)

    user_id = make_user(db)
    result = scan_nutrition_label(OcrScanRequest(image="ZmFrZQ==", user_id=user_id), db=db)

    assert all(item["status"] == "unknown" for item in result["nutrient_statuses"])
    assert all(item["status_label"] == "정보없음" for item in result["nutrient_statuses"])


def test_scan_label_not_detected_returns_422(db, monkeypatch):
    monkeypatch.setattr(ocr_router, "USE_MOCK_GEMINI", False)
    monkeypatch.setattr(
        ocr_router,
        "call_gemini_vision",
        lambda image: (_ for _ in ()).throw(LabelNotDetectedError("영양성분표를 인식하지 못했습니다.")),
    )

    user_id = make_user(db)
    with pytest.raises(HTTPException) as exc_info:
        scan_nutrition_label(OcrScanRequest(image="ZmFrZQ==", user_id=user_id), db=db)
    assert exc_info.value.status_code == 422


def test_scan_daily_limit_exceeded_returns_429_with_error_code(db, monkeypatch):
    monkeypatch.setattr(ocr_router, "USE_MOCK_GEMINI", False)
    monkeypatch.setattr(
        ocr_router,
        "call_gemini_vision",
        lambda image: (_ for _ in ()).throw(GeminiDailyLimitExceededError("상한 초과")),
    )

    user_id = make_user(db)
    with pytest.raises(HTTPException) as exc_info:
        scan_nutrition_label(OcrScanRequest(image="ZmFrZQ==", user_id=user_id), db=db)
    assert exc_info.value.status_code == 429
    assert exc_info.value.detail["error_code"] == "DAILY_LIMIT_REACHED"


def test_scan_generic_gemini_failure_returns_502_with_error_code(db, monkeypatch):
    monkeypatch.setattr(ocr_router, "USE_MOCK_GEMINI", False)
    monkeypatch.setattr(
        ocr_router,
        "call_gemini_vision",
        lambda image: (_ for _ in ()).throw(RuntimeError("network blew up")),
    )

    user_id = make_user(db)
    with pytest.raises(HTTPException) as exc_info:
        scan_nutrition_label(OcrScanRequest(image="ZmFrZQ==", user_id=user_id), db=db)
    assert exc_info.value.status_code == 502
    assert exc_info.value.detail["error_code"] == "GEMINI_CALL_FAILED"
