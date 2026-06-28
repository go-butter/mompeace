"""
디버그용: food_items 테이블 스키마(컬럼명, 타입, NOT NULL, DEFAULT 값)
조회 스크립트.

용도: 테스트 데이터를 INSERT하기 전에 DEFAULT 값이 걸린 컬럼이
있는지 미리 확인. 예: caffeine_mg/sugar_g/sodium_mg/calories_kcal는
DEFAULT '0'이 걸려 있어서, INSERT 문에서 컬럼을 생략하면 NULL이 아니라
자동으로 0이 들어가 버린다. NULL을 의도적으로 넣고 싶으면 컬럼을
반드시 명시하고 값으로 NULL을 직접 지정해야 한다.

실행: mompeace 루트에서 `python check_schema.py`
"""

import sqlite3

conn = sqlite3.connect("mompeace.db")
cur = conn.cursor()
cur.execute("PRAGMA table_info(food_items)")
for row in cur.fetchall():
    print(row)
