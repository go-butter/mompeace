"""
Gemini Vision 기반 영양성분표 OCR 추출.

역할은 "이미지 → 구조화된 필드 추출"에 한정된다 (분리의 원칙 — 안전 판정은
절대 하지 않음, risk.py/recommendation_model.py 규칙 엔진이 전담). 카페인은
추출 대상에서 완전히 제외한다 (OCR 기능 자체의 범위 밖).

이미지 바이트는 이 모듈 함수 안에서만 잠깐 메모리에 존재하고, 디스크에 쓰거나
로그에 남기지 않는다 (최소 보유 원칙).
"""
from __future__ import annotations

import base64
import os
from typing import Literal, Optional

from dotenv import load_dotenv
from google import genai
from google.genai import types
from pydantic import BaseModel

load_dotenv()

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

MODEL_NAME = "gemini-2.5-flash"

_PROMPT = """\
당신은 한국 포장식품 영양성분표 이미지를 읽고 구조화된 데이터를 추출하는 도구입니다.
반드시 아래 JSON 스키마 형식으로만 응답하세요. 판정이나 안전성 평가는 하지 마세요 —
오직 라벨에 적힌 값을 그대로 추출하는 것이 역할입니다.

추출할 필드:
- product_name: 제품명 (읽을 수 없으면 null)
- nutrition_table_found: 이미지에 영양성분표가 실제로 존재하는지 (true/false)
- reference_amount_display_method: 다음 중 하나
  - "total_content": 1회 제공량 = 총 내용량인 경우 (예: "총 내용량 500ml, 나트륨 200mg")
  - "per_basis_with_total": 100g/100ml 등 기준량 표기 + 총 내용량이 별도 표기된 경우
    (예: "나트륨 50mg(100g당)", "총 내용량 355g")
  - "per_serving_with_count": 1회 제공량 + 총 제공 횟수로 표기된 경우
    (예: "1회 제공량 30g(총 3회 제공량)")
  - "unknown": 위 세 가지 중 어느 것인지 판단할 수 없는 경우
- basis_amount_value: 기준량 숫자 (예: "100g" → 100). 없으면 null
- total_content_value: 총 내용량 숫자 (예: "355g" → 355). 없으면 null
- servings_per_container: 총 제공 횟수 (예: "총 3회 제공량" → 3). 없으면 null
- sugar_g_per_basis: 기준량 당 당류(g). 읽을 수 없으면 null (0으로 추측하지 말 것)
- sodium_mg_per_basis: 기준량 당 나트륨(mg). 읽을 수 없으면 null (0으로 추측하지 말 것)

카페인 관련 필드는 추출하지 않습니다.
"""


class GeminiLabelExtraction(BaseModel):
    product_name: Optional[str] = None
    nutrition_table_found: bool
    reference_amount_display_method: Literal[
        "total_content", "per_basis_with_total", "per_serving_with_count", "unknown"
    ] = "unknown"
    basis_amount_value: Optional[float] = None
    total_content_value: Optional[float] = None
    servings_per_container: Optional[float] = None
    sugar_g_per_basis: Optional[float] = None
    sodium_mg_per_basis: Optional[float] = None


class LabelNotDetectedError(Exception):
    """Gemini가 이미지에서 영양성분표 자체를 찾지 못한 경우.
    ("찾았지만 환산 방식이 불명확함"과는 다른 케이스 — 그쪽은 needs_review로 처리)"""


def _strip_data_uri_prefix(image_base64: str) -> str:
    if "," in image_base64 and image_base64[:5] == "data:":
        return image_base64.split(",", 1)[1]
    return image_base64


def _build_contents(image_base64: str) -> list:
    image_bytes = base64.b64decode(_strip_data_uri_prefix(image_base64))
    return [
        types.Part.from_bytes(data=image_bytes, mime_type="image/jpeg"),
        _PROMPT,
    ]


def _parse_response(raw_text: str) -> dict:
    """Gemini 응답 원문(JSON 문자열)을 GeminiLabelExtraction으로 검증 후 dict로 변환.
    네트워크 호출 없이 이 함수만 단위 테스트 가능하도록 분리."""
    extraction = GeminiLabelExtraction.model_validate_json(raw_text)
    return extraction.model_dump()


def call_gemini_vision(image_base64: str) -> dict:
    """
    Gemini Vision을 호출해 영양성분표 이미지를 구조화된 dict로 변환한다.
    nutrition_table_found가 False면 LabelNotDetectedError를 발생시킨다.
    """
    if not GEMINI_API_KEY:
        raise ValueError("GEMINI_API_KEY가 .env 파일에 설정되어 있지 않습니다.")

    client = genai.Client(api_key=GEMINI_API_KEY)
    response = client.models.generate_content(
        model=MODEL_NAME,
        contents=_build_contents(image_base64),
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=GeminiLabelExtraction,
        ),
    )

    extraction = _parse_response(response.text)

    if not extraction.get("nutrition_table_found"):
        raise LabelNotDetectedError("이미지에서 영양성분표를 찾지 못했습니다.")

    return extraction
