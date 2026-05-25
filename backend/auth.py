import sqlite3
from fastapi import HTTPException
from backend.models import RegisterRequest, LoginRequest


def register_user(user: RegisterRequest, db: sqlite3.Connection):
    if user.password != user.password_confirm:
        raise HTTPException(status_code=400, detail="비밀번호가 일치하지 않습니다.")

    cursor = db.cursor()

    cursor.execute("SELECT user_id FROM users WHERE login_id = ?", (user.login_id,))
    if cursor.fetchone():
        raise HTTPException(status_code=400, detail="이미 사용 중인 아이디입니다.")

    cursor.execute("""
        INSERT INTO users (nickname, login_id, password)
        VALUES (?, ?, ?)
    """, (user.nickname, user.login_id, user.password))

    db.commit()

    return {
        "user_id": cursor.lastrowid,
        "nickname": user.nickname,
        "login_id": user.login_id,
        "message": "회원가입 완료"
    }


def login_user(user: LoginRequest, db: sqlite3.Connection):
    cursor = db.cursor()

    cursor.execute("""
        SELECT * FROM users
        WHERE login_id = ? AND password = ?
    """, (user.login_id, user.password))

    found_user = cursor.fetchone()

    if not found_user:
        raise HTTPException(status_code=401, detail="아이디 또는 비밀번호가 올바르지 않습니다.")

    return {
        "user_id": found_user["user_id"],
        "nickname": found_user["nickname"],
        "login_id": found_user["login_id"],
        "pregnancy_week": found_user["pregnancy_week"],
        "due_date": found_user["due_date"],
        "allergy_info": found_user["allergy_info"],
        "message": "로그인 성공"
    }