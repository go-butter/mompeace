"""
디버그용: food_log 특정 log_id 행의 판정 결과(recommendation_status,
reason_nutrient 등) 직접 조회 스크립트.

용도: API 응답에 판정 결과 필드가 안 보일 때, DB에 실제로 무엇이
저장됐는지 직접 확인하기 위함 (메모리 원칙: API 응답보다 DB 직접
검증 우선). log_id=19는 최초 NULL 영양소 테스트 시 사용한 값으로,
다른 log_id를 조회하려면 SQL의 WHERE log_id = 19 부분을 바꿔서 사용.

실행: mompeace 루트에서 `python check_log19.py`
"""

import sqlite3

conn = sqlite3.connect("mompeace.db")
conn.row_factory = sqlite3.Row
cur = conn.cursor()

cur.execute("""
    SELECT log_id, food_name, caffeine_mg, sugar_g, sodium_mg,
           recommendation_status, reason_nutrient, eaten_at
    FROM food_log
    WHERE log_id = 19
""")
row = cur.fetchone()
print(dict(row) if row else "log_id=19 없음")

conn.close()
