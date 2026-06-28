import sqlite3

from fastapi import APIRouter, Depends

from backend.database import get_db
from backend.models import RegisterRequest, LoginRequest
from backend.auth import register_user, login_user

router = APIRouter()


@router.post("/auth/register")
def register(
    user: RegisterRequest,
    db: sqlite3.Connection = Depends(get_db)
):
    """회원가입"""
    return register_user(user, db)


@router.post("/auth/login")
def login(
    user: LoginRequest,
    db: sqlite3.Connection = Depends(get_db)
):
    """로그인"""
    return login_user(user, db)
