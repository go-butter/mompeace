"""
카페인 키워드 탐지.

recommendation_model.py의 규칙 판정(유일한 소비자)에서 caffeine_mg가 없는 식품에
대해 식품명 기반으로 카페인 함유 가능성을 보조 판단할 때 사용한다.
"""

CAFFEINE_KEYWORDS = [
    "커피", "카페", "카페인", "에스프레소", "라떼", "모카", "콜드브루",
    "녹차", "말차", "홍차", "초콜릿", "초코", "코코아", "콜라",
    "에너지드링크", "과라나"
]


def detect_caffeine_keywords(food_name: str) -> list:
    if not food_name:
        return []
    return [kw for kw in CAFFEINE_KEYWORDS if kw in food_name]
