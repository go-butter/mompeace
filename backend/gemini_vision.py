"""
Gemini Vision 기반 영양성분표 OCR 추출.

역할은 "이미지 → 구조화된 필드 추출"에 한정된다 (분리의 원칙 — 안전 판정은
절대 하지 않음, intake_totals.py/recommendation_model.py 규칙 엔진이 전담). 카페인은
추출 대상에서 완전히 제외한다 (OCR 기능 자체의 범위 밖).

이미지 바이트는 이 모듈 함수 안에서만 잠깐 메모리에 존재하고, 디스크에 쓰거나
로그에 남기지 않는다 (최소 보유 원칙).

예외적으로, OCR_RAW_LOG_PATH가 설정된 경우에 한해 Gemini가 돌려준 JSON 응답
"원문 텍스트"는 파일에 남긴다 (기본값 없음 = 꺼짐). 이미지 바이트는 여전히 남기지
않으며, 남는 것은 추출된 텍스트뿐이다 — 다만 제품명이 디스크에 기록되므로
운영 환경에서 켜둘 용도가 아니라, 실제 오독 패턴을 관찰하기 위한 한시적 수단이다
(OCR_RAW_LOG_MAX회까지만 기록하고 그 뒤로는 조용히 멈춘다).
"""
from __future__ import annotations

import base64
import json
import os
from datetime import date, datetime
from typing import Literal, Optional

from dotenv import load_dotenv
from google import genai
from google.genai import types
from pydantic import AliasChoices, BaseModel, Field, field_validator

load_dotenv()

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

MODEL_NAME = "gemini-3.6-flash"

# 개발/테스트 중 실수로 반복 호출돼 과금되는 걸 막기 위한 하루 호출 상한.
# 서버 프로세스가 살아있는 동안만 유지되는 메모리 카운터 — 재시작하면 초기화된다
# (DB 테이블 없이도 충분한 수준의 안전장치이며, 이 이상의 영속성이 필요할 근거가 없다).
GEMINI_DAILY_CALL_LIMIT = int(os.getenv("GEMINI_DAILY_CALL_LIMIT", "30"))

_call_count_by_day: dict[str, int] = {}

# Gemini 응답 원문(JSON 텍스트) 기록 — 실제 라벨에서 어떤 식으로 잘못 읽는지
# 관찰하기 위한 한시적 수단이다. 경로가 없으면 아무것도 하지 않는다(기본 꺼짐).
# DB 테이블을 만들지 않는 이유: 이 데이터는 스키마를 정하기 위한 관찰용이지
# 앱이 읽는 상태가 아니라서, 스키마를 먼저 고정하면 순서가 뒤바뀐다.
OCR_RAW_LOG_PATH = os.getenv("OCR_RAW_LOG_PATH")
OCR_RAW_LOG_MAX = int(os.getenv("OCR_RAW_LOG_MAX", "10"))

_raw_log_count = 0

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
- basis_amount_unit: 기준량의 단위, "g" 또는 "ml" 중 하나로만 응답하세요 (예: "100g" → "g",
  "100ml" → "ml"). 확인할 수 없으면 "g"
- total_content_value: 총 내용량 숫자 (예: "355g" → 355). 없으면 null
- total_content_unit: 총 내용량의 단위, "g" 또는 "ml" 중 하나로만 응답하세요. 확인할 수 없으면 "g"
- servings_per_container: 총 제공 횟수 (예: "총 3회 제공량" → 3). 없으면 null
- serving_size_value: 1회 제공량이 그램(g)/밀리리터(ml)로 별도 표기되어 있으면 그 숫자
  (영양성분표의 기준이 100g/100ml이더라도, 라벨 어딘가에 "1회 제공량: 30g"처럼
  별도로 적혀 있으면 그 값). 없으면 null (0으로 추측하지 말 것)
- serving_size_unit: serving_size_value의 단위, "g" 또는 "ml" 중 하나로만 응답하세요.
  확인할 수 없으면 "g"
- carbohydrate_g_per_basis: 기준량 당 탄수화물(g). 읽을 수 없으면 null (0으로 추측하지 말 것)
- sugar_g_per_basis: 기준량 당 당류(g). 읽을 수 없으면 null (0으로 추측하지 말 것)
- energy_kcal_per_basis: 기준량 당 에너지/열량(kcal). 읽을 수 없으면 null (0으로 추측하지 말 것)
- fat_g_per_basis: 기준량 당 지방(g). 읽을 수 없으면 null (0으로 추측하지 말 것)
- iron_mg_per_basis: 기준량 당 철분(mg). 읽을 수 없으면 null (0으로 추측하지 말 것)
- protein_g_per_basis: 기준량 당 단백질(g). 읽을 수 없으면 null (0으로 추측하지 말 것)
- sodium_mg_per_basis: 기준량 당 나트륨(mg). 읽을 수 없으면 null (0으로 추측하지 말 것)

