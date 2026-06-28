"""
디버그용: users 테이블 전체 조회 스크립트.

용도: login_id ↔ user_id 매핑을 빠르게 확인할 때 사용.
(예: Swagger에서 user_id를 지정해 API를 직접 호출해야 할 때,
실기기에서 로그인한 계정의 login_id가 어떤 user_id에 대응하는지 확인)

실행: mompeace 루트에서 `python check_users.py`
"""

import sqlite3

conn = sqlite3.connect("mompeace.db")
conn.row_factory = sqlite3.Row
cur = conn.cursor()

cur.execute("SELECT user_id, nickname, login_id FROM users")
for row in cur.fetchall():
    print(dict(row))

conn.close()
