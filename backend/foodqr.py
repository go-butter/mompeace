import os
import requests
from dotenv import load_dotenv

load_dotenv()

FOOD_QR_API_KEY = os.getenv("FOOD_QR_API_KEY")

BASE_URL = "https://foodqr.kr/openapi/service"

ENDPOINTS = {
    "basic": "/qr1003/F003",             # 기본정보
    "safety": "/qr1004/F004",            # 소비자 안전 주의사항
    "ingredient": "/qr1007/F007",        # 원재료 정보
    "nutrition": "/qr1008/F008",         # 영양표시정보
    "allergy": "/qr1009/F009",           # 알레르기정보
    "intake_warning": "/qr1014/F014"     # 섭취 시 주의사항
}


def extract_items(data):
    """
    푸드QR 응답에서 실제 item만 꺼내기.
    API 응답 구조가 조금 달라도 최대한 대응.
    """

    try:
        body = data.get("response", {}).get("body", {})
        items = body.get("items")

        if not items:
            return []

        item = items.get("item")

        if not item:
            return []

        if isinstance(item, list):
            return item

        return [item]

    except AttributeError:
        return []


def request_foodqr(endpoint: str, barcode: str):
    if not FOOD_QR_API_KEY:
        raise ValueError("FOOD_QR_API_KEY가 .env 파일에 설정되어 있지 않습니다.")

    if endpoint not in ENDPOINTS:
        raise ValueError(f"지원하지 않는 endpoint입니다: {endpoint}")

    url = BASE_URL + ENDPOINTS[endpoint]

    params = {
        "accessKey": FOOD_QR_API_KEY,
        "numOfRows": 10,
        "pageNo": 1,
        "_type": "json",
        "brcdNo": barcode
    }

    response = requests.get(url, params=params, timeout=10)
    response.raise_for_status()

    data = response.json()
    items = extract_items(data)

    return items


def get_food_info(barcode: str):
    """
    바코드로 푸드QR 주요 정보 통합 조회.
    기본정보가 없으면 해당 제품이 없다고 판단.
    """

    basic = request_foodqr("basic", barcode)

    # 기본정보가 없으면 제품 자체가 없다고 판단
    if not basic:
        return None

    return {
        "basic": basic,
        "safety": request_foodqr("safety", barcode),
        "ingredient": request_foodqr("ingredient", barcode),
        "nutrition": request_foodqr("nutrition", barcode),
        "allergy": request_foodqr("allergy", barcode),
        "intake_warning": request_foodqr("intake_warning", barcode)
    }

def simplify_food_info(api_data: dict):
    """
    푸드QR 원본 데이터를 앱에서 쓰기 좋은 형태로 정리
    """

    if not api_data:
        return None

    basic_list = api_data.get("basic", [])
    nutrition_list = api_data.get("nutrition", [])
    allergy_list = api_data.get("allergy", [])
    safety_list = api_data.get("safety", [])
    intake_warning_list = api_data.get("intake_warning", [])

    if not basic_list:
        return None

    basic = basic_list[0]

    # 영양정보 정리
    nutrition = {}
    for item in nutrition_list:
        name = item.get("nirwmtNm")   # 영양성분명
        amount = item.get("cta")      # 함량
        unit = item.get("igrdUcd")    # 단위

        if name:
            nutrition[name] = {
                "amount": amount,
                "unit": unit
            }

    # 앱에서 자주 쓸 값만 따로 꺼내기
    calories_kcal = nutrition.get("열량", {}).get("amount", 0)
    sodium_mg = nutrition.get("나트륨", {}).get("amount", 0)
    sugar_g = nutrition.get("당류", {}).get("amount", 0)
    carbohydrate_g = nutrition.get("탄수화물", {}).get("amount", 0)
    protein_g = nutrition.get("단백질", {}).get("amount", 0)

    # 알레르기 정보 정리
    allergens = []
    for item in allergy_list:
        allergen = item.get("algCsgMtrNm")
        if allergen and allergen not in allergens:
            allergens.append(allergen)

    # 주의사항 정리
    warnings = []

    for item in safety_list:
        warning = item.get("atentMterCn")
        if warning:
            warnings.append(warning.strip())

    for item in intake_warning_list:
        warning = item.get("atentMterCn")
        if warning:
            warnings.append(warning.strip())

    return {
        "barcode": basic.get("brcdNo"),
        "food_name": basic.get("prdctNm"),
        "food_category": basic.get("foodSeCdNm"),
        "food_type": basic.get("foodTypeCdNm"),
        "serving_size": basic.get("ctv"),

        "calories_kcal": calories_kcal,
        "sodium_mg": sodium_mg,
        "sugar_g": sugar_g,
        "carbohydrate_g": carbohydrate_g,
        "protein_g": protein_g,

        "allergens": allergens,
        "warnings": warnings,
    }