"""
backend/routers/users.py 의 회원 탈퇴(DELETE /users/{user_id}) 테스트.

핵심 검증 대상:
- 비밀번호가 맞으면 users 와 사용자에 연결된 모든 자식 테이블 행이 삭제된다
  (users 뿐 아니라 food_log_extra_nutrients / food_log / water_log /
   user_food_items / user_sensitivity_log 까지 전부 비워지는지 확인)
- 존재하지 않는 user_id 는 404
- 비밀번호가 틀리면 401 이고, 아무것도 삭제되지 않는다
- 삭제는 호출한 본인 user_id 에만 스코프된다 (다른 사용자 데이터는 그대로)
"""
import bcrypt
import pytest
from fastapi import HTTPException

from backend.models import AccountDeleteRequest
from backend.routers.users import delete_user

from .conftest import make_food_log, make_user, make_user_food_item, make_water_log


PLAIN_PASSWORD = "correct-horse"


def _hash(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def _add_extra_nutrient(db, food_log_id):
    cursor = db.cursor()
    cursor.execute(
        "INSERT INTO food_log_extra_nutrients (food_log_id, name, value, unit) VALUES (?, ?, ?, ?)",
        (food_log_id, "엽산", "400", "mcg"),
    )
    db.commit()
    return cursor.lastrowid


def _add_sensitivity_log(db, user_id):
    cursor = db.cursor()
    cursor.execute(
        """
        INSERT INTO user_sensitivity_log (user_id, nutrient, old_adj, new_adj, trigger_reason)
        VALUES (?, ?, ?, ?, ?)
        """,
        (user_id, "caffeine", 0.0, 0.1, "test"),
    )
    db.commit()
    return cursor.lastrowid


def _seed_full_user(db, **user_overrides):
    """자식 테이블 5종에 모두 행이 있는 사용자 한 명을 만들고 관련 id들을 반환한다."""
    user_id = make_user(db, password=_hash(PLAIN_PASSWORD), **user_overrides)
    log_id = make_food_log(db, user_id)
    extra_id = _add_extra_nutrient(db, log_id)
    water_id = make_water_log(db, user_id)
    ufi_id = make_user_food_item(db, user_id)
    sens_id = _add_sensitivity_log(db, user_id)
    return {
        "user_id": user_id,
        "log_id": log_id,
        "extra_id": extra_id,
        "water_id": water_id,
        "ufi_id": ufi_id,
        "sens_id": sens_id,
    }


def _count(db, table, column, value):
    cursor = db.cursor()
    cursor.execute(f"SELECT COUNT(*) FROM {table} WHERE {column} = ?", (value,))
    return cursor.fetchone()[0]


class TestDeleteAccount:
    def test_success_removes_user_and_every_child_row(self, db):
        ids = _seed_full_user(db)
        user_id = ids["user_id"]

        result = delete_user(
            user_id=user_id,
            req=AccountDeleteRequest(password=PLAIN_PASSWORD),
            db=db,
        )

        assert result["message"] == "회원 탈퇴가 완료되었습니다."
        assert result["user_id"] == user_id

        # 부모 + 자식 테이블 전부 비어 있어야 한다 (users 만 확인하지 않는다).
        assert _count(db, "users", "user_id", user_id) == 0
        assert _count(db, "food_log", "user_id", user_id) == 0
        assert _count(db, "water_log", "user_id", user_id) == 0
        assert _count(db, "user_food_items", "user_id", user_id) == 0
        assert _count(db, "user_sensitivity_log", "user_id", user_id) == 0
        # food_log_extra_nutrients 는 user_id 가 없으므로 food_log_id 로 확인 —
        # 부모 food_log 를 지우기 전에 서브쿼리로 지워졌는지(고아 방지) 검증.
        assert _count(db, "food_log_extra_nutrients", "food_log_id", ids["log_id"]) == 0

    def test_nonexistent_user_raises_404(self, db):
        with pytest.raises(HTTPException) as exc_info:
            delete_user(
                user_id=999999,
                req=AccountDeleteRequest(password=PLAIN_PASSWORD),
                db=db,
            )
        assert exc_info.value.status_code == 404

    def test_wrong_password_raises_401_and_deletes_nothing(self, db):
        ids = _seed_full_user(db)
        user_id = ids["user_id"]

        with pytest.raises(HTTPException) as exc_info:
            delete_user(
                user_id=user_id,
                req=AccountDeleteRequest(password="wrong-password"),
                db=db,
            )
        assert exc_info.value.status_code == 401

        # 아무것도 지워지지 않았어야 한다.
        assert _count(db, "users", "user_id", user_id) == 1
        assert _count(db, "food_log", "user_id", user_id) == 1
        assert _count(db, "water_log", "user_id", user_id) == 1
        assert _count(db, "user_food_items", "user_id", user_id) == 1
        assert _count(db, "user_sensitivity_log", "user_id", user_id) == 1
        assert _count(db, "food_log_extra_nutrients", "food_log_id", ids["log_id"]) == 1

    def test_delete_is_scoped_to_target_user(self, db):
        victim = _seed_full_user(db)
        bystander = _seed_full_user(db, nickname="다른유저", login_id="other")

        delete_user(
            user_id=victim["user_id"],
            req=AccountDeleteRequest(password=PLAIN_PASSWORD),
            db=db,
        )

        # 다른 사용자의 데이터는 전부 그대로 남아 있어야 한다.
        other_id = bystander["user_id"]
        assert _count(db, "users", "user_id", other_id) == 1
        assert _count(db, "food_log", "user_id", other_id) == 1
        assert _count(db, "water_log", "user_id", other_id) == 1
        assert _count(db, "user_food_items", "user_id", other_id) == 1
        assert _count(db, "user_sensitivity_log", "user_id", other_id) == 1
        assert _count(db, "food_log_extra_nutrients", "food_log_id", bystander["log_id"]) == 1
