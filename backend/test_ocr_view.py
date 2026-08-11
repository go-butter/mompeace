"""
backend/ocr_view.py::build_ocr_status_view() 테스트.

intake_totals.py의 순수 함수 단위 테스트(test_intake_totals.py)와 달리, 여기서는
실제 users/food_log 행을 심어 "사용자 컨텍스트 조회 -> 하루 누적 집계 -> 판정 ->
헤드라인 선택"까지의 결합을 검증한다.

핵심 검증 대상:
- 같은 품목이라도 그날 이미 먹은 양에 따라 판정이 달라진다 (일일 투영의 존재 이유)
- 카페인은 사용자가 아무것도 입력하지 않아도 오늘 누적분으로 판정된다
- 관심성분(users.selected_nutrients)이 같은 심각도 안에서 헤드라인 우선권을 갖는다
- 하한형/밴드형 하한 미달은 헤드라인이 되지 않는다
- 하루 경계는 서버 로컬 날짜 기준이며 다른 날짜의 기록은 섞이지 않는다
"""
from datetime import date

import pytest

from backend.ocr_view import build_ocr_status_view

from .conftest import make_food_log, make_user


def _user_row(db, user_id: int) -> dict:
    cursor = db.cursor()
    cursor.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
    return dict(cursor.fetchone())


def _by_key(view: dict) -> dict:
    return {item["key"]: item for item in view["nutrient_statuses"]}


