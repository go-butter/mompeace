def get_trimester(week: int):
    """
    임신 주차를 초기/중기/후기로 변환
    """
    if week <= 12:
        return "early"
    elif week <= 27:
        return "middle"
    else:
        return "late"


def get_trimester_label(trimester: str):
    """
    초기/중기/후기를 한국어로 변환
    """
    if trimester == "early":
        return "임신 초기"
    elif trimester == "middle":
        return "임신 중기"
    elif trimester == "late":
        return "임신 후기"
    return "임신 단계 알 수 없음"


# 단일 제품 기준
# 주의: 아래 수치는 공식 임신 주차별 의학 기준이 아니라,
# 공신력 있는 1일 권고량을 바탕으로 앱 내부에서 보수적으로 설정한 판정 기준임.
PRODUCT_LIMITS = {
    "early": {
        "caffeine": {
            "safe_max": 50,
            "caution_max": 150,
            "unit": "mg"
        },
        "sugar": {
            "safe_max": 8,
            "caution_max": 25,
            "unit": "g"
        },
        "sodium": {
            "safe_max": 400,
            "caution_max": 1200,
            "unit": "mg"
        }
    },
    "middle": {
        "caffeine": {
            "safe_max": 70,
            "caution_max": 200,
            "unit": "mg"
        },
        "sugar": {
            "safe_max": 10,
            "caution_max": 30,
            "unit": "g"
        },
        "sodium": {
            "safe_max": 500,
            "caution_max": 1500,
            "unit": "mg"
        }
    },
    "late": {
        "caffeine": {
            "safe_max": 70,
            "caution_max": 200,
            "unit": "mg"
        },
        "sugar": {
            "safe_max": 8,
            "caution_max": 25,
            "unit": "g"
        },
        "sodium": {
            "safe_max": 400,
            "caution_max": 1200,
            "unit": "mg"
        }
    }
}


def get_product_status(nutrient: str, value: float, trimester: str):
    """
    임신 단계별 단일 제품 기준 위험도 판단

    safe: 비교적 낮음
    caution: 주의 필요
    avoid: 높은 편
    unknown: 값 없음 (None)
    """

    if value is None:
        return "unknown"

    limits = PRODUCT_LIMITS.get(trimester, PRODUCT_LIMITS["middle"])
    nutrient_limit = limits.get(nutrient)

    if not nutrient_limit:
        return "unknown"

    safe_max = nutrient_limit["safe_max"]
    caution_max = nutrient_limit["caution_max"]

    if value <= safe_max:
        return "safe"
    elif value <= caution_max:
        return "caution"
    else:
        return "avoid"


def get_product_standard_text(nutrient: str, trimester: str):
    """
    프론트/디버깅용 기준 설명 문장
    """

    limits = PRODUCT_LIMITS.get(trimester, PRODUCT_LIMITS["middle"])
    nutrient_limit = limits.get(nutrient)

    if not nutrient_limit:
        return "기준 정보 없음"

    safe_max = nutrient_limit["safe_max"]
    caution_max = nutrient_limit["caution_max"]
    unit = nutrient_limit["unit"]

    return f"단일 제품 기준 {safe_max}{unit} 이하 safe, {caution_max}{unit} 이하 caution, 초과 avoid"


def get_overall_status(statuses: list):
    """
    개별 성분 중 가장 높은 위험도를 전체 위험도로 반영.
    unknown/check_required는 수치 판단 불가이므로 전체 등급 산정에서 제외.
    """
    numeric = [s for s in statuses if s in ("safe", "caution", "avoid")]
    if not numeric:
        return "safe"
    if "avoid" in numeric:
        return "avoid"
    elif "caution" in numeric:
        return "caution"
    return "safe"


def make_risk_title(overall_status: str):
    """
    화면에 보여줄 위험도 제목
    """
    if overall_status == "safe":
        return "섭취 가능해 보여요"
    elif overall_status == "caution":
        return "조금 주의가 필요해요"
    elif overall_status == "avoid":
        return "섭취 전 확인이 필요해요"
    return "확인이 필요해요"


def make_status_label(status: str):
    """
    화면 표시용 한글 라벨
    """
    labels = {
        "safe": "안전",
        "caution": "주의",
        "avoid": "위험",
        "unknown": "정보 없음",
        "check_required": "확인 필요"
    }
    return labels.get(status, "확인")


