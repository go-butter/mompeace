_TRUSTED_SOURCES = {"dish_db_download", "food_qr_api"}


def calculate_data_confidence(food: dict) -> dict:
    score = 0.0
    reasons = []

    if food.get("data_source") in _TRUSTED_SOURCES:
        score += 0.3
        reasons.append("공공 음식DB 또는 푸드QR 기반 데이터예요.")
    else:
        reasons.append("출처가 제한적인 데이터예요.")

    if food.get("caffeine_mg") is not None:
        score += 0.25
        reasons.append("카페인 수치가 제공되어 있어요.")
    else:
        reasons.append("카페인 수치가 확인되지 않았어요.")

    if food.get("sugar_g") is not None:
        score += 0.2
        reasons.append("당류 수치가 제공되어 있어요.")
    else:
        reasons.append("당류 수치가 확인되지 않았어요.")

    if food.get("sodium_mg") is not None:
        score += 0.15
        reasons.append("나트륨 수치가 제공되어 있어요.")
    else:
        reasons.append("나트륨 수치가 확인되지 않았어요.")

    allergen = food.get("allergen_info") or ""
    if allergen.strip():
        score += 0.1
        reasons.append("알레르기 정보가 제공되어 있어요.")

    score = min(score, 1.0)

    if score >= 0.75:
        label = "높음"
    elif score >= 0.45:
        label = "보통"
    else:
        label = "낮음"

    return {"score": round(score, 2), "label": label, "reasons": reasons}
