from pydantic import BaseModel
from typing import Optional


class RegisterRequest(BaseModel):
    nickname: str
    login_id: str
    password: str
    password_confirm: str


class LoginRequest(BaseModel):
    login_id: str
    password: str


class UserCreate(BaseModel):
    nickname: str
    pregnancy_week: Optional[int] = None
    due_date: Optional[str] = None
    allergy_info: Optional[str] = None
    interest_ingredients: Optional[str] = None


class PregnancyUpdate(BaseModel):
    pregnancy_week: Optional[int] = None
    pregnancy_day: Optional[int] = None
    due_date: Optional[str] = None


class AllergyUpdate(BaseModel):
    allergy_info: str


class FoodLogCreate(BaseModel):
    user_id: int
    food_name: str
    input_type: str
    category: Optional[str] = None
    amount: float = 1.0
    unit: str = "개"
    caffeine_mg: Optional[float] = None
    sugar_g: float = 0
    sodium_mg: float = 0
    calories_kcal: float = 0
    carbohydrate_g: Optional[float] = None
    protein_g: Optional[float] = None
    food_id: Optional[int] = None


class FoodLogFromFood(BaseModel):
    user_id: int
    food_id: int
    amount: float = 1.0
    unit: str = "개"


class RecommendationRequest(BaseModel):
    user_id: int
    query: Optional[str] = None
    category: Optional[str] = None
    limit: int = 10


class PremiumUpgradeRequest(BaseModel):
    user_id: int
    agree: bool


class PremiumStatusResponse(BaseModel):
    user_id: int
    is_premium: bool
    premium_started_at: Optional[str] = None
    premium_updated_at: Optional[str] = None
    message: str


class FeedbackRequest(BaseModel):
    user_id: int
    log_id: int
    feedback: int  # 1 or -1 only