class TestBuildOcrStatusView:
    def test_returns_eight_statuses_and_a_headline_slot(self, db):
        user = _user_row(db, make_user(db))

        view = build_ocr_status_view({}, user, db)

        assert len(view["nutrient_statuses"]) == 8
        assert "headline" in view

    def test_empty_day_with_no_pending_values_has_no_headline(self, db):
        user = _user_row(db, make_user(db))

        view = build_ocr_status_view({}, user, db)

        assert view["headline"] is None
        assert all(item["tier"] == "unknown" for item in view["nutrient_statuses"])

    def test_days_saved_logs_push_a_scanned_item_over_the_limit(self, db):
        # 브리프의 사례. 품목 단독 판정이면 1710/2300 = 74%(caution)지만, 이미 1400mg을
        # 먹은 날이라 실제 투영은 3110mg(135%, avoid)다.
        user_id = make_user(db)
        make_food_log(db, user_id, sodium_mg=1400)
        user = _user_row(db, user_id)

        view = build_ocr_status_view({"sodium": 1710.0}, user, db)

        sodium = _by_key(view)["sodium"]
        assert sodium["value"] == 3110
        assert sodium["tier"] == "avoid"
        assert view["headline"]["key"] == "sodium"

    def test_same_item_on_a_clean_day_is_safe_and_headline_is_not_alarming(self, db):
        user = _user_row(db, make_user(db))

        view = build_ocr_status_view({"sodium": 800.0}, user, db)

        assert _by_key(view)["sodium"]["tier"] == "safe"
        assert view["headline"]["tier"] == "safe"

    def test_caffeine_reflects_todays_logs_without_any_typed_value(self, db):
        # 라벨에 카페인은 인쇄되지 않으므로 pending은 항상 None으로 들어온다 —
        # 그래도 오늘 이미 마신 커피가 있으면 그 상태가 보여야 한다.
        user_id = make_user(db)
        make_food_log(db, user_id, caffeine_mg=180)
        user = _user_row(db, user_id)

        view = build_ocr_status_view({"caffeine": None}, user, db)

        caffeine = _by_key(view)["caffeine"]
        assert caffeine["value"] == 180
        assert caffeine["tier"] == "caution"  # 180/200 = 90%
        assert view["headline"]["key"] == "caffeine"

    def test_typed_caffeine_is_added_to_todays_total(self, db):
        user_id = make_user(db)
        make_food_log(db, user_id, caffeine_mg=150)
        user = _user_row(db, user_id)

        view = build_ocr_status_view({"caffeine": 100.0}, user, db)

        assert _by_key(view)["caffeine"]["value"] == 250
        assert _by_key(view)["caffeine"]["tier"] == "avoid"

    def test_manual_iron_value_gets_a_real_verdict(self, db):
        user = _user_row(db, make_user(db))

        view = build_ocr_status_view({"iron": 50.0}, user, db)

        iron = _by_key(view)["iron"]
        assert iron["status"] == "avoid"
        assert iron["tier"] == "avoid"

    def test_iron_below_lower_bound_is_neutral_and_never_the_headline(self, db):
        # ADDITION B: 철분 하한 미달은 유일한 판정 가능 항목이어도 헤드라인이 아니다.
        user = _user_row(db, make_user(db))

        view = build_ocr_status_view({"iron": 5.0}, user, db)

        assert _by_key(view)["iron"]["tier"] == "neutral"
        assert view["headline"] is None

    def test_floor_shortfall_alone_produces_no_headline(self, db):
        # 아침 스캔: 단백질/탄수화물이 하루 목표에 못 미치는 건 당연한 일이라
        # 경고 문장을 만들지 않는다.
        user = _user_row(db, make_user(db))

        view = build_ocr_status_view(
            {"carbohydrate": 20.0, "protein": 5.0, "energy": 300.0}, user, db
        )

        by_key = _by_key(view)
        assert by_key["protein"]["tier"] == "neutral"
        assert by_key["carbohydrate"]["tier"] == "neutral"
        assert view["headline"] is None

    def test_preferred_nutrient_wins_the_headline_within_the_same_severity(self, db):
        # 관심성분이 당류인 사용자: 나트륨/당류가 모두 avoid면 당류가 헤드라인이 된다.
        user_id = make_user(db, selected_nutrients="sugar")
        user = _user_row(db, user_id)

        view = build_ocr_status_view({"sodium": 3105.0, "sugar": 51.0}, user, db)

        assert _by_key(view)["sodium"]["tier"] == "avoid"
        assert _by_key(view)["sugar"]["tier"] == "avoid"
        assert view["headline"]["key"] == "sugar"

    def test_worse_severity_still_beats_a_preferred_nutrient(self, db):
        user_id = make_user(db, selected_nutrients="sugar")
        user = _user_row(db, user_id)

        view = build_ocr_status_view({"sodium": 3000.0, "sugar": 40.0}, user, db)

        assert _by_key(view)["sugar"]["tier"] == "caution"
        assert view["headline"]["key"] == "sodium"

    def test_other_days_logs_do_not_leak_into_todays_projection(self, db):
        user_id = make_user(db)
        make_food_log(db, user_id, sodium_mg=1400, eaten_at="2020-01-01 09:00:00")
        user = _user_row(db, user_id)

        view = build_ocr_status_view({"sodium": 800.0}, user, db)

        assert _by_key(view)["sodium"]["value"] == 800
        assert _by_key(view)["sodium"]["tier"] == "safe"

    def test_explicit_target_date_selects_that_days_logs(self, db):
        user_id = make_user(db)
        make_food_log(db, user_id, sodium_mg=1400, eaten_at="2020-01-01 09:00:00")
        user = _user_row(db, user_id)

        view = build_ocr_status_view({"sodium": 800.0}, user, db, target_date="2020-01-01")

        assert _by_key(view)["sodium"]["value"] == 2200

    def test_defaults_to_server_local_today(self, db):
        # make_food_log의 eaten_at 기본값은 datetime('now','localtime')이므로
        # date.today()와 같은 날짜여야 한다 — /intake/summary와 동일한 방식.
        user_id = make_user(db)
        make_food_log(db, user_id, sugar_g=30)
        user = _user_row(db, user_id)

        default_view = build_ocr_status_view({}, user, db)
        explicit_view = build_ocr_status_view({}, user, db, target_date=date.today().isoformat())

        assert _by_key(default_view)["sugar"]["value"] == _by_key(explicit_view)["sugar"]["value"]

    def test_headline_is_deterministic_for_the_same_inputs(self, db):
        user_id = make_user(db)
        make_food_log(db, user_id, sodium_mg=1400, caffeine_mg=190, sugar_g=48)
        user = _user_row(db, user_id)

        keys = {
            build_ocr_status_view({"sodium": 1710.0}, user, db)["headline"]["key"]
            for _ in range(25)
        }

        assert len(keys) == 1
