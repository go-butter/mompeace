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
  GeminiNotConfiguredError -> 503(error_code=OCR_UNAVAILABLE),
  GeminiDailyLimitExceededError -> 429(error_code=DAILY_LIMIT_REACHED),
  기타 예외 -> 502(error_code=GEMINI_CALL_FAILED) — 기존 라벨 미인식 422 경로는 그대로 유지
"""
import pytest
from fastapi import HTTPException

from backend.gemini_vision import (
    GeminiDailyLimitExceededError,
    GeminiNotConfiguredError,
    LabelNotDetectedError,
)
from backend.routers import ocr as ocr_router
from backend.routers.ocr import (
    OcrRecomputeNutrientInput,
    OcrRecomputeRequest,
    OcrScanRequest,
    recompute_ocr_statuses,
    scan_nutrition_label,
)

from .conftest import make_food_log, make_user


@pytest.fixture(autouse=True)
def force_mock_gemini(monkeypatch):
    """이 파일의 테스트는 절대 실제 Gemini를 호출하지 않는다.

    USE_MOCK_GEMINI가 소스 상수(True 고정)에서 환경변수(OCR_USE_MOCK_GEMINI, 기본
    false)로 바뀌면서 "테스트에서는 항상 목"이 더 이상 기본값에 딸려오지 않는다 —
    여기서 명시적으로 고정한다. 실제 호출 경로를 검증하는 테스트는 각자 다시
    False로 monkeypatch하며, 같은 monkeypatch 인스턴스라 나중 setattr이 이긴다.
    """
    monkeypatch.setattr(ocr_router, "USE_MOCK_GEMINI", True)


def test_scan_happy_path_returns_additive_fields(db):
    user_id = make_user(db)
    result = scan_nutrition_label(OcrScanRequest(image="ZmFrZQ==", user_id=user_id), db=db)

    # 기존 필드 — 하위 호환 확인 (기존 프론트엔드가 그대로 읽을 수 있어야 한다)
    for field in (
        "product_name", "sugar_g", "sodium_mg", "scale_method",
        "scale_factor_applied", "basis_amount_value", "needs_review",
    ):
        assert field in result

    # 새 필드 (단위 3종 — T3.1)
    for field in ("basis_amount_unit", "total_content_unit", "serving_size_unit"):
        assert field in result
    assert result["basis_amount_unit"] == "g"
    assert result["total_content_unit"] == "g"
    assert result["serving_size_unit"] == "g"

    # nutrients는 OCR이 추출할 수 있는 7개 그대로다 (카페인은 라벨에 없으므로 제외)
    assert set(result["nutrients"].keys()) == {
        "carbohydrate", "sugar", "energy", "fat", "iron", "protein", "sodium",
    }
    # nutrient_statuses는 일일 투영 판정이라 카페인을 포함해 8개다 (T5)
    assert len(result["nutrient_statuses"]) == 8
    assert {item["key"] for item in result["nutrient_statuses"]} == {
        "carbohydrate", "sugar", "energy", "fat", "iron", "protein", "sodium", "caffeine",
    }
    # 각 항목이 T5에서 추가된 필드를 갖는다
    for item in result["nutrient_statuses"]:
        assert set(item) == {
            "key", "label", "unit", "value", "limit", "percent", "status", "status_label", "tier",
        }
    assert "headline" in result
    assert result["total_content_value"] == 355.0
    assert result["needs_review"] is False
    # 기존 sugar_g/sodium_mg는 nutrients 아래 값과 동일해야 한다
    assert result["sugar_g"] == result["nutrients"]["sugar"]["serving_value"]
    assert result["sodium_mg"] == result["nutrients"]["sodium"]["serving_value"]


def test_scan_projects_onto_todays_saved_totals(db):
    # T5의 핵심: 확인 화면 카드 제목이 "오늘 섭취 안전도"인 만큼, 판정은 품목
    # 단독이 아니라 "오늘 누적 + 이 품목"이어야 한다. 목 데이터의 나트륨은
    # 178mg/100g * 0.3 = 53.4mg으로 단독으로는 안전하지만, 이미 1450mg을 먹은
    # 날이라면 합계가 한도를 넘는다.
    user_id = make_user(db)
    make_food_log(db, user_id, sodium_mg=1450)

    result = scan_nutrition_label(OcrScanRequest(image="ZmFrZQ==", user_id=user_id), db=db)

    sodium = next(i for i in result["nutrient_statuses"] if i["key"] == "sodium")
    assert sodium["value"] == pytest.approx(1503.4)
    assert sodium["tier"] == "avoid"


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


def test_scan_not_configured_returns_503_with_error_code(db, monkeypatch):
    # 키 미설정은 502(호출 실패)와 구분되어야 한다 — 재촬영으로 해결되지 않는
    # 서버 설정 문제라, 화면이 다른 안내를 보여줄 수 있어야 한다.
    monkeypatch.setattr(ocr_router, "USE_MOCK_GEMINI", False)
    monkeypatch.setattr(
        ocr_router,
        "call_gemini_vision",
        lambda image: (_ for _ in ()).throw(GeminiNotConfiguredError("키 없음")),
    )

    user_id = make_user(db)
    with pytest.raises(HTTPException) as exc_info:
        scan_nutrition_label(OcrScanRequest(image="ZmFrZQ==", user_id=user_id), db=db)
    assert exc_info.value.status_code == 503
    assert exc_info.value.detail["error_code"] == "OCR_UNAVAILABLE"


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


# ── POST /ocr/recompute ──────────────────────────────────────────
# 확인 화면에서 값을 고칠 때마다 판정을 다시 계산하는 엔드포인트. Gemini를
# 호출하지 않으므로 목 플래그와 무관하게 동작한다.

def _recompute(db, user_id, **values):
    """values: key=값(또는 (값, source)). 지정하지 않은 영양소는 화면에서 비어
    있는 것으로 보고 None을 보낸다 — 8칸 전부를 항상 보내는 실제 호출과 동일."""
    nutrients = {}
    for key in ("carbohydrate", "sugar", "energy", "fat", "iron", "protein", "sodium", "caffeine"):
        raw = values.get(key)
        if isinstance(raw, tuple):
            value, source = raw
        else:
            value, source = raw, "manual"
        nutrients[key] = OcrRecomputeNutrientInput(value=value, source=source)
    return recompute_ocr_statuses(OcrRecomputeRequest(user_id=user_id, nutrients=nutrients), db=db)


def _by_key(result):
    return {item["key"]: item for item in result["nutrient_statuses"]}


def test_recompute_missing_user_returns_404(db):
    with pytest.raises(HTTPException) as exc_info:
        _recompute(db, 999999, sodium=100.0)
    assert exc_info.value.status_code == 404


def test_recompute_returns_eight_statuses_and_headline(db):
    user_id = make_user(db)

    result = _recompute(db, user_id, sodium=800.0)

    assert len(result["nutrient_statuses"]) == 8
    assert "headline" in result


def test_recompute_blends_in_todays_saved_totals(db):
    user_id = make_user(db)
    make_food_log(db, user_id, sodium_mg=1400)

    result = _recompute(db, user_id, sodium=1710.0)

    sodium = _by_key(result)["sodium"]
    assert sodium["value"] == 3110
    assert sodium["tier"] == "avoid"
    assert result["headline"]["key"] == "sodium"


def test_recompute_manually_typed_iron_gets_a_real_verdict(db):
    # 라벨에 철분이 없어 OCR은 null을 주지만, 사용자가 직접 입력하면 판정된다.
    user_id = make_user(db)

    result = _recompute(db, user_id, iron=(50.0, "manual"))

    iron = _by_key(result)["iron"]
    assert iron["status"] == "avoid"
    assert iron["tier"] == "avoid"


def test_recompute_empty_nutrient_stays_unknown(db):
    user_id = make_user(db)

    result = _recompute(db, user_id, sodium=800.0)

    # 사용자가 비워둔 칸은 None으로 전송되어 unknown으로 남는다 (정보 없음 ≠ 0)
    iron = _by_key(result)["iron"]
    assert iron["status"] == "unknown"
    assert iron["value"] is None


def test_recompute_judges_typed_caffeine(db):
    user_id = make_user(db)

    result = _recompute(db, user_id, caffeine=250.0)

    caffeine = _by_key(result)["caffeine"]
    assert caffeine["value"] == 250
    assert caffeine["tier"] == "avoid"


def test_recompute_shows_accumulated_caffeine_before_user_types_anything(db):
    user_id = make_user(db)
    make_food_log(db, user_id, caffeine_mg=180)

    result = _recompute(db, user_id, sodium=100.0)  # 카페인은 None으로 전송됨

    caffeine = _by_key(result)["caffeine"]
    assert caffeine["value"] == 180
    assert caffeine["tier"] == "caution"


def test_recompute_source_marker_does_not_affect_judgment(db):
    # source는 저장 스냅샷용 메타데이터일 뿐 판정에 관여하지 않는다.
    user_id = make_user(db)

    from_ocr = _recompute(db, user_id, sodium=(1710.0, "ocr"))
    from_manual = _recompute(db, user_id, sodium=(1710.0, "manual"))

    assert from_ocr["nutrient_statuses"] == from_manual["nutrient_statuses"]
    assert from_ocr["headline"] == from_manual["headline"]


def test_recompute_source_defaults_to_manual_when_omitted(db):
    # 화면이 source를 빼먹어도 요청이 깨지지 않아야 한다.
    user_id = make_user(db)
    request = OcrRecomputeRequest(user_id=user_id, nutrients={"sodium": {"value": 800.0}})

    result = recompute_ocr_statuses(request, db=db)

    assert request.nutrients["sodium"].source == "manual"
    assert _by_key(result)["sodium"]["value"] == 800


def test_recompute_floor_shortfall_is_neutral_and_not_the_headline(db):
    user_id = make_user(db)

    result = _recompute(db, user_id, protein=5.0, carbohydrate=20.0)

    assert _by_key(result)["protein"]["tier"] == "neutral"
    assert result["headline"] is None


def test_recompute_is_deterministic_across_repeated_calls(db):
    # 디바운스로 타이핑마다 호출되므로 같은 입력이면 항상 같은 결과여야 한다.
    user_id = make_user(db)
    make_food_log(db, user_id, sodium_mg=1400, caffeine_mg=190)

    keys = {_recompute(db, user_id, sodium=1710.0)["headline"]["key"] for _ in range(20)}

    assert len(keys) == 1
