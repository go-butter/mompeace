"""
OCR로 인식한 제품명을 food_items.category/subcategory 값으로 2단계 분류한다.

역할은 "제품명 텍스트 -> 우리 DB에 실제로 존재하는 category/subcategory 값 중
하나 선택"에 한정된다. 이미지는 다시 보내지 않는다 (분류는 텍스트만으로 충분하며,
gemini_vision.py의 이미지 추출과는 별개 관심사로 분리 유지한다 — 그 파일은 이 모듈
때문에 수정하지 않는다).

후보 목록(category 25개, category별 subcategory 목록)은 매 호출마다 food_items에서
직접 조회한다 (하드코딩 상수 아님) — import_dish_db.py가 엑셀을 다시 임포트할 때마다
값이 바뀔 수 있어, 상수로 고정하면 조용히 낡아버리기 때문이다.

Gemini의 스키마 enum 강제만으로는 부족하다고 보고, 반환값은 항상 우리가 넘긴 후보
목록과 정확히 일치하는지 파이썬에서 다시 검증한다 — 불일치/예외/일일 호출 상한 초과는
전부 "분류 실패"(None)로 취급하고 절대 예외를 밖으로 올리지 않는다. 대체 메뉴는 부가
기능이라, 분류 실패가 스캔 흐름 자체를 막아서는 안 된다.
"""
from __future__ import annotations

import os
import sqlite3
from datetime import date
from typing import Literal, Optional

from google import genai
from google.genai import types
from pydantic import BaseModel, create_model

from backend.gemini_vision import GEMINI_API_KEY, GeminiDailyLimitExceededError

# gemini_vision.py가 실제로 성공시키고 있는 모델로 맞춘다 (2.5-flash가 신규 키에
# 더 이상 제공되지 않는 경위는 ai_report_summary.py의 같은 상수 주석 참고) —
# classify_food()가 "절대 예외를 올리지 않는" 설계(위 모듈 docstring)라 그 404는
# 조용히 삼켜져 왔을 가능성이 크다.
MODEL_NAME = "gemini-3.6-flash"

# 추출(gemini_vision.py)과는 별개의 하루 호출 상한 — 대체 메뉴는 부가 기능이므로
# 핵심 기능인 OCR 추출의 호출 상한을 잠식해서는 안 된다.
GEMINI_CLASSIFY_DAILY_CALL_LIMIT = int(os.getenv("GEMINI_CLASSIFY_DAILY_CALL_LIMIT", "30"))

_call_count_by_day: dict[str, int] = {}

_ALLOWED_SOURCE = "dish_db_download"

_CATEGORY_PROMPT = """\
아래는 포장식품 라벨에서 인식한 제품명입니다.
제품명: {product_name}

이 제품이 속할 가능성이 가장 높은 음식 대분류(category)를 반드시 주어진 목록 중
하나로만 답하세요. 목록에 없는 값을 만들어내지 마세요.
"""

_SUBCATEGORY_PROMPT = """\
아래는 포장식품 라벨에서 인식한 제품명입니다.
제품명: {product_name}
이미 "{category}" 대분류로 분류되었습니다.

이 제품이 속할 가능성이 가장 높은 소분류(subcategory)를 반드시 주어진 목록 중
하나로만 답하세요. 목록에 없는 값을 만들어내지 마세요.
"""


def _under_daily_limit() -> bool:
    today = date.today().isoformat()
    return _call_count_by_day.get(today, 0) < GEMINI_CLASSIFY_DAILY_CALL_LIMIT


def _record_call() -> None:
    today = date.today().isoformat()
    _call_count_by_day[today] = _call_count_by_day.get(today, 0) + 1


def get_category_taxonomy(db: sqlite3.Connection) -> dict[str, list[str]]:
    """food_items(dish_db_download)에 실제 존재하는 category -> subcategory 목록을
    조회한다. 한 번의 쿼리로 전체를 가져온 뒤 파이썬에서 그룹화한다."""
    cursor = db.cursor()
    cursor.execute(
        "SELECT DISTINCT category, subcategory FROM food_items "
        "WHERE data_source = ? AND category IS NOT NULL AND subcategory IS NOT NULL",
        (_ALLOWED_SOURCE,),
    )
    taxonomy: dict[str, list[str]] = {}
    for row in cursor.fetchall():
        taxonomy.setdefault(row["category"], []).append(row["subcategory"])
    for category, subcategories in taxonomy.items():
        taxonomy[category] = sorted(set(subcategories))
    return taxonomy


