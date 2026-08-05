"""
backend/ocr_category_classifier.py 테스트.

핵심 검증 대상:
- get_category_taxonomy()가 dish_db_download 행만, category별로 올바르게 그룹화한다
- classify_category/classify_subcategory는 Gemini가 준 값이 후보 목록과 정확히
  일치할 때만 그 값을 반환한다 — 스키마 enum 강제를 우회해 목록 밖 값이 와도
  (_call_gemini_enum_choice를 직접 monkeypatch해 재현) None으로 처리한다
- classify_subcategory는 "다른 category에서는 유효했을 값"도 지금 category의
  목록에 없으면 무효로 취급한다 (전역 값이 아니라 category별로 좁힌 목록 기준)
- Gemini 호출이 예외를 던져도(일일 상한 포함) 절대 밖으로 새지 않고 None
- classify_food는 product_name이 비어있으면 Gemini를 한 번도 호출하지 않고
  (None, None)을 반환하고, category 분류가 실패하면 subcategory 분류를
  아예 시도하지 않는다(낭비되는 2번째 호출 방지)
"""
import pytest

from backend.gemini_vision import GeminiDailyLimitExceededError
from backend.ocr_category_classifier import (
    classify_category,
    classify_food,
    classify_subcategory,
    get_category_taxonomy,
)
from backend import ocr_category_classifier as classifier_module

from .conftest import make_food_item


# ── get_category_taxonomy ────────────────────────────────────────

def test_get_category_taxonomy_groups_by_category(db):
    make_food_item(db, food_name="라면A", category="면류", subcategory="라면")
    make_food_item(db, food_name="짜장면A", category="면류", subcategory="짜장면")
    make_food_item(db, food_name="커피A", category="음료류", subcategory="커피")

    taxonomy = get_category_taxonomy(db)

    assert set(taxonomy["면류"]) == {"라면", "짜장면"}
    assert taxonomy["음료류"] == ["커피"]


def test_get_category_taxonomy_excludes_non_dish_db_sources(db):
    make_food_item(db, food_name="API음식", category="면류", subcategory="라면",
                    data_source="food_nutrition_api")

    taxonomy = get_category_taxonomy(db)

    assert taxonomy == {}


def test_get_category_taxonomy_excludes_null_category_or_subcategory(db):
    make_food_item(db, food_name="분류없음", category=None, subcategory=None)

    taxonomy = get_category_taxonomy(db)

    assert taxonomy == {}


# ── classify_category ────────────────────────────────────────────

def test_classify_category_returns_exact_match(monkeypatch):
    monkeypatch.setattr(classifier_module, "_call_gemini_enum_choice", lambda prompt, choices: "면류")
    assert classify_category("신라면", ["면류", "음료류"]) == "면류"


def test_classify_category_rejects_off_list_value(monkeypatch):
    """스키마 enum 강제를 SDK가 지키지 못했다고 가정하고, _call_gemini_enum_choice가
    후보 목록에 없는 값을 그대로 반환하는 상황을 재현한다."""
    monkeypatch.setattr(classifier_module, "_call_gemini_enum_choice", lambda prompt, choices: "존재하지않는카테고리")
    assert classify_category("신라면", ["면류", "음료류"]) is None


def test_classify_category_returns_none_on_daily_limit_exceeded(monkeypatch):
    def _raise(prompt, choices):
        raise GeminiDailyLimitExceededError("상한 초과")
    monkeypatch.setattr(classifier_module, "_call_gemini_enum_choice", _raise)
    assert classify_category("신라면", ["면류", "음료류"]) is None


def test_classify_category_returns_none_on_generic_exception(monkeypatch):
    def _raise(prompt, choices):
        raise RuntimeError("network blew up")
    monkeypatch.setattr(classifier_module, "_call_gemini_enum_choice", _raise)
    assert classify_category("신라면", ["면류", "음료류"]) is None


def test_classify_category_empty_inputs_short_circuit(monkeypatch):
    calls = []
    monkeypatch.setattr(classifier_module, "_call_gemini_enum_choice", lambda prompt, choices: calls.append(1) or "면류")
    assert classify_category("", ["면류"]) is None
    assert classify_category("신라면", []) is None
    assert calls == []


# ── classify_subcategory ──────────────────────────────────────────

def test_classify_subcategory_returns_exact_match(monkeypatch):
    monkeypatch.setattr(classifier_module, "_call_gemini_enum_choice", lambda prompt, choices: "라면")
    assert classify_subcategory("신라면", "면류", ["라면", "짜장면"]) == "라면"


def test_classify_subcategory_rejects_value_valid_only_in_another_category(monkeypatch):
    """"커피"는 음료류의 실제 subcategory지만, 지금 분류 중인 category는 면류다 —
    전역 subcategory 집합이 아니라 이 category로 좁힌 목록 기준으로 검증해야 한다."""
    monkeypatch.setattr(classifier_module, "_call_gemini_enum_choice", lambda prompt, choices: "커피")
    assert classify_subcategory("신라면", "면류", ["라면", "짜장면"]) is None


def test_classify_subcategory_returns_none_on_exception(monkeypatch):
    def _raise(prompt, choices):
        raise GeminiDailyLimitExceededError("상한 초과")
    monkeypatch.setattr(classifier_module, "_call_gemini_enum_choice", _raise)
    assert classify_subcategory("신라면", "면류", ["라면"]) is None


# ── classify_food (오케스트레이션) ────────────────────────────────

@pytest.mark.parametrize("product_name", [None, "", "   "])
def test_classify_food_empty_product_name_makes_no_gemini_calls(db, monkeypatch, product_name):
    calls = []
    monkeypatch.setattr(
        classifier_module, "_call_gemini_enum_choice",
        lambda prompt, choices: calls.append(1) or "면류",
    )
    make_food_item(db, category="면류", subcategory="라면")

    result = classify_food(product_name, db)

    assert result == (None, None)
    assert calls == []


def test_classify_food_skips_subcategory_call_when_category_fails(db, monkeypatch):
    make_food_item(db, category="면류", subcategory="라면")

    monkeypatch.setattr(classifier_module, "classify_category", lambda name, cats: None)
    subcategory_calls = []
    monkeypatch.setattr(
        classifier_module, "classify_subcategory",
        lambda name, cat, subs: subcategory_calls.append(1) or "라면",
    )

    result = classify_food("신라면", db)

    assert result == (None, None)
    assert subcategory_calls == []


def test_classify_food_partial_classification_does_not_fall_back_to_category_only(db, monkeypatch):
    make_food_item(db, category="면류", subcategory="라면")

    monkeypatch.setattr(classifier_module, "classify_category", lambda name, cats: "면류")
    monkeypatch.setattr(classifier_module, "classify_subcategory", lambda name, cat, subs: None)

    assert classify_food("신라면", db) == (None, None)


def test_classify_food_happy_path(db, monkeypatch):
    make_food_item(db, category="면류", subcategory="라면")
    make_food_item(db, category="면류", subcategory="짜장면")

    monkeypatch.setattr(classifier_module, "classify_category", lambda name, cats: "면류")
    monkeypatch.setattr(classifier_module, "classify_subcategory", lambda name, cat, subs: "라면")

    assert classify_food("신라면", db) == ("면류", "라면")


def test_classify_food_no_taxonomy_available_returns_none(db):
    assert classify_food("신라면", db) == (None, None)
