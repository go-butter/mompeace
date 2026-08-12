"""
OCR 스캔 품목이 위험(avoid) 판정을 받았을 때, 같은 subcategory 안에서 그 원인이 된
특정 영양소 기준으로 정렬한 대체 후보를 찾는다. trigger nutrient 결정은 순수 함수
(nutrient_statuses 리스트만 있으면 됨)라 라우터/분류 로직과 독립적으로 테스트하기
쉽고, 후보 조회는 food_items 조회라는 별개의 관심사라 분리해 둔다.
"""
from __future__ import annotations

import sqlite3
from typing import Optional

from backend.nutrition_constants import NUTRIENT_STATUS_TYPE

_ALLOWED_SOURCE = "dish_db_download"

# carbohydrate/energy/protein(floor 타입)은 단일 품목 판정에서 항상 "unknown"이라
# 절대 avoid가 될 수 없다 (intake_totals.get_item_nutrient_status 참고) — 그래서
# 이 4개만 실제 trigger 후보이자, food_items에 그대로 존재하는 정렬 기준 컬럼이다.
_NUTRIENT_TO_COLUMN = {
    "sugar": "sugar_g",
    "fat": "fat_g",
    "iron": "iron_mg",
    "sodium": "sodium_mg",
}


def determine_trigger_nutrient(nutrient_statuses: list[dict]) -> Optional[str]:
    """avoid 상태인 영양소가 여러 개 동시에 있을 수 있으므로, nutrition_constants
    .NUTRIENT_STATUS_TYPE에 이미 선언된 순서(carbohydrate, sugar, energy, fat, iron,
    protein, sodium)를 그대로 우선순위로 재사용한다 — 새 우선순위 규칙을 만들지 않고
    기존에 존재하는 정식 순서를 따른다. 결과적으로 sugar > fat > iron > sodium 순.
    avoid인 영양소가 하나도 없으면 None.
    """
    statuses_by_key = {item["key"]: item["status"] for item in nutrient_statuses}
    for key in NUTRIENT_STATUS_TYPE:
        if key in _NUTRIENT_TO_COLUMN and statuses_by_key.get(key) == "avoid":
            return key
    return None


def find_subcategory_alternatives(
    db: sqlite3.Connection,
    subcategory: str,
    trigger_nutrient: str,
    limit: int = 5,
) -> list[dict]:
    """같은 subcategory(dish_db_download 한정) 안에서 trigger_nutrient 값이 낮은
    순서로 후보를 찾는다.

    trigger_nutrient 컬럼이 NULL인 행은 명시적으로 제외한다 — SQLite는 ASC 정렬 시
    NULL을 가장 작은 값으로 취급해 맨 앞에 놓으므로, 이 가드가 없으면 정보가 없는
    행이 "가장 좋은 대안"으로 잘못 표시된다.
    """
    if trigger_nutrient not in _NUTRIENT_TO_COLUMN:
        raise ValueError(f"정렬 기준으로 사용할 수 없는 영양소입니다: {trigger_nutrient}")

    column = _NUTRIENT_TO_COLUMN[trigger_nutrient]
    cursor = db.cursor()
    cursor.execute(
        f"SELECT food_id, food_name, subcategory, sugar_g, sodium_mg, fat_g, iron_mg, calories_kcal "
        f"FROM food_items "
        f"WHERE data_source = ? AND subcategory = ? AND {column} IS NOT NULL "
        f"ORDER BY {column} ASC "
        f"LIMIT ?",
        (_ALLOWED_SOURCE, subcategory, limit),
    )
    return [dict(row) for row in cursor.fetchall()]
