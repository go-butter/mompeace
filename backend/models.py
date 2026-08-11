from pydantic import BaseModel, field_validator
from typing import Optional, Union

from backend.nutrition_constants import PANEL_NUTRIENT_KEYS


class RegisterRequest(BaseModel):
    nickname: str
    login_id: str
    password: str
    password_confirm: str
    selected_nutrients: Optional[list[str]] = None
    age_bracket: Optional[str] = None


class LoginRequest(BaseModel):
    login_id: str
    password: str


class AccountDeleteRequest(BaseModel):
    password: str


class PregnancyUpdate(BaseModel):
    pregnancy_week: Optional[int] = None
    pregnancy_day: Optional[int] = None
    due_date: Optional[str] = None
    age_bracket: Optional[str] = None


class NutrientPreferenceUpdate(BaseModel):
    selected_nutrients: Optional[list[str]] = None


class ExtraNutrientIn(BaseModel):
    name: str
    value: str
    unit: Optional[str] = None


class FoodLogCreate(BaseModel):
    user_id: int
    food_name: str
    input_type: str
    category: Optional[str] = None
    amount: float = 1.0
    unit: str = "개"
    caffeine_mg: Optional[float] = None
    sugar_g: Optional[float] = None
    sodium_mg: Optional[float] = None
    calories_kcal: Optional[float] = None
    carbohydrate_g: Optional[float] = None
    protein_g: Optional[float] = None
    fat_g: Optional[float] = None
    cholesterol_mg: Optional[float] = None
    iron_mg: Optional[float] = None
    food_id: Optional[int] = None
    eaten_at: Optional[str] = None
    extra_nutrients: Optional[list[ExtraNutrientIn]] = None
    needs_review: Optional[bool] = False
    serving_multiplier: Optional[float] = None


class FoodLogFromFood(BaseModel):
    user_id: int
    food_id: int
    amount: float = 1.0
    unit: str = "개"


class WaterLogCreate(BaseModel):
    user_id: int
    amount_ml: float
    logged_at: Optional[str] = None


class UserFoodItemCreate(BaseModel):
    user_id: int
    food_name: str
    caffeine_mg: Optional[float] = None
    sugar_g: float = 0
    sodium_mg: float = 0
    calories_kcal: float = 0
    carbohydrate_g: Optional[float] = None
    protein_g: Optional[float] = None
    fat_g: Optional[float] = None
    saturated_fat_g: Optional[float] = None
    trans_fat_g: Optional[float] = None
    cholesterol_mg: Optional[float] = None
    iron_mg: Optional[float] = None


class RecommendationRequest(BaseModel):
    user_id: int
    query: Optional[str] = None
    # 문자열 하나(기존 클라이언트) 또는 리스트(다중 선택) 둘 다 받는다. 어느 쪽으로
    # 들어오든 아래 validator가 list[str]로 정규화하므로 라우터는 한 가지 형태만 다룬다.
    # 빈 리스트는 "카테고리 필터 없음"(전체)이며, None과 같은 의미다.
    category: Optional[Union[str, list[str]]] = None
    limit: int = 10
    # 화면의 영양소 칩. 정렬 기준일 뿐 후보를 걸러내지는 않는다 — 어떤 칩을 골라도
    # 목록에서 음식이 사라지지 않아야 한다.
    sort_nutrient: Optional[str] = None

    @field_validator("sort_nutrient", mode="after")
    @classmethod
    def _validate_sort_nutrient(cls, value):
        if value is None or value == "":
            return None
        if value not in PANEL_NUTRIENT_KEYS:
            raise ValueError("정렬 기준으로 사용할 수 없는 영양소예요.")
        return value

    @field_validator("category", mode="after")
    @classmethod
    def _normalize_category(cls, value):
        if value is None:
            return []
        if isinstance(value, str):
            return [value] if value else []
        return [c for c in value if c]


class FeedbackRequest(BaseModel):
    user_id: int
    log_id: int
    feedback: int  # 1 or -1 only