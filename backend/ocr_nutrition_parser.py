"""
OCR 영양성분표 파싱/스케일링 로직.

Gemini Vision이 라벨에서 추출한 원시 필드(dict)를 받아, 기준량(basis) 대비
"1회 제공량(official serving)" 기준의 최종 당류/나트륨 값을 계산한다 — 총
내용량(전체 포장) 기준이 아니다. 실제로 몇 인분을 먹었는지는 이 모듈이 알 수
없으므로(사용자가 확인 화면에서 나중에 입력), 여기서는 항상 "1인분당" 값을
반환하고, 그 값에 인분수/그램을 곱하는 것은 호출 쪽(food_log.py의
serving_multiplier)의 책임이다.

import_dish_db.py의 _parse_weight_value/_compute_scale/_scale와 개념은 같지만
(1) 이쪽은 임포트 시점이 아닌 요청 시점 로직이고, (2) "1회 제공량 + 총 제공
횟수" 케이스가 추가로 있어 별도 모듈로 둔다.

핵심 원칙: 원본 값이 None이면 스케일 적용 여부와 무관하게 항상 None을 유지한다
(정보 없음 ≠ 0 원칙, README.md에 명시된 앱 전체의 불변 조건).
"""
from __future__ import annotations

import re

_LEADING_NUMBER_RE = re.compile(r"[-+]?\d+(?:\.\d+)?")

_VALID_METHODS = {
    "total_content",
    "per_basis_with_total",
    "per_serving_with_count",
    "unknown",
}


def parse_amount_value(value) -> float | None:
    """'100g'/'355 ml'/'100' 같은 문자열에서 선행 숫자만 추출한다.
    None/빈 문자열/숫자 없는 문자열 → None."""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    s = str(value).strip()
    if not s:
        return None
    match = _LEADING_NUMBER_RE.search(s)
    if not match:
        return None
    try:
        return float(match.group())
    except ValueError:
        return None


def compute_total_content_scale(basis_amount: float | None, target_amount: float | None) -> float | None:
    """기준량(basis_amount) 대비 target_amount의 배율. 총 내용량(package total)
    또는 1회 제공량(serving size) 어느 쪽에도 재사용되는 순수 비율 계산 —
    "기준량 대비 실제 양"이라는 개념 자체는 동일하기 때문이다.
    둘 중 하나라도 없거나 basis_amount가 0 이하면 계산 불가 (None)."""
    if basis_amount is None or target_amount is None or basis_amount <= 0:
        return None
    return target_amount / basis_amount


def scale_value(value: float | None, scale: float | None) -> float | None:
    """None-preserving 곱셈. value가 None이면 무조건 None, scale이 없으면 원본값 그대로."""
    if value is None or scale is None:
        return value
    return value * scale


def resolve_ocr_nutrients(extraction: dict) -> dict:
    """
    Gemini 추출 결과(dict)를 받아 최종 응답을 만든다.

    목표 값은 항상 "1회 제공량(official serving) 기준"이다 — 총 내용량(전체 포장)
    기준이 아니다. 사용자가 실제로 먹은 인분수/그램은 이후 확인 화면에서 입력받아
    이 값에 곱해진다 (food_log.py의 serving_multiplier, food_id 경로의 _multiply()와
    동일한 패턴).

    Gemini가 스스로 분류한 reference_amount_display_method를 신뢰하되,
    그 방식을 계산하는 데 필요한 값이 실제로는 빠져 있으면(예: per_basis_with_total로
    분류했는데 serving_size_g가 없음) scale_factor를 None으로 남긴다 — 라벨을
    읽었어도 1회 제공량이 실제로는 확정되지 않은 경우이기 때문. 이 경우
    needs_review=True이고, basis_amount_value는 있을 수 있으므로(예: "100g당") 확인
    화면에서 그램 직접 입력 대체 흐름을 제공할 수 있다.

    반환: {product_name, sugar_g, sodium_mg, scale_method, scale_factor_applied,
           basis_amount_value, needs_review}
    """
    declared_method = extraction.get("reference_amount_display_method")
    if declared_method not in _VALID_METHODS:
        declared_method = "unknown"

    sugar_raw = extraction.get("sugar_g_per_basis")
    sodium_raw = extraction.get("sodium_mg_per_basis")
    basis_amount = extraction.get("basis_amount_value")

    scale_method = declared_method
    scale_factor: float | None = None

    if declared_method == "total_content":
        # 1회 제공량 = 총 내용량이므로 이미 1회 제공량 기준 값이다.
        scale_factor = 1.0
    elif declared_method == "per_serving_with_count":
        # 값 자체가 이미 1회 제공량 기준으로 표기되어 있다 (servings_per_container는
        # 총 제공 횟수 표시용일 뿐, 스케일 계산에는 쓰이지 않는다).
        scale_factor = 1.0
    elif declared_method == "per_basis_with_total":
        serving_size_g = extraction.get("serving_size_g")
        scale_factor = compute_total_content_scale(basis_amount, serving_size_g)
    # declared_method == "unknown" → scale_factor stays None

    needs_review = scale_factor is None

    sugar_g = scale_value(sugar_raw, scale_factor)
    sodium_mg = scale_value(sodium_raw, scale_factor)

    return {
        "product_name": extraction.get("product_name"),
        "sugar_g": sugar_g,
        "sodium_mg": sodium_mg,
        "scale_method": scale_method,
        "scale_factor_applied": scale_factor,
        "basis_amount_value": basis_amount,
        "needs_review": needs_review,
    }
