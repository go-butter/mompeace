"""
테스트용: food_log 테이블만 비우는 스크립트 (users, food_items는 보존).

용도: 테스트 음식(insert_test_food.py, insert_confirmed_zero_food.py 등)을
기록했다가 화면을 깨끗한 상태에서 다시 확인하고 싶을 때 사용.
계정(users)이나 등록된 테스트 음식(food_items)은 지우지 않으므로
재로그인이나 재생성 없이 반복 테스트 가능.

주의: 운영 데이터가 들어있는 DB에는 절대 실행하지 말 것 — 모든
사용자의 모든 섭취 기록이 삭제됨.

실행: mompeace 루트에서 `python clear_food_log.py`
"""

import sqlite3

conn = sqlite3.connect("mompeace.db")
cur = conn.cursor()

# 삭제 전 개수 확인
cur.execute("SELECT COUNT(*) FROM food_log")
before = cur.fetchone()[0]
print(f"삭제 전 food_log 행 수: {before}")

# food_log만 비움 (users, food_items는 그대로 유지)
cur.execute("DELETE FROM food_log")
conn.commit()

cur.execute("SELECT COUNT(*) FROM food_log")
after = cur.fetchone()[0]
print(f"삭제 후 food_log 행 수: {after}")

# food_items는 보존됐는지 확인 (테스트 음식 포함)
cur.execute("SELECT food_id, food_name FROM food_items")
print("food_items 보존 확인:", cur.fetchall())

conn.close()
print("✅ food_log 초기화 완료")
