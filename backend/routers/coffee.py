from fastapi import APIRouter

from backend.coffee_caffeine_data import COFFEE_CAFFEINE_DATA, HOME_COFFEE_PRESETS

router = APIRouter()


@router.get("/coffee/options")
def get_coffee_options():
    return {"brands": COFFEE_CAFFEINE_DATA, "home_presets": HOME_COFFEE_PRESETS}
