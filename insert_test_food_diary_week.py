"""
테스트용: Food Diary 캘린더 점(dot) 색상 검증을 위해 최근 7일에 걸쳐
safe/caution/avoid/unknown 상태가 섞인 food_log 데이터를 INSERT.

용도: 24시간 지나 기존 테스트 데이터가 "오늘" 범위에서 벗어나면서
캘린더/날짜별 조회 화면을 시각적으로 확인할 데이터가 사라짐.
실제 트라이미스터별 한도(caffeine_mg)를 기준으로 의도적으로
하루씩 다른 등급이 나오게 양을 조절해서 넣음.

주의: 실행할 때마다 새 행이 INSERT됨 (중복 생성됨에 유의).
재실행 전 정리하려면 clear_food_log.py 사용 권장.

실행: mompeace 루트에서 `python insert_test_food_diary_week.py`
"""

import sqlite3
from datetime import datetime, timedelta

conn = sqlite3.connect("mompeace.db")
conn.row_factory = sqlite3.Row
cur = conn.cursor()

# user_id 직접 지정 (로그인 계정 확인됨: user_id=2)
TARGET_USER_ID = 2

cur.execute("SELECT user_id, pregnancy_week FROM users WHERE user_id = ?", (TARGET_USER_ID,))
user_row = cur.fetchone()
if user_row is None:
    raise SystemExit(f"user_id={TARGET_USER_ID} 가 users 테이블에 없음 — TARGET_USER_ID 값을 확인하세요.")

user_id = user_row["user_id"]
pregnancy_week = user_row["pregnancy_week"]
print(f"대상 user_id: {user_id} (pregnancy_week={pregnancy_week})")

# 트라이미스터별 카페인 한도(mg) — main.py/intake_totals.py와 동일한 기준치 참고용.
# 임신 전체 기간 공통 ACOG 한도는 200mg/day. 이 스크립트는 그 기준선만 사용.
CAFFEINE_LIMIT = 200

today = datetime.now()

# (일자 오프셋, 라벨, food_name, caffeine_mg, sugar_g, sodium_mg)
# caffeine_mg=None 인 행은 "정보없음(unknown)" 상태를 재현.
plan = [
    (0, "safe",    "오늘_디카페인라떼",      20,   10,  50),
    (-1, "caution", "어제_아메리카노2잔",     180,  15,  80),
    (-2, "avoid",   "이틀전_에너지드링크",    320,  40, 100),
    (-3, "safe",    "3일전_보리차",           5,    5,  20),
    (-4, "unknown", "4일전_정체불명_음료",   None,  None, None),
    (-5, "caution", "5일전_초콜릿라떼",       150,  35,  60),
    (-6, "safe",    "6일전_생수",             0,    0,   5),
]

inserted = []
for offset, label, name, caffeine, sugar, sodium in plan:
    eaten_at = (today + timedelta(days=offset)).strftime("%Y-%m-%d 09:00:00")
    cur.execute(
        """
        INSERT INTO food_log
        (user_id, food_name, category, input_type,
         caffeine_mg, sugar_g, sodium_mg, calories_kcal, carbohydrate_g, protein_g,
         risk_level, eaten_at)
        VALUES (?, ?, 'test', 'manual_test', ?, ?, ?, 100, 10, 1, ?, ?)
        """,
        (user_id, name, caffeine, sugar, sodium, label, eaten_at),
    )
    inserted.append((cur.lastrowid, label, name, eaten_at))

conn.commit()

print("\nINSERT 완료:")
for log_id, label, name, eaten_at in inserted:
    print(f"  log_id={log_id:<4} [{label:<8}] {name:<20} eaten_at={eaten_at}")

# 검증: 실제로 저장된 값 재조회
print("\n저장 확인:")
cur.execute(
    "SELECT log_id, food_name, caffeine_mg, sugar_g, sodium_mg, eaten_at "
    "FROM food_log WHERE log_id IN ({})".format(
        ",".join(str(r[0]) for r in inserted)
    )
)
for row in cur.fetchall():
    print(dict(row))

conn.close()

print(
    "\n참고: caution/avoid 등급은 caffeine_mg 기준으로만 의도해서 양을 잡았습니다 "
    f"(한도 {CAFFEINE_LIMIT}mg 기준 참고치이며, 실제 overall_status는 백엔드의 "
    "트라이미스터별 sugar/sodium 한도까지 종합 판정하므로 캘린더에서 보이는 색이 "
    "위 라벨과 정확히 일치하지 않을 수 있습니다 — 다르면 그것도 정상 동작 확인의 "
    "일부입니다.)"
)
