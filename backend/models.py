from pydantic import BaseModel
from typing import Optional


class RegisterRequest(BaseModel):
    nickname: str
    login_id: str
    password: str
    password_confirm: str
    selected_nutrients: Optional[list[str]] = None


class LoginRequest(BaseModel):
    login_id: str
    password: str


class PregnancyUpdate(BaseModel):
    pregnancy_week: Optional[int] = None
    pregnancy_day: Optional[int] = None
    due_date: Optional[str] = None


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
    calories_kcal: float = 0
    carbohydrate_g: Optional[float] = None
    protein_g: Optional[float] = None
    fat_g: Optional[float] = None
    cholesterol_mg: Optional[float] = None
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


class RecommendationRequest(BaseModel):
    user_id: int
    query: Optional[str] = None
    category: Optional[str] = None
    limit: int = 10


class FeedbackRequest(BaseModel):
    user_id: int
    log_id: int
    feedback: int  # 1 or -1 only