"""
테스트용: caffeine_mg/sugar_g/sodium_mg가 전부 NULL("정보 없음")인
가상 음식을 food_items에 INSERT.

용도: FoodQR API가 막혀 있어 실제 바코드 스캔으로 NULL 영양소
음식을 재현할 수 없는 상황(주말 등)에서, "정보 없음" 음식을 먹었을
때의 전체 플로우(판정 로직 → food_log 저장 → 홈 화면 집계 →
unknown_*_count → status_label "정보없음" 표시)를 수동으로
검증하기 위해 작성.

생성된 food_id를 가지고 Swagger UI(/docs)에서
POST /food-log/from-food 호출 → 휴대폰 앱에서 결과 확인.

주의: 실행할 때마다 새 행이 INSERT됨 (중복 생성됨에 유의).
실행: mompeace 루트에서 `python insert_test_food.py`
"""

import sqlite3

conn = sqlite3.connect("mompeace.db")
cur = conn.cursor()

# caffeine_mg, sugar_g, sodium_mg 전부 NULL인 테스트 음식
# DEFAULT '0'이 있는 컬럼들이라, INSERT 문에 컬럼을 반드시 명시하고
# 값으로 None(NULL)을 직접 넘겨야 함 (컬럼을 생략하면 기본값 0이 들어가버림)
cur.execute("""
    INSERT INTO food_items
    (food_name, category, caffeine_mg, sugar_g, sodium_mg, calories_kcal, carbohydrate_g, protein_g, data_source)
    VALUES (?, ?, NULL, NULL, NULL, ?, ?, ?, ?)
""", ("테스트_영양정보없음", "snack", 150, 20, 3, "manual_test"))

conn.commit()

food_id = cur.lastrowid
print(f"생성된 food_id: {food_id}")

# 확인: 실제로 NULL로 들어갔는지 검증
cur.execute("SELECT food_id, food_name, caffeine_mg, sugar_g, sodium_mg FROM food_items WHERE food_id = ?", (food_id,))
row = cur.fetchone()
print("INSERT 결과:", row)
print("caffeine_mg is None:", row[2] is None)
print("sugar_g is None:", row[3] is None)
print("sodium_mg is None:", row[4] is None)

conn.close()
