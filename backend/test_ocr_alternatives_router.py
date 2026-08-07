"""
backend/routers/ocr.py::get_ocr_alternatives() 테스트.

test_ocr_router.py와 동일하게 FastAPI TestClient가 아니라 라우터 함수를 직접
호출한다 (conftest.py의 인메모리 DB 격리 원칙 참고).

핵심 검증 대상:
- avoid인 영양소가 하나도 없으면 available=false이고 분류/조회 함수를 아예
  호출하지 않는다 (Gemini 호출도, DB 후보 조회도 낭비하지 않는다)
- product_name이 비어있으면 avoid가 있어도 분류를 시도하지 않는다
- 분류 실패, 후보 0건 등 모든 "매칭 안 됨" 경로가 동일하게 available=false로
  수렴한다
- Gemini 분류 중 일일 상한 초과가 나도 /ocr/scan과 달리 429가 아니라
  200(available=false)으로 응답한다 — 대체 메뉴는 부가 기능이라 실패가
  스캔 흐름을 막으면 안 된다는 설계 결정을 라우터 레벨에서 확인
- user_id가 없으면 404 (기존 패턴)
- USE_MOCK_GEMINI=True면 classify_food()를 아예 호출하지 않고 고정된 목 분류
  결과를 쓴다 — 개발/기기 테스트가 실제 Gemini 호출(및
  GEMINI_CLASSIFY_DAILY_CALL_LIMIT)을 소모하지 않도록. classify_food()의 실제
  동작을 검증하는 테스트들은 이 플래그를 False로 monkeypatch해 실제 경로를
  강제한다.
"""
import pytest
from fastapi import HTTPException

from backend import ocr_category_classifier
from backend.gemini_vision import GeminiDailyLimitExceededError
from backend.routers import ocr as ocr_router
from backend.routers.ocr import OcrAlternativesRequest, get_ocr_alternatives

from .conftest import make_food_item, make_user


@pytest.fixture(autouse=True)
def force_mock_gemini(monkeypatch):
    """test_ocr_router.py의 같은 이름 fixture와 동일한 이유 — USE_MOCK_GEMINI가
    환경변수(기본 false)로 바뀌었으므로 테스트에서 명시적으로 목을 고정한다."""
    monkeypatch.setattr(ocr_router, "USE_MOCK_GEMINI", True)

_ALL_KEYS = ("carbohydrate", "sugar", "energy", "fat", "iron", "protein", "sodium")


def _nutrients(**overrides) -> dict:
    return {k: overrides.get(k) for k in _ALL_KEYS}


def test_missing_user_returns_404(db):
    with pytest.raises(HTTPException) as exc_info:
        get_ocr_alternatives(
            OcrAlternativesRequest(user_id=999999, product_name="신라면", nutrients=_nutrients()),
            db=db,
        )
    assert exc_info.value.status_code == 404


def test_no_avoid_nutrient_skips_classification_and_query(db, monkeypatch):
    user_id = make_user(db)
    classify_calls = []
    query_calls = []
    monkeypatch.setattr(ocr_router, "classify_food", lambda name, db: classify_calls.append(1) or (None, None))
    monkeypatch.setattr(ocr_router, "find_subcategory_alternatives", lambda *a, **k: query_calls.append(1) or [])

    result = get_ocr_alternatives(
        OcrAlternativesRequest(user_id=user_id, product_name="신라면", nutrients=_nutrients()),
        db=db,
    )

    assert result == {
        "available": False, "trigger_nutrient": None, "category": None,
        "subcategory": None, "alternatives": [],
    }
    assert classify_calls == []
    assert query_calls == []


@pytest.mark.parametrize("product_name", [None, "", "   "])
def test_avoid_present_but_empty_product_name_skips_classification(db, monkeypatch, product_name):
    user_id = make_user(db)
    classify_calls = []
    monkeypatch.setattr(ocr_router, "classify_food", lambda name, db: classify_calls.append(1) or (None, None))

    result = get_ocr_alternatives(
        OcrAlternativesRequest(user_id=user_id, product_name=product_name, nutrients=_nutrients(sodium=2000.0)),
        db=db,
    )

    assert result["available"] is False
    assert result["trigger_nutrient"] == "sodium"
    assert classify_calls == []


def test_classification_failure_returns_unavailable(db, monkeypatch):
    user_id = make_user(db)
    monkeypatch.setattr(ocr_router, "USE_MOCK_GEMINI", False)
    monkeypatch.setattr(ocr_router, "classify_food", lambda name, db: (None, None))

    result = get_ocr_alternatives(
        OcrAlternativesRequest(user_id=user_id, product_name="알수없는제품", nutrients=_nutrients(sodium=2000.0)),
        db=db,
    )

    assert result["available"] is False
    assert result["trigger_nutrient"] == "sodium"
    assert result["category"] is None
    assert result["subcategory"] is None


