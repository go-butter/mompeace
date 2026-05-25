import os
import requests
from pathlib import Path
from dotenv import load_dotenv

# ── .env 로드 ───────────────────────────────────────
BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

FOOD_NUTRITION_API_KEY = os.getenv("FOOD_NUTRITION_API_KEY")

BASE_URL = "https://apis.data.go.kr/1471000/FoodNtrCpntDbInfo02/getFoodNtrCpntDbInq02"

CAFFEINE_KEYWORDS = [
    "커피", "카페", "카페인", "에스프레소", "라떼", "모카", "콜드브루",
    "녹차", "말차", "홍차", "초콜릿", "초코", "코코아", "콜라",
    "에너지드링크", "과라나"
]


def detect_caffeine_keywords(food_name: str) -> list:
    if not food_name:
        return []
    return [kw for kw in CAFFEINE_KEYWORDS if kw in food_name]


def to_float(value, default=0):
    """
    문자열 숫자를 float로 변환

    예:
    - "100g" -> 100.0
    - "58.00g" -> 58.0
    - "238.000" -> 238.0
    - "" -> 0
    """

    if value is None:
        return default

    try:
        text = str(value).strip()

        if text == "" or text == "-" or text.upper() == "N/A":
            return default

        text = (
            text.replace("g", "")
            .replace("mg", "")
            .replace("kcal", "")
            .strip()
        )

        return float(text)

    except ValueError:
        return default


def normalize_items(raw_items):
    """
    공공데이터포털 응답의 items 구조를 리스트로 통일한다.
    """

    if not raw_items:
        return []

    if isinstance(raw_items, list):
        return raw_items

    if isinstance(raw_items, dict):
        return [raw_items]

    return []


def search_food_nutrition_raw(
    query: str,
    page_no: int = 1,
    num_of_rows: int = 10
):
    """
    식품의약품안전처 식품영양성분DB정보 원본 응답 조회
    """

    if not FOOD_NUTRITION_API_KEY:
        raise RuntimeError("FOOD_NUTRITION_API_KEY가 .env에 설정되어 있지 않습니다.")

    params = {
        "serviceKey": FOOD_NUTRITION_API_KEY,
        "pageNo": page_no,
        "numOfRows": num_of_rows,
        "type": "json",
        "FOOD_NM_KR": query
    }

    response = requests.get(BASE_URL, params=params, timeout=10)
    response.raise_for_status()

    return response.json()


def simplify_food_nutrition_item(item: dict):
    """
    식품영양성분DB item 1개를 앱에서 쓰는 형태로 정리한다.

    저장하는 성분:
    - AMT_NUM3: 단백질 g
    - AMT_NUM6: 탄수화물 g
    - AMT_NUM13: 나트륨 mg
    - AMT_NUM23: 당류 g

    저장하지 않는 성분:
    - 열량
    - 지방
    - 포화지방
    - 트랜스지방
    - 콜레스테롤

    이유:
    이 앱은 체중 관리가 아니라 임산부의 섭취 안전 판단이 목적이므로,
    카페인·당류·나트륨·알레르기 중심으로 데이터를 최소화한다.
    """

    food_name = item.get("FOOD_NM_KR")

    if not food_name:
        return None

    serving_size = item.get("Z10500") or item.get("SERVING_SIZE") or ""

    food_data = {
        "food_code": item.get("FOOD_CD"),
        "food_name": food_name,
        "food_name_en": None,
        "barcode": None,

        "category": item.get("FOOD_CAT1_NM") or item.get("DB_GRP_NM"),
        "subcategory": item.get("FOOD_REF_NM") or item.get("FOOD_CAT2_NM"),

        "serving_size_g": to_float(serving_size),
        "serving_label": str(serving_size),

        # 핵심 판단 성분
        "caffeine_mg": None,
        "caffeine_keywords": detect_caffeine_keywords(food_name),
        "sugar_g": to_float(item.get("AMT_NUM23")),
        "sodium_mg": to_float(item.get("AMT_NUM13")),

        # 보조 참고 성분
        "carbohydrate_g": to_float(item.get("AMT_NUM6")),
        "protein_g": to_float(item.get("AMT_NUM3")),

        # 이 API에는 알레르기 정보가 안정적으로 없음
        "allergens": [],
        "warnings": [],

        "maker_name": item.get("MAKER_NM"),
        "item_report_no": item.get("ITEM_REPORT_NO"),

        "notes": (
            f"자료출처: {item.get('SUB_REF_NAME') or ''} / "
            f"제조사: {item.get('MAKER_NM') or ''} / "
            f"식품분류: {item.get('DB_CLASS_NM') or ''} / "
            f"데이터생성일자: {item.get('RESEARCH_YMD') or ''} / "
            f"데이터수정일자: {item.get('UPDATE_DATE') or ''}"
        )
    }

    return food_data


def search_food_nutrition(
    query: str,
    page_no: int = 1,
    num_of_rows: int = 10
):
    """
    음식명으로 식품영양성분DB 검색 후 앱용 데이터 리스트 반환
    """

    raw = search_food_nutrition_raw(
        query=query,
        page_no=page_no,
        num_of_rows=num_of_rows
    )

    header = raw.get("header", {})
    result_code = header.get("resultCode")
    result_msg = header.get("resultMsg")

    if result_code != "00":
        print(f"❌ 식품영양성분DB API 오류: {result_code} / {result_msg}")
        return []

    body = raw.get("body", {})
    raw_items = body.get("items")

    item_list = normalize_items(raw_items)

    results = []

    for item in item_list:
        simplified = simplify_food_nutrition_item(item)
        if simplified:
            results.append(simplified)

    return results