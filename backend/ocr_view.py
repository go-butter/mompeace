"""
OCR 확인 화면이 쓰는 뷰 모델 조립.

/ocr/scan과 /ocr/recompute가 정확히 같은 모양의 판정 결과를 돌려주도록 두
엔드포인트가 공유하는 단 하나의 진입점이다 — 한쪽만 고쳐서 화면이 스캔 직후와
편집 직후에 다른 규칙으로 판정되는 일을 구조적으로 막는다.

판정 자체는 전부 intake_totals.py(룰 엔진)가 한다. 이 모듈은 "누구의 하루인지,
어떤 날짜인지"를 결정해 넘기고 결과를 묶기만 한다 — 임계값이나 판정 분기를
여기에 두지 않는다.
"""
from __future__ import annotations

import sqlite3
from datetime import date

from backend.intake_totals import (
    build_daily_projected_statuses,
    fetch_daily_nutrient_totals,
    get_trimester_limits,
    resolve_user_nutrition_context,
    select_headline_nutrient,
)
from backend.nutrition_constants import parse_selected_nutrients


def build_ocr_status_view(
    pending_values: dict[str, float | None],
    user: dict,
    db: sqlite3.Connection,
    target_date: str | None = None,
) -> dict:
    """"오늘 누적 + 지금 확인 중인 품목" 기준 8개 영양소 상태 + 헤드라인.

    pending_values: 확인 화면에 현재 떠 있는 값 전체. OCR이 읽지 못했거나 사용자가
      비워둔 영양소는 None이어야 한다(정보 없음 ≠ 0). 카페인처럼 라벨에서 절대
      추출할 수 없는 항목도 None으로 넣으면 오늘 누적분만으로 판정된다.

    target_date: 기본값은 서버 로컬 기준 오늘(date.today()). /intake/summary가
      하루 경계를 정하는 방식과 정확히 동일해야 자정 무렵에 확인 화면과 요약
      화면의 "오늘"이 어긋나지 않는다 — 그쪽도 date.today() + DATE(eaten_at)
      문자열 비교를 쓴다.
    """
    week, age_bracket = resolve_user_nutrition_context(user)
    _, limits = get_trimester_limits(week, age_bracket)

    day = target_date or date.today().isoformat()
    daily_totals = fetch_daily_nutrient_totals(user["user_id"], day, db)

    statuses = build_daily_projected_statuses(pending_values, daily_totals, limits)
    preferred_keys = parse_selected_nutrients(user.get("selected_nutrients"))

    return {
        "nutrient_statuses": statuses,
        "headline": select_headline_nutrient(statuses, preferred_keys),
    }
