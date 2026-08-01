"""
OCR 영양성분표 파싱/스케일링 로직.

Gemini Vision이 라벨에서 추출한 원시 필드(dict)를 받아, 기준량(basis) 대비
총 내용량(total)/1회 제공량 횟수(servings) 스케일을 적용한 최종 당류/나트륨
값을 계산한다. import_dish_db.py의 _parse_weight_value/_compute_scale/_scale와
개념은 같지만 (1) 이쪽은 임포트 시점이 아닌 요청 시점 로직이고, (2) "1회 제공량
+ 총 제공 횟수" 케이스가 추가로 있어 별도 모듈로 둔다.

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


def compute_total_content_scale(basis_amount: float | None, total_content: float | None) -> float | None:
    """기준량(basis_amount) 대비 총 내용량(total_content)의 배율.
    둘 중 하나라도 없거나 basis_amount가 0 이하면 계산 불가 (None)."""
    if basis_amount is None or total_content is None or basis_amount <= 0:
        return None
    return total_content / basis_amount


def scale_value(value: float | None, scale: float | None) -> float | None:
    """None-preserving 곱셈. value가 None이면 무조건 None, scale이 없으면 원본값 그대로."""
    if value is None or scale is None:
        return value
    return value * scale


def resolve_ocr_nutrients(extraction: dict) -> dict:
    """
    Gemini 추출 결과(dict)를 받아 최종 응답을 만든다.

    Gemini가 스스로 분류한 reference_amount_display_method를 신뢰하되,
    그 방식을 계산하는 데 필요한 값이 실제로는 빠져 있으면(예: per_basis_with_total로
    분류했는데 total_content_value가 없음) "unknown"으로 강등한다 — 라벨을
    읽었어도 스케일링 방식이 실제로는 확정되지 않은 경우이기 때문.

    반환: {product_name, sugar_g, sodium_mg, scale_method, scale_factor_applied, needs_review}
    """
    declared_method = extraction.get("reference_amount_display_method")
    if declared_method not in _VALID_METHODS:
        declared_method = "unknown"

    sugar_raw = extraction.get("sugar_g_per_basis")
    sodium_raw = extraction.get("sodium_mg_per_basis")

    scale_method = "unknown"
    scale_factor: float | None = None

    if declared_method == "total_content":
        scale_method = "total_content"
        scale_factor = 1.0
    elif declared_method == "per_basis_with_total":
        basis_amount = extraction.get("basis_amount_value")
        total_content = extraction.get("total_content_value")
        factor = compute_total_content_scale(basis_amount, total_content)
        if factor is not None:
            scale_method = "per_basis_with_total"
            scale_factor = factor
    elif declared_method == "per_serving_with_count":
        servings = extraction.get("servings_per_container")
        if servings is not None and servings > 0:
            scale_method = "per_serving_with_count"
            scale_factor = servings

    needs_review = scale_method == "unknown"

    sugar_g = sugar_raw if scale_method == "unknown" else scale_value(sugar_raw, scale_factor)
    sodium_mg = sodium_raw if scale_method == "unknown" else scale_value(sodium_raw, scale_factor)

    return {
        "product_name": extraction.get("product_name"),
        "sugar_g": sugar_g,
        "sodium_mg": sodium_mg,
        "scale_method": scale_method,
        "scale_factor_applied": scale_factor if scale_method != "unknown" else None,
        "needs_review": needs_review,
    }
