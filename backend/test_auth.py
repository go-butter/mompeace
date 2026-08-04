"""
회원가입/로그인 (nickname/login_id 유일성, 로그인 아이디-or-닉네임 매칭) 테스트.

핵심 검증 대상:
- nickname, login_id 각각 중복 가입 거부
- 신규 nickname이 기존 login_id와 겹치는 경우 / 신규 login_id가 기존 nickname과
  겹치는 경우(교차 충돌) 모두 거부
- 로그인은 login_id 또는 nickname 어느 쪽으로도 가능
- 매칭되는 계정이 없으면 401
"""
import pytest
from fastapi import HTTPException

from backend.auth import register_user, login_user
from backend.models import RegisterRequest, LoginRequest

from .conftest import make_user


def _register(db, **overrides):
    defaults = {
        "nickname": "테스트유저",
        "login_id": "tester1",
        "password": "pw1234",
        "password_confirm": "pw1234",
    }
    defaults.update(overrides)
    return register_user(RegisterRequest(**defaults), db)


class TestRegisterUniqueness:
    def test_duplicate_nickname_rejected(self, db):
        _register(db, nickname="중복닉네임", login_id="userA")

        with pytest.raises(HTTPException) as exc_info:
            _register(db, nickname="중복닉네임", login_id="userB")
        assert exc_info.value.status_code == 400

    def test_duplicate_login_id_rejected(self, db):
        _register(db, nickname="유저에이", login_id="dupid")

        with pytest.raises(HTTPException) as exc_info:
            _register(db, nickname="유저비", login_id="dupid")
        assert exc_info.value.status_code == 400

    def test_new_nickname_colliding_with_existing_login_id_rejected(self, db):
        _register(db, nickname="유저에이", login_id="crossid")

        with pytest.raises(HTTPException) as exc_info:
            _register(db, nickname="crossid", login_id="userb")
        assert exc_info.value.status_code == 400

    def test_new_login_id_colliding_with_existing_nickname_rejected(self, db):
        _register(db, nickname="크로스닉", login_id="usera")

        with pytest.raises(HTTPException) as exc_info:
            _register(db, nickname="유저비", login_id="크로스닉")
        assert exc_info.value.status_code == 400


class TestLoginMatchesEitherField:
    def test_login_via_login_id(self, db):
        _register(db, nickname="아이디로그인유저", login_id="loginidtest")

        result = login_user(LoginRequest(login_id="loginidtest", password="pw1234"), db)
        assert result["login_id"] == "loginidtest"
        assert result["nickname"] == "아이디로그인유저"

    def test_login_via_nickname(self, db):
        _register(db, nickname="닉네임로그인유저", login_id="nicktest")

        result = login_user(LoginRequest(login_id="닉네임로그인유저", password="pw1234"), db)
        assert result["nickname"] == "닉네임로그인유저"
        assert result["login_id"] == "nicktest"

    def test_login_with_no_match_returns_401(self, db):
        with pytest.raises(HTTPException) as exc_info:
            login_user(LoginRequest(login_id="nosuchuser", password="pw1234"), db)
        assert exc_info.value.status_code == 401
