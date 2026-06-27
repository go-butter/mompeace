"""
backend/main.py 의 get_today_intake() 테스트.

핵심 검증 대상:
- 응답에 pregnancy_day, due_date, days_until_due 필드가 포함된다
- due_date가 미래로 설정되어 있으면 days_until_due는 양의 정수다
- due_date가 없으면 days_until_due는 None이다
"""
from backend.main import get_today_intake

from .conftest import make_user


def _seed_pregnancy_limit(db, trimester="middle"):
    db.execute(
        "INSERT INTO pregnancy_limits (trimester, caffeine_limit_mg, sugar_caution_g, sodium_caution_mg, note) "
        "VALUES (?, 200, 50, 2000, '')",
        (trimester,),
    )
    db.commit()


class TestGetTodayIntakeDueDate:
    def test_includes_due_date_fields_when_due_date_set(self, db):
        _seed_pregnancy_limit(db)
        user_id = make_user(db, due_date="2099-01-01")

        result = get_today_intake(user_id=user_id, db=db)

        assert "pregnancy_day" in result
        assert "due_date" in result
        assert "days_until_due" in result
        assert result["due_date"] == "2099-01-01"
        assert isinstance(result["days_until_due"], int)
        assert result["days_until_due"] > 0

    def test_days_until_due_is_none_when_due_date_not_set(self, db):
        _seed_pregnancy_limit(db)
        user_id = make_user(db, due_date=None)

        result = get_today_intake(user_id=user_id, db=db)

        assert result["due_date"] is None
        assert result["days_until_due"] is None
