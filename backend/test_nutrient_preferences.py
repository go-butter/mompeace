"""
선택 영양소(nutrient preferences) 기능 테스트.

핵심 검증 대상:
- 회원가입 시 selected_nutrients 미지정 -> NULL 저장, 조회 시 DEFAULT_SELECTED_NUTRIENTS로 해석
- 검증: 최대 4개, 허용 목록(SELECTABLE_NUTRIENT_KEYS)만 가능, 중복 불가
- 카페인/물은 애초에 SELECTABLE_NUTRIENT_KEYS에 없으므로 자동으로 거부됨
- PUT: selected_nutrients가 None이면 부분 업데이트(변경 없음), 빈 리스트는 유효한 값
- NULL(미설정)과 ""(명시적으로 전부 해제)은 서로 다른 상태로 유지됨
"""
import pytest
from fastapi import HTTPException

from backend.auth import register_user
from backend.models import NutrientPreferenceUpdate, RegisterRequest
from backend.routers.users import update_nutrient_preferences

from .conftest import make_user


class TestRegisterDefaultSelection:
    def test_omitted_selection_stores_null_and_reads_as_default(self, db):
        result = register_user(
            RegisterRequest(
                nickname="테스트유저", login_id="tester1",
                password="pw1234", password_confirm="pw1234",
            ),
            db,
        )
        cursor = db.cursor()
        cursor.execute("SELECT selected_nutrients FROM users WHERE user_id = ?", (result["user_id"],))
        assert cursor.fetchone()["selected_nutrients"] is None

        read_back = update_nutrient_preferences(
            user_id=result["user_id"], prefs=NutrientPreferenceUpdate(selected_nutrients=None), db=db
        )
        assert read_back["selected_nutrients"] == ["carbohydrate", "sugar", "sodium"]

    def test_valid_selection_at_register_is_stored(self, db):
        result = register_user(
            RegisterRequest(
                nickname="테스트유저", login_id="tester2",
                password="pw1234", password_confirm="pw1234",
                selected_nutrients=["protein", "fat"],
            ),
            db,
        )
        cursor = db.cursor()
        cursor.execute("SELECT selected_nutrients FROM users WHERE user_id = ?", (result["user_id"],))
        assert cursor.fetchone()["selected_nutrients"] == "protein,fat"

    def test_more_than_four_at_register_returns_400(self, db):
        with pytest.raises(HTTPException) as exc_info:
            register_user(
                RegisterRequest(
                    nickname="테스트유저", login_id="tester3",
                    password="pw1234", password_confirm="pw1234",
                    selected_nutrients=["carbohydrate", "sugar", "sodium", "protein", "fat"],
                ),
                db,
            )
        assert exc_info.value.status_code == 400


class TestUpdateNutrientPreferencesValidation:
    def test_unknown_user_returns_404(self, db):
        with pytest.raises(HTTPException) as exc_info:
            update_nutrient_preferences(
                user_id=999999, prefs=NutrientPreferenceUpdate(selected_nutrients=["sodium"]), db=db
            )
        assert exc_info.value.status_code == 404

    def test_more_than_four_returns_400(self, db):
        user_id = make_user(db)
        with pytest.raises(HTTPException) as exc_info:
            update_nutrient_preferences(
                user_id=user_id,
                prefs=NutrientPreferenceUpdate(
                    selected_nutrients=["carbohydrate", "sugar", "sodium", "protein", "fat"]
                ),
                db=db,
            )
        assert exc_info.value.status_code == 400

    def test_duplicate_key_returns_400(self, db):
        user_id = make_user(db)
        with pytest.raises(HTTPException) as exc_info:
            update_nutrient_preferences(
                user_id=user_id,
                prefs=NutrientPreferenceUpdate(selected_nutrients=["sodium", "sodium"]),
                db=db,
            )
        assert exc_info.value.status_code == 400

    def test_caffeine_is_rejected_as_not_selectable(self, db):
        user_id = make_user(db)
        with pytest.raises(HTTPException) as exc_info:
            update_nutrient_preferences(
                user_id=user_id,
                prefs=NutrientPreferenceUpdate(selected_nutrients=["caffeine"]),
                db=db,
            )
        assert exc_info.value.status_code == 400

    def test_water_is_rejected_as_not_selectable(self, db):
        user_id = make_user(db)
        with pytest.raises(HTTPException) as exc_info:
            update_nutrient_preferences(
                user_id=user_id,
                prefs=NutrientPreferenceUpdate(selected_nutrients=["water"]),
                db=db,
            )
        assert exc_info.value.status_code == 400

    def test_invalid_key_returns_400(self, db):
        user_id = make_user(db)
        with pytest.raises(HTTPException) as exc_info:
            update_nutrient_preferences(
                user_id=user_id,
                prefs=NutrientPreferenceUpdate(selected_nutrients=["iron"]),
                db=db,
            )
        assert exc_info.value.status_code == 400


class TestUpdateNutrientPreferencesPartialUpdate:
    def test_none_leaves_existing_selection_unchanged(self, db):
        user_id = make_user(db)
        update_nutrient_preferences(
            user_id=user_id, prefs=NutrientPreferenceUpdate(selected_nutrients=["protein", "fat"]), db=db
        )
        result = update_nutrient_preferences(
            user_id=user_id, prefs=NutrientPreferenceUpdate(selected_nutrients=None), db=db
        )
        assert result["selected_nutrients"] == ["protein", "fat"]

    def test_explicit_empty_list_is_valid_and_distinct_from_unset(self, db):
        user_id = make_user(db)
        result = update_nutrient_preferences(
            user_id=user_id, prefs=NutrientPreferenceUpdate(selected_nutrients=[]), db=db
        )
        assert result["selected_nutrients"] == []

        cursor = db.cursor()
        cursor.execute("SELECT selected_nutrients FROM users WHERE user_id = ?", (user_id,))
        # ""(명시적으로 전부 해제)은 NULL(미설정)과 다른 값으로 저장되어야 한다
        assert cursor.fetchone()["selected_nutrients"] == ""

    def test_valid_four_item_selection_is_stored_and_read_back(self, db):
        user_id = make_user(db)
        result = update_nutrient_preferences(
            user_id=user_id,
            prefs=NutrientPreferenceUpdate(
                selected_nutrients=["carbohydrate", "energy", "cholesterol", "sodium"]
            ),
            db=db,
        )
        assert result["selected_nutrients"] == ["carbohydrate", "energy", "cholesterol", "sodium"]