def _build_choice_model(choices: list[str]) -> type[BaseModel]:
    """choices 값들만 허용하는 단일 필드짜리 Pydantic 모델을 동적으로 만든다.
    gemini_vision.py의 GeminiLabelExtraction과 동일한 JSON response_schema 방식을
    재사용한다 — 이 프로젝트/SDK 조합에서 이미 검증된 패턴이라 그대로 따른다."""
    literal_type = Literal[tuple(choices)]  # type: ignore[valid-type]
    return create_model("ChoiceResponse", choice=(literal_type, ...))


def _call_gemini_enum_choice(prompt: str, choices: list[str]) -> str:
    """choices 중 정확히 하나를 고르도록 강제한 Gemini 텍스트 전용(이미지 없음) 호출.

    호출 실패/파싱 실패/일일 상한 초과 시 예외를 그대로 올린다 — swallow는 이 함수를
    호출하는 classify_category/classify_subcategory의 책임이다 (테스트에서 이 함수를
    직접 monkeypatch해 "스키마를 어긴 값을 반환" 같은 상황도 재현할 수 있도록, 이
    함수는 검증 없이 원문 문자열만 반환한다 — 후보 목록과의 일치 검증은 호출부가 한다).
    """
    if not GEMINI_API_KEY:
        raise RuntimeError("GEMINI_API_KEY가 .env 파일에 설정되어 있지 않습니다.")
    if not _under_daily_limit():
        raise GeminiDailyLimitExceededError(
            f"하루 Gemini 분류 호출 상한({GEMINI_CLASSIFY_DAILY_CALL_LIMIT}회)을 초과했습니다."
        )

    choice_model = _build_choice_model(choices)
    client = genai.Client(api_key=GEMINI_API_KEY)
    _record_call()
    response = client.models.generate_content(
        model=MODEL_NAME,
        contents=prompt,
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=choice_model,
        ),
    )
    parsed = choice_model.model_validate_json(response.text)
    return parsed.choice


def classify_category(product_name: str, categories: list[str]) -> Optional[str]:
    """product_name을 categories 중 하나로 분류한다. 정확히 일치하지 않거나
    호출 자체가 실패하면(일일 상한 포함) None — 절대 예외를 올리지 않는다."""
    if not product_name or not categories:
        return None
    try:
        result = _call_gemini_enum_choice(
            _CATEGORY_PROMPT.format(product_name=product_name), categories
        )
    except Exception:
        return None
    return result if result in categories else None


def classify_subcategory(product_name: str, category: str, subcategories: list[str]) -> Optional[str]:
    """product_name을 (이미 정해진) category 아래 subcategories 중 하나로 분류한다.
    다른 category에서는 유효했을 값이라도, 이 category의 목록에 없으면 무효로
    취급한다 (전역 1,236개 값이 아니라 category별로 좁힌 목록 기준 검증)."""
    if not product_name or not subcategories:
        return None
    try:
        result = _call_gemini_enum_choice(
            _SUBCATEGORY_PROMPT.format(product_name=product_name, category=category),
            subcategories,
        )
    except Exception:
        return None
    return result if result in subcategories else None


def classify_food(product_name: Optional[str], db: sqlite3.Connection) -> tuple[Optional[str], Optional[str]]:
    """product_name -> (category, subcategory) 2단계 분류를 오케스트레이션한다.

    product_name이 비어있거나, category 분류가 실패하거나, subcategory 분류가
    실패하면 (None, None) — category만 맞고 subcategory가 틀린 부분 분류는
    category 단독 매칭으로 폴백하지 않는다(확정된 범위: category 단독 매칭은
    너무 넓어서 이미 배제됨).
    """
    if not product_name or not product_name.strip():
        return None, None

    taxonomy = get_category_taxonomy(db)
    if not taxonomy:
        return None, None

    category = classify_category(product_name, list(taxonomy.keys()))
    if category is None:
        return None, None

    subcategory = classify_subcategory(product_name, category, taxonomy[category])
    if subcategory is None:
        return None, None

    return category, subcategory