def test_classification_succeeds_but_no_candidates_returns_unavailable(db, monkeypatch):
    """분류는 성공했지만 그 subcategory에 dish_db_download 후보가 하나도 없는 경우
    (포장 과자/음료류처럼 조사에서 확인된 정상 케이스) — available=false여야 한다."""
    user_id = make_user(db)
    monkeypatch.setattr(ocr_router, "USE_MOCK_GEMINI", False)
    monkeypatch.setattr(ocr_router, "classify_food", lambda name, db: ("빵 및 과자류", "과자"))

    result = get_ocr_alternatives(
        OcrAlternativesRequest(user_id=user_id, product_name="포카칩", nutrients=_nutrients(sodium=2000.0)),
        db=db,
    )

    assert result["available"] is False
    assert result["category"] is None
    assert result["subcategory"] is None


def test_happy_path_returns_available_with_sorted_alternatives(db, monkeypatch):
    user_id = make_user(db)
    make_food_item(db, food_name="라면_짜장라면 (100g)", subcategory="라면", sodium_mg=306.0)
    make_food_item(db, food_name="라면_김치 (760ml)", subcategory="라면", sodium_mg=828.4)
    monkeypatch.setattr(ocr_router, "USE_MOCK_GEMINI", False)
    monkeypatch.setattr(ocr_router, "classify_food", lambda name, db: ("면 및 만두류", "라면"))

    result = get_ocr_alternatives(
        OcrAlternativesRequest(user_id=user_id, product_name="신라면", nutrients=_nutrients(sodium=2000.0)),
        db=db,
    )

    assert result["available"] is True
    assert result["trigger_nutrient"] == "sodium"
    assert result["category"] == "면 및 만두류"
    assert result["subcategory"] == "라면"
    assert [a["food_name"] for a in result["alternatives"]] == [
        "라면_짜장라면 (100g)", "라면_김치 (760ml)",
    ]


def test_gemini_daily_limit_during_classification_degrades_to_unavailable_not_429(db, monkeypatch):
    """/ocr/scan과 달리 대체 메뉴는 부가 기능이므로, 분류 중 일일 상한 초과가 나도
    예외를 올리지 않고 200 + available=false로 응답해야 한다."""
    user_id = make_user(db)
    make_food_item(db, category="면 및 만두류", subcategory="라면", sodium_mg=100.0)
    monkeypatch.setattr(ocr_router, "USE_MOCK_GEMINI", False)

    def _raise(prompt, choices):
        raise GeminiDailyLimitExceededError("상한 초과")
    monkeypatch.setattr(ocr_category_classifier, "_call_gemini_enum_choice", _raise)

    result = get_ocr_alternatives(
        OcrAlternativesRequest(user_id=user_id, product_name="신라면", nutrients=_nutrients(sodium=2000.0)),
        db=db,
    )

    assert result["available"] is False
    assert result["category"] is None


def test_mock_gemini_skips_real_classification(db, monkeypatch):
    """USE_MOCK_GEMINI가 켜져 있으면 classify_food()를 한 번도 호출하지 않고,
    고정된 목 분류 결과("면 및 만두류"/"라면")로 실제 DB 후보를 조회한다 —
    실제 키가 있어도 개발/기기 테스트가 GEMINI_CLASSIFY_DAILY_CALL_LIMIT을
    소모하지 않아야 한다.

    (이 플래그의 기본값은 이제 환경변수 OCR_USE_MOCK_GEMINI이며 기본 false다 —
    "켜져 있으면"을 만드는 것은 이 파일의 autouse fixture다.)"""
    user_id = make_user(db)
    make_food_item(db, food_name="라면_라면만 (100g)", subcategory="라면", sodium_mg=306.0)
    classify_calls = []
    monkeypatch.setattr(ocr_router, "classify_food", lambda name, db: classify_calls.append(1) or ("x", "y"))

    result = get_ocr_alternatives(
        OcrAlternativesRequest(user_id=user_id, product_name="신라면", nutrients=_nutrients(sodium=2000.0)),
        db=db,
    )

    assert classify_calls == []
    assert result["available"] is True
    assert result["category"] == "면 및 만두류"
    assert result["subcategory"] == "라면"
    assert [a["food_name"] for a in result["alternatives"]] == ["라면_라면만 (100g)"]
