"""
테스트용: caffeine_mg/sugar_g/sodium_mg가 전부 "확인된 0"
(정보 없음이 아니라 실제로 무카페인/무가당/무나트륨)인 가상 음식을
food_items에 INSERT.

용도: insert_test_food.py(NULL 케이스)와 짝을 이루는 대조군.
"정보 없음(NULL)"과 "확인된 0"이 status_label에서 각각
"정보없음" / "여유"로 다르게 표시되는지 구분 검증하기 위해 작성.
(둘 다 같은 "0"으로 처리되면 안 된다는 설계 원칙의 핵심 테스트 케이스)

실행: mompeace 루트에서 `python insert_confirmed_zero_food.py`
"""

import sqlite3

conn = sqlite3.connect("mompeace.db")
cur = conn.cursor()

# 비교용: 확인된 0 (실제로 무카페인/무가당/무나트륨) 음식
cur.execute("""
    INSERT INTO food_items
    (food_name, category, caffeine_mg, sugar_g, sodium_mg, calories_kcal, carbohydrate_g, protein_g, data_source)
    VALUES (?, ?, 0, 0, 0, ?, ?, ?, ?)
""", ("테스트_확인된무함량", "snack", 50, 5, 1, "manual_test"))

conn.commit()
food_id = cur.lastrowid
print(f"확인된 0 테스트 음식 food_id: {food_id}")

cur.execute("SELECT food_id, food_name, caffeine_mg, sugar_g, sodium_mg FROM food_items WHERE food_id = ?", (food_id,))
print(cur.fetchone())

conn.close()
