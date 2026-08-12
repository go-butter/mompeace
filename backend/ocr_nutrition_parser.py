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

import math
import re

_LEADING_NUMBER_RE = re.compile(r"[-+]?\d+(?:\.\d+)?")

_VALID_METHODS = {
    "total_content",
    "per_basis_with_total",
    "per_serving_with_count",
    "unknown",
}

# 추적 대상 7개 영양소 키(nutrition_constants.NUTRIENT_LABELS_KO와 동일한 키)를
# GeminiLabelExtraction의 필드명으로 매핑한다 — resolve_ocr_nutrients()가 이 매핑을
# 따라 7개 전부를 동일한 방식으로 스케일링한다.
_NUTRIENT_EXTRACTION_FIELDS = {
    "carbohydrate": "carbohydrate_g_per_basis",
    "sugar": "sugar_g_per_basis",
    "energy": "energy_kcal_per_basis",
    "fat": "fat_g_per_basis",
    "iron": "iron_mg_per_basis",
    "protein": "protein_g_per_basis",
    "sodium": "sodium_mg_per_basis",
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


def truncate_to_places(value: float | None, places: int = 2) -> float | None:
    """None-preserving 절사(truncate-toward-zero). round()과 달리 반올림하지 않는다.

    이 앱의 영양소 값/기준량은 항상 0 이상이므로 절사(0 방향)와 내림(음의 무한대
    방향)이 결과적으로 같지만, "절사"의 정확한 의미는 0 방향이므로 math.trunc를
    쓴다 — round()를 재사용하는 food_log.py의 _multiply()와는 의도적으로 다른 함수다.
    """
    if value is None:
        return None
    factor = 10 ** places
    return math.trunc(value * factor) / factor


def compute_total_content_value(
    basis_value: float | None,
    basis_amount: float | None,
    total_content_amount: float | None,
    places: int = 2,
) -> float | None:
    """기준량(basis_amount)당 basis_value를 총 내용량(total_content_amount) 기준으로
    환산 후 절사한다. compute_total_content_scale()을 그대로 재사용 — 1회 제공량
    스케일(scale_factor)과는 완전히 독립적인 계산이므로, needs_review 여부와 무관하게
    (1회 제공량을 몰라도) 항상 계산 가능하다.

    scale_value()와 달리 scale이 None이면(기준량/총 내용량 중 하나라도 없으면)
    basis_value를 그대로 통과시키지 않고 None을 반환한다 — resolve_ocr_nutrients()의
    1회 제공량 스케일에는 needs_review 플래그가 있어 "raw passthrough"임을 호출 측이
    알 수 있지만, 이 total_value에는 그런 플래그가 없다. scale 없이 passthrough하면
    100g당 값을 총 내용량 값인 것처럼 잘못 표시하게 되어(둘의 실제 비율은 모르는
    채로) 정보 없음보다 더 나쁜, 조용히 틀린 값이 된다.
    """
    scale = compute_total_content_scale(basis_amount, total_content_amount)
    if scale is None:
        return None
    return truncate_to_places(scale_value(basis_value, scale), places)


def resolve_ocr_nutrients(extraction: dict) -> dict:
    """
    Gemini 추출 결과(dict)를 받아 최종 응답을 만든다. 목표 값은 항상 "1회 제공량
    (official serving) 기준"이다 (이유는 모듈 docstring 참고).

    Gemini가 스스로 분류한 reference_amount_display_method를 신뢰하되, 그 방식을
    계산하는 데 필요한 값이 실제로는 빠져 있으면 scale_factor를 None으로 남기고
    needs_review=True로 둔다 — 라벨을 읽었어도 1회 제공량이 확정되지 않은 경우이기
    때문. total_value는 scale_factor와 무관하게 계산되므로 이때도 항상 값이 있다.

    기존 sugar_g/sodium_mg는 nutrients["sugar"/"sodium"]["serving_value"]와 같은
    값을 유지하고(기존 소비자와의 하위 호환), 단위 기본값 "g"는 이 함수가 테스트 등
    에서 raw dict를 직접 받기도 하므로 여기서도 방어적으로 채운다.
    """
    declared_method = extraction.get("reference_amount_display_method")
    if declared_method not in _VALID_METHODS:
        declared_method = "unknown"

    basis_amount = extraction.get("basis_amount_value")
    basis_amount_unit = extraction.get("basis_amount_unit") or "g"
    total_content_amount = extraction.get("total_content_value")
    total_content_unit = extraction.get("total_content_unit") or "g"
    serving_size_unit = extraction.get("serving_size_unit") or "g"

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
        serving_size_value = extraction.get("serving_size_value")
        scale_factor = compute_total_content_scale(basis_amount, serving_size_value)
    # declared_method == "unknown" → scale_factor stays None

    needs_review = scale_factor is None

    nutrients: dict[str, dict] = {}
    for key, field_name in _NUTRIENT_EXTRACTION_FIELDS.items():
        basis_value = extraction.get(field_name)
        nutrients[key] = {
            "basis_value": basis_value,
            "serving_value": scale_value(basis_value, scale_factor),
            "total_value": compute_total_content_value(basis_value, basis_amount, total_content_amount),
        }

    return {
        "product_name": extraction.get("product_name"),
        "sugar_g": nutrients["sugar"]["serving_value"],
        "sodium_mg": nutrients["sodium"]["serving_value"],
        "scale_method": scale_method,
        "scale_factor_applied": scale_factor,
        "basis_amount_value": basis_amount,
        "basis_amount_unit": basis_amount_unit,
        "total_content_value": total_content_amount,
        "total_content_unit": total_content_unit,
        "serving_size_unit": serving_size_unit,
        "needs_review": needs_review,
        "nutrients": nutrients,
    }
