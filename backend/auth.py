import sqlite3
import bcrypt
from fastapi import HTTPException
from backend.models import RegisterRequest, LoginRequest
from backend.nutrition_constants import validate_selected_nutrients


def register_user(user: RegisterRequest, db: sqlite3.Connection):
    if user.password != user.password_confirm:
        raise HTTPException(status_code=400, detail="비밀번호가 일치하지 않습니다.")

    normalized_login_id = user.login_id.strip().lower()

    cursor = db.cursor()

    cursor.execute("SELECT user_id FROM users WHERE nickname = ?", (user.nickname,))
    if cursor.fetchone():
        raise HTTPException(status_code=400, detail={"field": "nickname", "message": "이미 사용 중인 닉네임입니다."})

    cursor.execute("SELECT user_id FROM users WHERE login_id = ?", (normalized_login_id,))
    if cursor.fetchone():
        raise HTTPException(status_code=400, detail={"field": "login_id", "message": "이미 사용 중인 아이디입니다."})

    cursor.execute("SELECT user_id FROM users WHERE login_id = ?", (user.nickname.strip().lower(),))
    if cursor.fetchone():
        raise HTTPException(status_code=400, detail={"field": "nickname", "message": "이미 다른 사용자의 아이디로 사용 중인 닉네임입니다."})

    cursor.execute("SELECT user_id FROM users WHERE nickname = ?", (normalized_login_id,))
    if cursor.fetchone():
        raise HTTPException(status_code=400, detail={"field": "login_id", "message": "이미 다른 사용자의 닉네임으로 사용 중인 아이디입니다."})

    try:
        selected_nutrients_value = validate_selected_nutrients(user.selected_nutrients)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    password_hash = bcrypt.hashpw(user.password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")

    try:
        cursor.execute("""
            INSERT INTO users (nickname, login_id, password, selected_nutrients)
            VALUES (?, ?, ?, ?)
        """, (user.nickname, normalized_login_id, password_hash, selected_nutrients_value))
        db.commit()
    except sqlite3.IntegrityError:
        raise HTTPException(status_code=400, detail="이미 사용 중인 닉네임 또는 아이디입니다.")

    return {
        "user_id": cursor.lastrowid,
        "nickname": user.nickname,
        "login_id": normalized_login_id,
        "message": "회원가입 완료"
    }


def login_user(user: LoginRequest, db: sqlite3.Connection):
    normalized_login_id = user.login_id.strip().lower()

    cursor = db.cursor()

    cursor.execute("""
        SELECT * FROM users
        WHERE login_id = ? OR nickname = ?
    """, (normalized_login_id, user.login_id.strip()))

    found_user = cursor.fetchone()

    stored_hash = found_user["password"] or "" if found_user else ""
    password_ok = bcrypt.checkpw(user.password.encode("utf-8"), stored_hash.encode("utf-8")) if found_user else False

    if not found_user or not password_ok:
        raise HTTPException(status_code=401, detail="아이디 또는 비밀번호가 올바르지 않습니다.")

    return {
        "user_id": found_user["user_id"],
        "nickname": found_user["nickname"],
        "login_id": found_user["login_id"],
        "pregnancy_week": found_user["pregnancy_week"],
        "due_date": found_user["due_date"],
        "message": "로그인 성공"
    }