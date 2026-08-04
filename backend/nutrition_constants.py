"""임산부 1일 영양소 섭취 절대 기준값 (트라이메스터 불변, 앱 내부 보수적 기준).
- 카페인 200mg/day: ACOG/WHO
- 당류 50g/day: WHO (2000kcal 기준 10% 미만)
- 나트륨 1500mg/day: KDRI 충분섭취량(AI) — 기존 2300mg(CDRR)에서 변경

트라이메스터는 caution 민감도(early 카페인 60%, late 나트륨 80%, apply_safety_guard())에만
영향을 주며, 아래 절대 기준값 자체는 트라이메스터와 무관하게 항상 동일하다.

에너지/단백질 기준값은 19-29세 구간(2000kcal/55g)을 전 사용자 공통 baseline으로 고정 사용한다.
가입 시 나이(생년월일)를 수집하지 않기로 확정했으므로, 30-49세 구간이나 나이 기반 분기는
추가하지 않는다 — 분기할 나이 정보 자체가 없다.
"""
DAILY_CAFFEINE_LIMIT_MG = 200.0
DAILY_SUGAR_LIMIT_G = 50.0
DAILY_SODIUM_LIMIT_MG = 1500.0

# 탄수화물: 하한선(최소 섭취 권장량) — 다른 영양소와 달리 "초과"가 아니라 "미달"이 문제.
DAILY_CARB_MINIMUM_G = 175.0

# 에너지/단백질: 19-29세 baseline + 트라이메스터 가산량 (트라이메스터별로 값이 달라지는 유일한 절대 기준)
BASE_ENERGY_KCAL = 2000.0
BASE_PROTEIN_G = 55.0
TRIMESTER_ENERGY_ADD_KCAL = {"early": 0.0, "middle": 340.0, "late": 450.0}
TRIMESTER_PROTEIN_ADD_G = {"early": 0.0, "middle": 15.0, "late": 30.0}

# 지방: 고정 그램 기준이 아니라 총 에너지 섭취량 대비 비율 기준 (트라이메스터 불변)
FAT_ENERGY_RATIO_MIN = 0.15
FAT_ENERGY_RATIO_MAX = 0.30
SATURATED_FAT_ENERGY_RATIO_MAX = 0.07
TRANS_FAT_ENERGY_RATIO_MAX = 0.01
# 콜레스테롤: 국내 공식 상한 기준 없음 — 임계값을 만들지 않고 참고용 수치만 표시한다.

# 홈 화면 요약에 표시할 수 있는 선택형 영양소 (카페인/물은 항상 표시되므로 선택지에서 제외)
SELECTABLE_NUTRIENT_KEYS = ("carbohydrate", "sugar", "energy", "fat", "cholesterol", "protein", "sodium")
DEFAULT_SELECTED_NUTRIENTS = ("carbohydrate", "sugar", "sodium")
MAX_SELECTED_NUTRIENTS = 3

# 자유 텍스트로 입력된 추가 성분(food_log_extra_nutrients)의 name이 아래 라벨과
# 정확히 일치하면, 추가 성분 저장과 별개로 food_log의 타입 컬럼에도 값을 반영한다.
EXTRA_NUTRIENT_NAME_TO_COLUMN = {
    "지방": "fat_g",
    "콜레스테롤": "cholesterol_mg",
}


def validate_selected_nutrients(selected: list[str] | None) -> str | None:
    """selected_nutrients 입력값을 검증하고 DB 저장용 comma-separated 문자열로 변환한다.

    None(미지정)은 그대로 None을 반환한다 — PUT에서는 "값을 바꾸지 않음"으로,
    회원가입에서는 컬럼을 NULL로 남겨 조회 시 DEFAULT_SELECTED_NUTRIENTS로 해석되게 한다.
    빈 리스트는 유효한 입력(사용자가 3자리를 모두 명시적으로 비움)이며 ""로 저장된다.
    """
    if selected is None:
        return None
    if len(selected) > MAX_SELECTED_NUTRIENTS:
        raise ValueError(f"영양소는 최대 {MAX_SELECTED_NUTRIENTS}개까지 선택할 수 있어요.")
    if len(set(selected)) != len(selected):
        raise ValueError("같은 영양소를 중복해서 선택할 수 없어요.")
    if any(key not in SELECTABLE_NUTRIENT_KEYS for key in selected):
        raise ValueError("선택할 수 없는 영양소가 포함되어 있어요.")
    return ",".join(selected)


def parse_selected_nutrients(raw: str | None) -> list[str]:
    """DB에 저장된 comma-separated 문자열을 리스트로 변환한다.

    NULL(미설정)이면 DEFAULT_SELECTED_NUTRIENTS, 빈 문자열("")이면 사용자가 명시적으로
    전부 해제한 것이므로 빈 리스트를 반환한다 — 이 둘은 서로 다른 상태다.
    """
    if raw is None:
        return list(DEFAULT_SELECTED_NUTRIENTS)
    if raw == "":
        return []
    return raw.split(",")

# 수분 1일 권장 섭취량 2000mL(8잔 x 250mL): 일반 성인 권장 참고치.
# 트라이메스터별 기준값은 별도 연구 예정 - 현재는 단일 고정값만 사용.
DAILY_WATER_TARGET_ML = 2000.0

TRIMESTER_NOTES = {
    "early": "임신 초기에는 카페인 섭취량과 알레르기 유발 성분을 특히 꼼꼼히 확인해 주세요.",
    "middle": "임신 중기에는 당류 섭취가 누적되지 않도록 확인하고, 카페인 섭취량도 함께 관리해 주세요.",
    "late": "임신 후기에는 나트륨과 당류 섭취가 과도하게 누적되지 않도록 주의해 주세요.",
}