카페인 관련 필드는 추출하지 않습니다.
"""


# Gemini의 단위 표기는 대소문자/한글 표기가 일정하지 않다("mL"/"ML"/"밀리리터" 등) —
# Literal["g","ml"] 검증에 그대로 맡기면 스키마 검증 실패(502)로 스캔 전체가 죽는다.
# mode="before" 검증기로 알려진 변형을 정규화하고, 모르는 값은 예외를 던지는 대신
# "g"로 폴백한다 — 단위 오인식이 스캔 자체를 막아서는 안 된다는 원칙(라벨 값 자체의
# None-preserving 원칙과는 별개로, 단위는 항상 값이 있어야 하는 표시 전용 필드라
# "정보 없음"을 표현할 다른 방법이 없다).
_UNIT_NORMALIZATION = {
    "g": "g",
    "그램": "g",
    "ml": "ml",
    "밀리리터": "ml",
}


class GeminiLabelExtraction(BaseModel):
    product_name: Optional[str] = None
    nutrition_table_found: bool
    reference_amount_display_method: Literal[
        "total_content", "per_basis_with_total", "per_serving_with_count", "unknown"
    ] = "unknown"
    basis_amount_value: Optional[float] = None
    basis_amount_unit: Literal["g", "ml"] = "g"
    total_content_value: Optional[float] = None
    total_content_unit: Literal["g", "ml"] = "g"
    servings_per_container: Optional[float] = None
    # AliasChoices: 스키마 변경 전 이름(serving_size_g)으로 응답이 와도 같은 속성에
    # 매핑한다 — Gemini가 옛 이름을 계속 내보내면 이 필드가 조용히 None이 되고,
    # 그 결과 needs_review=True가 되어 7개 배지 전부가 "정보없음"으로 보인다(실제
    # OCR 실패와 시각적으로 구분되지 않음). 코드/프롬프트의 정식 이름은 항상
    # serving_size_value다.
    serving_size_value: Optional[float] = Field(
        default=None, validation_alias=AliasChoices("serving_size_value", "serving_size_g")
    )
    serving_size_unit: Literal["g", "ml"] = "g"
    carbohydrate_g_per_basis: Optional[float] = None
    sugar_g_per_basis: Optional[float] = None
    energy_kcal_per_basis: Optional[float] = None
    fat_g_per_basis: Optional[float] = None
    iron_mg_per_basis: Optional[float] = None
    protein_g_per_basis: Optional[float] = None
    sodium_mg_per_basis: Optional[float] = None

    @field_validator("basis_amount_unit", "total_content_unit", "serving_size_unit", mode="before")
    @classmethod
    def _normalize_unit(cls, value):
        if value is None:
            return "g"
        return _UNIT_NORMALIZATION.get(str(value).strip().lower(), "g")


class LabelNotDetectedError(Exception):
    """Gemini가 이미지에서 영양성분표 자체를 찾지 못한 경우.
    ("찾았지만 환산 방식이 불명확함"과는 다른 케이스 — 그쪽은 needs_review로 처리)"""


class GeminiNotConfiguredError(Exception):
    """GEMINI_API_KEY가 설정되어 있지 않은 경우.

    "우리 쪽 설정이 안 되어 있다"와 "Gemini 호출이 실패했다"는 사용자가 할 수 있는
    행동이 전혀 다르다(전자는 재촬영해도 소용없다) — routers/ocr.py가 502가 아닌
    503으로 구분해 응답한다."""


class GeminiDailyLimitExceededError(Exception):
    """하루 Gemini 호출 상한(GEMINI_DAILY_CALL_LIMIT)을 초과한 경우.
    개발/테스트 중 반복 호출로 인한 의도치 않은 과금을 막기 위한 안전장치 —
    routers/ocr.py가 다른 실패와 구분해 별도 응답(429)으로 처리한다."""


def _under_daily_limit() -> bool:
    today = date.today().isoformat()
    return _call_count_by_day.get(today, 0) < GEMINI_DAILY_CALL_LIMIT


def _record_call() -> None:
    today = date.today().isoformat()
    _call_count_by_day[today] = _call_count_by_day.get(today, 0) + 1


def _append_raw_log(raw_text: str) -> None:
    """Gemini 응답 원문을 JSONL 한 줄로 덧붙인다. OCR_RAW_LOG_PATH가 없으면 no-op.

    기록 실패(경로 없음/권한 없음 등)는 조용히 삼킨다 — 관찰용 부가 기능이 스캔
    자체를 막아서는 안 된다. 상한(OCR_RAW_LOG_MAX)은 실제로 기록에 성공한 횟수로만
    센다. 프로세스 메모리 카운터이므로 재시작하면 다시 0부터 센다 — 하루 호출
    상한(_call_count_by_day)과 같은 수준의 장치이며, 그 이상의 영속성이 필요할
    근거가 없다.
    """
    global _raw_log_count
    if not OCR_RAW_LOG_PATH or _raw_log_count >= OCR_RAW_LOG_MAX:
        return
    record = {
        "ts": datetime.now().isoformat(timespec="seconds"),
        "model": MODEL_NAME,
        "raw_text": raw_text,
    }
    try:
        with open(OCR_RAW_LOG_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
    except OSError:
        return
    _raw_log_count += 1


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
        raise GeminiNotConfiguredError("GEMINI_API_KEY가 .env 파일에 설정되어 있지 않습니다.")
    if not _under_daily_limit():
        raise GeminiDailyLimitExceededError(
            f"하루 Gemini 호출 상한({GEMINI_DAILY_CALL_LIMIT}회)을 초과했습니다."
        )

    client = genai.Client(api_key=GEMINI_API_KEY)
    _record_call()
    response = client.models.generate_content(
        model=MODEL_NAME,
        contents=_build_contents(image_base64),
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=GeminiLabelExtraction,
        ),
    )

    # 파싱 "전에" 원문을 남긴다. _parse_response가 ValidationError를 던지면
    # (routers/ocr.py에서 502가 되며) 응답 본문이 그대로 사라지는데, 실제 오독
    # 패턴을 보려면 바로 그 케이스가 가장 필요하다. _append_raw_log는 내부에서
    # 예외를 삼키므로 기록 실패가 스캔을 막지 않는다.
    raw_text = response.text
    _append_raw_log(raw_text)
    extraction = _parse_response(raw_text)

    if not extraction.get("nutrition_table_found"):
        raise LabelNotDetectedError("이미지에서 영양성분표를 찾지 못했습니다.")

    return extraction