def evaluate_food_risk(food_data: dict, pregnancy_week: int):
    """
    정리된 식품 데이터를 바탕으로 임산부 섭취 위험도 판단

    이 함수는 바코드 스캔 결과 화면용이다.
    즉, 하루 누적 섭취량이 아니라 단일 제품 기준으로 판단한다.
    """

    trimester = get_trimester(pregnancy_week)
    trimester_label = get_trimester_label(trimester)

    caffeine = food_data.get("caffeine_mg")           # None 유지 (unknown 처리)
    caffeine_keywords = food_data.get("caffeine_keywords") or []
    sugar = food_data.get("sugar_g", 0) or 0
    sodium = food_data.get("sodium_mg", 0) or 0
    allergens = food_data.get("allergens", []) or []

    # 카페인: None이면 키워드 유무로 unknown / check_required 분기
    if caffeine is None:
        if caffeine_keywords:
            caffeine_status = "check_required"
        else:
            caffeine_status = "unknown"
    else:
        caffeine_status = get_product_status("caffeine", caffeine, trimester)

    sugar_status = get_product_status("sugar", sugar, trimester)
    sodium_status = get_product_status("sodium", sodium, trimester)

    statuses = [caffeine_status, sugar_status, sodium_status]
    overall_status = get_overall_status(statuses)

    messages = []

    # 공통 메시지
    if sugar_status == "caution":
        messages.append("당류가 다소 있는 제품이에요. 다른 간식과 함께 먹을 때는 양을 조절해 주세요.")
    elif sugar_status == "avoid":
        messages.append("당류가 높은 편이에요. 섭취량을 줄이거나 대체 식품을 고려해 주세요.")

    if sodium_status == "caution":
        messages.append("나트륨이 다소 있는 제품이에요. 오늘 다른 짠 음식과 함께 먹는 것은 주의해 주세요.")
    elif sodium_status == "avoid":
        messages.append("나트륨이 높은 편이에요. 부종이나 혈압 관리가 필요한 경우 특히 확인해 주세요.")

    if caffeine_status == "check_required":
        messages.append(
            f"음식명에 {', '.join(caffeine_keywords)} 관련 표현이 있어 카페인 함량 확인이 필요해요."
        )
    elif caffeine_status == "caution":
        messages.append("카페인이 포함되어 있어요. 오늘 마신 커피나 차와 함께 계산해 주세요.")
    elif caffeine_status == "avoid":
        messages.append("카페인 함량이 높은 편이에요. 임신 중에는 섭취 전 확인이 필요해요.")

    if allergens:
        messages.append("알레르기 유발 성분이 포함되어 있어요. 본인 알레르기 정보와 꼭 비교해 주세요.")

    # 임신 단계별 강조 메시지
    if trimester == "early":
        if caffeine or caffeine_status in ("caution", "avoid", "check_required"):
            messages.append("임신 초기에는 카페인 섭취량을 특히 확인하는 것이 좋아요.")
        if sugar_status in ["caution", "avoid"]:
            messages.append("임신 초기에는 당류가 많은 간식이 누적되지 않도록 주의해 주세요.")
        if allergens:
            messages.append("임신 초기에는 음식 성분과 알레르기 정보를 더 꼼꼼히 확인해 주세요.")

    elif trimester == "middle":
        if sugar_status in ["caution", "avoid"]:
            messages.append("임신 중기에는 당류 섭취가 누적되지 않도록 주의해 주세요.")
        if caffeine or caffeine_status in ("caution", "avoid", "check_required"):
            messages.append("임신 중기에도 카페인 섭취량은 하루 누적량 기준으로 확인해 주세요.")

    else:
        if sodium_status in ["caution", "avoid"]:
            messages.append("임신 후기에는 나트륨 섭취가 많아지지 않도록 주의해 주세요.")
        if sugar_status in ["caution", "avoid"]:
            messages.append("임신 후기에는 당류와 나트륨을 함께 확인하는 것이 좋아요.")

    if not messages:
        messages.append("현재 확인된 주요 성분 기준으로는 큰 주의 신호가 없어요.")

    return {
        "pregnancy_week": pregnancy_week,
        "trimester": trimester,
        "trimester_label": trimester_label,
        "overall_status": overall_status,
        "overall_label": make_status_label(overall_status),
        "title": make_risk_title(overall_status),
        "details": {
            "caffeine": {
                "value": caffeine,
                "unit": "mg",
                "status": caffeine_status,
                "label": make_status_label(caffeine_status),
                "standard": get_product_standard_text("caffeine", trimester),
                "keywords": caffeine_keywords
            },
            "sugar": {
                "value": sugar,
                "unit": "g",
                "status": sugar_status,
                "label": make_status_label(sugar_status),
                "standard": get_product_standard_text("sugar", trimester)
            },
            "sodium": {
                "value": sodium,
                "unit": "mg",
                "status": sodium_status,
                "label": make_status_label(sodium_status),
                "standard": get_product_standard_text("sodium", trimester)
            },
            "allergy": {
                "allergens": allergens,
                "status": "check_required" if allergens else "safe",
                "label": "확인 필요" if allergens else "안전"
            }
        },
        "messages": messages
    }