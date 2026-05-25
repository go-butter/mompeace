import sqlite3
import json


def list_to_text(value):
    """
    리스트 형태 데이터를 DB 저장용 문자열로 변환
    """
    if value is None:
        return None

    if isinstance(value, list):
        return ", ".join(str(item) for item in value)

    return str(value)


def list_to_json_text(value):
    """
    warnings처럼 긴 리스트는 JSON 문자열로 저장
    """
    if value is None:
        return None

    if isinstance(value, list):
        return json.dumps(value, ensure_ascii=False)

    return str(value)


def save_food_item(food_data: dict, source: str, db: sqlite3.Connection):
    """
    외부 API에서 정리한 식품 데이터를 food_items 테이블에 저장하거나 업데이트한다.

    사용 가능 source 예시:
    - food_qr
    - fallback
    - food_search_api

    같은 barcode가 있으면 barcode 기준으로 업데이트하고,
    barcode가 없으면 food_name + source 기준으로 중복을 확인한다.
    """

    if not food_data:
        return None

    barcode = food_data.get("barcode")
    food_name = food_data.get("food_name")

    if not food_name:
        return None

    cursor = db.cursor()

    food_code = food_data.get("food_code")
    food_name_en = food_data.get("food_name_en")
    category = (
        food_data.get("category")
        or food_data.get("food_category")
    )
    subcategory = (
        food_data.get("subcategory")
        or food_data.get("food_type")
    )

    serving_size_g = food_data.get("serving_size_g")
    serving_label = (
        food_data.get("serving_label")
        or food_data.get("serving_size")
    )

    caffeine_mg = food_data.get("caffeine_mg")          # None 허용 (정보 없음 ≠ 0)
    sugar_g = food_data.get("sugar_g", 0) or 0
    sodium_mg = food_data.get("sodium_mg", 0) or 0
    calories_kcal = food_data.get("calories_kcal", 0) or 0
    carbohydrate_g = food_data.get("carbohydrate_g")
    protein_g = food_data.get("protein_g")

    allergens = food_data.get("allergens") or food_data.get("allergen_info")
    allergen_info = list_to_text(allergens)

    additive_info = food_data.get("additive_info")

    warnings = food_data.get("warnings")
    notes = (
        food_data.get("notes")
        or list_to_json_text(warnings)
    )

    # 1. barcode가 있으면 barcode 기준으로 기존 데이터 확인
    if barcode:
        cursor.execute("""
            SELECT food_id
            FROM food_items
            WHERE barcode = ?
        """, (barcode,))
    else:
        # 2. barcode가 없으면 food_name + source 기준으로 확인
        cursor.execute("""
            SELECT food_id
            FROM food_items
            WHERE food_name = ? AND data_source = ?
        """, (food_name, source))

    existing = cursor.fetchone()

    if existing:
        food_id = existing["food_id"]

        cursor.execute("""
            UPDATE food_items
            SET
                food_code = ?,
                food_name = ?,
                food_name_en = ?,
                barcode = ?,
                category = ?,
                subcategory = ?,
                serving_size_g = ?,
                serving_label = ?,
                caffeine_mg = ?,
                sugar_g = ?,
                sodium_mg = ?,
                calories_kcal = ?,
                carbohydrate_g = ?,
                protein_g = ?,
                allergen_info = ?,
                additive_info = ?,
                data_source = ?,
                notes = ?,
                updated_at = datetime('now')
            WHERE food_id = ?
        """, (
            food_code,
            food_name,
            food_name_en,
            barcode,
            category,
            subcategory,
            serving_size_g,
            serving_label,
            caffeine_mg,
            sugar_g,
            sodium_mg,
            calories_kcal,
            carbohydrate_g,
            protein_g,
            allergen_info,
            additive_info,
            source,
            notes,
            food_id
        ))

    else:
        cursor.execute("""
            INSERT INTO food_items (
                food_code,
                food_name,
                food_name_en,
                barcode,
                category,
                subcategory,
                serving_size_g,
                serving_label,
                caffeine_mg,
                sugar_g,
                sodium_mg,
                calories_kcal,
                carbohydrate_g,
                protein_g,
                allergen_info,
                additive_info,
                data_source,
                notes
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            food_code,
            food_name,
            food_name_en,
            barcode,
            category,
            subcategory,
            serving_size_g,
            serving_label,
            caffeine_mg,
            sugar_g,
            sodium_mg,
            calories_kcal,
            carbohydrate_g,
            protein_g,
            allergen_info,
            additive_info,
            source,
            notes
        ))

        food_id = cursor.lastrowid

    db.commit()

    return food_id


def save_food_item_from_foodqr(food_data: dict, db: sqlite3.Connection):
    """
    기존 코드 호환용 함수.
    내부적으로는 공통 저장 함수 save_food_item을 사용한다.
    """

    return save_food_item(
        food_data=food_data,
        source="food_qr",
        db=db
    )