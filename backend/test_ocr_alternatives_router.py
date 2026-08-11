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

프로덕션의 OCR_USE_MOCK_GEMINI 목 경로(routers/ocr.py)는 삭제됐다 —
/ocr/alternatives는 이제 항상 classify_food()를 호출한다. 이 파일의 테스트는
classify_food()(또는 그 아래 _call_gemini_enum_choice())를 필요한 곳마다 직접
monkeypatch해 실제 네트워크 호출 없이 커버리지를 유지한다 — 별도의 전역 목
fixture는 없다(아래 각 테스트가 자기 경로에 필요한 stub을 스스로 건다).
"""
import pytest
from fastapi import HTTPException

from backend import ocr_category_classifier
from backend.gemini_vision import GeminiDailyLimitExceededError
from backend.routers import ocr as ocr_router
from backend.routers.ocr import OcrAlternativesRequest, get_ocr_alternatives

from .conftest import make_food_item, make_user

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
        OcrAlternativesRequest(user_id=user_id, product_name=product_name, nutrients=_nutrients(sodium=2400.0)),
        db=db,
    )

    assert result["available"] is False
    assert result["trigger_nutrient"] == "sodium"
    assert classify_calls == []


def test_classification_failure_returns_unavailable(db, monkeypatch):
    user_id = make_user(db)
    monkeypatch.setattr(ocr_router, "classify_food", lambda name, db: (None, None))

    result = get_ocr_alternatives(
        OcrAlternativesRequest(user_id=user_id, product_name="알수없는제품", nutrients=_nutrients(sodium=2400.0)),
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
    monkeypatch.setattr(ocr_router, "classify_food", lambda name, db: ("빵 및 과자류", "과자"))

    result = get_ocr_alternatives(
        OcrAlternativesRequest(user_id=user_id, product_name="포카칩", nutrients=_nutrients(sodium=2400.0)),
        db=db,
    )

    assert result["available"] is False
    assert result["category"] is None
    assert result["subcategory"] is None


def test_happy_path_returns_available_with_sorted_alternatives(db, monkeypatch):
    user_id = make_user(db)
    make_food_item(db, food_name="라면_짜장라면 (100g)", subcategory="라면", sodium_mg=306.0)
    make_food_item(db, food_name="라면_김치 (760ml)", subcategory="라면", sodium_mg=828.4)
    monkeypatch.setattr(ocr_router, "classify_food", lambda name, db: ("면 및 만두류", "라면"))

    result = get_ocr_alternatives(
        OcrAlternativesRequest(user_id=user_id, product_name="신라면", nutrients=_nutrients(sodium=2400.0)),
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

    def _raise(prompt, choices):
        raise GeminiDailyLimitExceededError("상한 초과")
    monkeypatch.setattr(ocr_category_classifier, "_call_gemini_enum_choice", _raise)

    result = get_ocr_alternatives(
        OcrAlternativesRequest(user_id=user_id, product_name="신라면", nutrients=_nutrients(sodium=2400.0)),
        db=db,
    )

    assert result["available"] is False
    assert result["category"] is None

# test_mock_gemini_skips_real_classification은 여기 있었다 — USE_MOCK_GEMINI가
# 켜져 있으면 classify_food()를 건너뛰고 고정된 ("면 및 만두류","라면") 튜플을
# 쓰는 그 자체의 동작을 검증하던 테스트다. 검증 대상 동작(routers/ocr.py의
# USE_MOCK_GEMINI 분기)이 이번에 통째로 삭제되어 대응할 실제 코드가 없다 —
# "변환"이 아니라 삭제가 맞는 경우. 실제 classify_food() 성공 경로는 바로 위
# test_happy_path_returns_available_with_sorted_alternatives가 이미 같은
# 시나리오("면 및 만두류"/"라면" 분류 + 정렬된 대체재)를 실제 호출 경로로 커버한다.
