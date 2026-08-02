"""
One-time backfill: round already-stored dish_db_download nutrient columns to 2 decimals.

_scale() in import_dish_db.py now rounds after multiplying, but rows imported before
that fix still carry floating-point noise (e.g. 405.59999999999997). This script cleans
up existing rows in place — pure float rounding, no semantic value change, so it's safe
to run against the live DB (unlike the earlier T/B ratio scaling fix).

실행 방법:
    python -m backend.scripts.round_food_items
"""
from __future__ import annotations
import sqlite3

from backend.import_dish_db import DB_PATH

DATA_SOURCE = "dish_db_download"

NUMERIC_COLUMNS = [
    "calories_kcal", "fat_g", "sugar_g", "sodium_mg", "carbohydrate_g", "protein_g",
]


def main():
    conn = sqlite3.connect(str(DB_PATH))
    cursor = conn.cursor()

    set_clause = ", ".join(f"{col} = ROUND({col}, 2)" for col in NUMERIC_COLUMNS)
    cursor.execute(
        f"UPDATE food_items SET {set_clause} WHERE data_source = ?",
        (DATA_SOURCE,),
    )
    updated = cursor.rowcount

    conn.commit()
    conn.close()

    print(f"rounded rows: {updated}")
    print("✅ dish_db_download 소수점 정리 완료")


if __name__ == "__main__":
    main()
