"""임산부 1일 영양소 섭취 절대 기준값 (트라이메스터 불변, 앱 내부 보수적 기준).
- 카페인 200mg/day: ACOG/WHO
- 당류 50g/day: WHO (2000kcal 기준 10% 미만)
- 나트륨 2300mg/day: KDRI 만성질환위험감소섭취량(CDRR)

나트륨에는 KDRI 값이 두 개 있고 성격이 정반대다. 충분섭취량(AI) 1500mg은 "이 정도는
채우라"는 하한형 참고치라 상한으로 쓸 수 없고, 상한형 값은 CDRR 2300mg이다. 이 앱의
판정은 전부 "넘으면 위험"이므로 CDRR을 쓴다 (docs/임신_관련_정보.md 참고).

에너지/단백질 기준값은 나이대(19-29세 / 30-49세)에 따라 다른 baseline을 사용한다.
가입 시 생년월일 대신 나이대(age_bracket)를 선택형으로 수집한다 — 표준 자체가 나이대로
구간화되어 있고, 정확한 나이를 계속 계산할 필요도 없기 때문이다.
"""
DAILY_CAFFEINE_LIMIT_MG = 200.0
DAILY_SUGAR_LIMIT_G = 50.0
DAILY_SODIUM_LIMIT_MG = 2300.0

# 주의: mompeace.db의 pregnancy_limits 테이블은 이 값들의 죽은 그림자 사본이다
# (나트륨 2000/2000/1800, 당류 30/40/30 — 전부 낡은 값). 어떤 코드도 참조하지 않으며
# 기준값의 단일 소스는 이 파일이다. 별도 마이그레이션에서 테이블을 삭제할 것.

# 탄수화물: 하한선(최소 섭취 권장량) — 다른 영양소와 달리 "초과"가 아니라 "미달"이 문제.
DAILY_CARB_MINIMUM_G = 175.0

# 나이대: users.age_bracket 컬럼에 저장되는 값. 가입 시 미입력이거나 기존(마이그레이션 이전)
# 사용자는 "19-29"로 취급한다 — 기존 고정 baseline과 동일해 회귀가 없다.
AGE_BRACKETS = ("19-29", "30-49")
DEFAULT_AGE_BRACKET = "19-29"

# 에너지/단백질: 나이대별 baseline + 트라이메스터 가산량 (트라이메스터별로 값이 달라지는 유일한 절대 기준)
BASE_ENERGY_KCAL = {"19-29": 2000.0, "30-49": 1900.0}
BASE_PROTEIN_G = {"19-29": 55.0, "30-49": 50.0}
TRIMESTER_ENERGY_ADD_KCAL = {"early": 0.0, "middle": 340.0, "late": 450.0}
TRIMESTER_PROTEIN_ADD_G = {"early": 0.0, "middle": 15.0, "late": 30.0}


def validate_age_bracket(age_bracket: str | None) -> str | None:
    """age_bracket 입력값을 검증한다.

    None(미지정)은 그대로 None을 반환한다 — PUT에서는 "값을 바꾸지 않음"으로,
    회원가입에서는 컬럼을 NULL로 남겨 조회 시 DEFAULT_AGE_BRACKET으로 해석되게 한다.
    """
    if age_bracket is None:
        return None
    if age_bracket not in AGE_BRACKETS:
        raise ValueError(f"나이대는 {', '.join(AGE_BRACKETS)} 중 하나여야 해요.")
    return age_bracket

# 지방: 고정 그램 기준이 아니라 총 에너지 섭취량 대비 비율 기준 (트라이메스터 불변)
FAT_ENERGY_RATIO_MIN = 0.15
FAT_ENERGY_RATIO_MAX = 0.30
SATURATED_FAT_ENERGY_RATIO_MAX = 0.07
TRANS_FAT_ENERGY_RATIO_MAX = 0.01
# 지방 1g = 9kcal — 비율(energy_total * ratio)은 kcal 단위이므로, food_log에 그램 단위로
# 저장된 실제 섭취량과 비교하려면 이 값으로 나눠 그램 기준으로 환산해야 한다.
KCAL_PER_GRAM_FAT = 9.0

# 철분: 임신부 1일 권장섭취량(24mg)과 상한섭취량(45mg), KDRI. 트라이메스터 무관 고정값
# (카페인/당류/나트륨과 동일한 취급 — 지방처럼 에너지 대비 비율이 아니라 절대 mg 기준).
IRON_RECOMMENDED_MG = 24.0
IRON_UPPER_LIMIT_MG = 45.0

# 콜레스테롤: 국내 공식 상한 기준 없어 판정/선택형 트래킹 대상에서는 제외했지만,
# food_log.cholesterol_mg 등 데이터 수집 자체는 그대로 유지한다 (음식 상세 화면 등에서 계속 표시됨).

# 홈 화면 요약에 표시할 수 있는 선택형 영양소 (카페인/물은 항상 표시되므로 선택지에서 제외)
SELECTABLE_NUTRIENT_KEYS = ("carbohydrate", "sugar", "energy", "fat", "iron", "protein", "sodium")
DEFAULT_SELECTED_NUTRIENTS = ("carbohydrate", "sugar", "sodium")
MAX_SELECTED_NUTRIENTS = 3

# 추천 화면 상단 패널이 다루는 영양소 = 항상 표시하는 카페인 + 선택형 7개.
# NUTRIENT_SUMMARY_FIELDS(intake_totals.py)의 키 집합과 정확히 같아야 한다 — 그쪽이
# 방향(ceiling/floor/band)과 판정 함수를 들고 있고, 이쪽은 "무엇을 보여줄 수 있는가"만
# 정한다. /recommendations의 sort_nutrient 검증도 이 튜플을 쓴다.
PANEL_NUTRIENT_KEYS = ("caffeine",) + SELECTABLE_NUTRIENT_KEYS

# app/constants/nutrients.ts의 NUTRIENT_LABELS_KO와 값을 맞춰서 유지한다
# (두 언어 간 공유 코드젠이 없어 수동 동기화 — 파일 상단 주석 참고).
NUTRIENT_LABELS_KO = {
    "caffeine": "카페인",
    "water": "물",
    "carbohydrate": "탄수화물",
    "sugar": "당류",
    "energy": "에너지",
    "fat": "지방",
    "iron": "철분",
    "protein": "단백질",
    "sodium": "나트륨",
}

# 자유 텍스트로 입력된 추가 성분(food_log_extra_nutrients)의 name이 아래 라벨과
# 정확히 일치하면, 추가 성분 저장과 별개로 food_log의 타입 컬럼에도 값을 반영한다.
# 탄수화물/당류/에너지/단백질/나트륨은 추적 대상 7개 영양소(NUTRIENT_LABELS_KO)와
# 이름이 같다 — 매칭되면 daily 누적 판정(get_status 계열)에도 그대로 반영된다.
# 콜레스테롤은 7개 추적 대상에는 없지만(판정 제외, nutrition_constants 상단 주석 참고)
# 상세 화면 참고용 데이터 수집은 계속하므로 매핑을 유지한다.
EXTRA_NUTRIENT_NAME_TO_COLUMN = {
    "탄수화물": "carbohydrate_g",
    "당류": "sugar_g",
    "에너지": "calories_kcal",
    "지방": "fat_g",
    "철분": "iron_mg",
    "단백질": "protein_g",
    "나트륨": "sodium_mg",
    "콜레스테롤": "cholesterol_mg",
}

# 단일 품목(OCR 스캔 결과 등) 판정용 — 추적 대상 7개 영양소가 각각 어떤 판정 방식을
# 쓰는지(intake_totals.get_status 계열과 대응). "floor"(탄수화물/에너지/단백질)는
# 누적 하루 최소치 개념이라 단일 품목에는 적용하지 않는다 — 단일 품목 판정에서는
# 항상 unknown으로 처리한다(backend/intake_totals.py의 build_item_nutrient_statuses 참고).
NUTRIENT_STATUS_TYPE = {
    "carbohydrate": "floor",
    "sugar": "ceiling",
    "energy": "floor",
    "fat": "band",
    "iron": "band",
    "protein": "floor",
    "sodium": "ceiling",
}

# 일일 투영(daily projection) 판정용 — OCR 확인 화면의 "오늘 섭취 안전도" 카드가
# 쓰는 8개 영양소 정의. 위 NUTRIENT_STATUS_TYPE(단일 품목 판정용 7개)과 의도적으로
# 분리해 둔 별도 테이블이다:
# - 카페인은 한국 영양성분표에 인쇄되지 않아 OCR이 절대 추출할 수 없지만, 앱에서
#   가장 엄격한 기준(200mg)이라 하루 누적 판정에는 반드시 들어가야 한다.
# - 그렇다고 NUTRIENT_STATUS_TYPE에 카페인을 추가할 수는 없다 —
#   get_item_nutrient_status()의 ceiling 분기가 {"sugar","sodium"} 하드코딩 맵을
#   쓰기 때문에 /ocr/alternatives가 카페인 키에서 KeyError로 깨진다.
# 임계값 자체는 여기 두지 않는다(단일 소스 유지) — limit_key로 get_trimester_limits()의
# 반환값을 가리키기만 한다. band형(지방/철분)은 자체 판정 함수가 상한을 따로
# 계산하므로 limit_key가 None이다.
#
# total_key/known_key는 fetch_daily_nutrient_totals()가 돌려주는 집계 컬럼명이다.
# 순서 = 배지 그리드 표시 순서. 기존 7개 순서를 그대로 두고 카페인을 여덟 번째로
# 덧붙인다(기존 화면의 시각적 순서를 바꾸지 않기 위해).
DAILY_PROJECTION_NUTRIENTS = {
    "carbohydrate": {"type": "floor",   "total_key": "total_carbohydrate", "known_key": "known_carbohydrate_count", "limit_key": "carbohydrate_g", "unit": "g"},
    "sugar":        {"type": "ceiling", "total_key": "total_sugar",        "known_key": "known_sugar_count",        "limit_key": "sugar_g",        "unit": "g"},
    "energy":       {"type": "floor",   "total_key": "total_calories",     "known_key": "known_energy_count",       "limit_key": "energy_kcal",    "unit": "kcal"},
    "fat":          {"type": "band",    "total_key": "total_fat",          "known_key": "known_fat_count",          "limit_key": None,             "unit": "g"},
    "iron":         {"type": "band",    "total_key": "total_iron",         "known_key": "known_iron_count",         "limit_key": None,             "unit": "mg"},
    "protein":      {"type": "floor",   "total_key": "total_protein",      "known_key": "known_protein_count",      "limit_key": "protein_g",      "unit": "g"},
    "sodium":       {"type": "ceiling", "total_key": "total_sodium",       "known_key": "known_sodium_count",       "limit_key": "sodium_mg",      "unit": "mg"},
    "caffeine":     {"type": "ceiling", "total_key": "total_caffeine",     "known_key": "known_caffeine_count",     "limit_key": "caffeine_mg",    "unit": "mg"},
}

# 헤드라인(안전도 카드의 대표 문장) 후보와 최종 동점 처리 순서.
#
# 이 튜플에 있는 키만 헤드라인 후보다 — floor형(탄수화물/에너지/단백질)이 빠져
# 있는 것은 실수가 아니라 설계다. 하루 최소 섭취량은 아침에 스캔하면 당연히
# 미달이라, "단백질이 부족해요"가 경고처럼 보이면 안 된다(tier="neutral").
# band형(지방/철분)은 상한 초과일 때만 후보가 된다 — 하한 미달(status="low")은
# floor형과 같은 이유로 tier가 "neutral"이 되어 후보 필터에서 걸러진다.
#
# 순서는 심각도/관심성분/비율이 전부 같을 때만 쓰이는 최후의 결정론적 타이브레이크다.
# 카페인이 첫 번째인 이유는 앱에서 가장 엄격한 기준(200mg)이기 때문.
HEADLINE_TIEBREAK_ORDER = ("caffeine", "sodium", "sugar", "fat", "iron")


def validate_selected_nutrients(selected: list[str] | None) -> str | None:
    """selected_nutrients 입력값을 검증하고 DB 저장용 comma-separated 문자열로 변환한다.

    None(미지정)은 그대로 None을 반환한다 — PUT에서는 "값을 바꾸지 않음"으로,
    회원가입에서는 컬럼을 NULL로 남겨 조회 시 DEFAULT_SELECTED_NUTRIENTS로 해석되게 한다.
    빈 리스트는 유효한 입력(사용자가 4자리를 모두 명시적으로 비움)이며 ""로 저장된다.
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

# 수분 1일 충분섭취량 2300mL: 비임신 여성 기준 2,100mL + 임신부 가산량 200mL
# (질병관리청 국가건강정보포털 「식이영양(임산부)」, 트라이메스터 무관 동일값).
DAILY_WATER_TARGET_ML = 2300.0

TRIMESTER_NOTES = {
    "early": "임신 초기에는 카페인 섭취량과 하루 영양소 기준을 특히 꼼꼼히 확인해 주세요.",
    "middle": "임신 중기에는 당류 섭취가 누적되지 않도록 확인하고, 카페인 섭취량도 함께 관리해 주세요.",
    "late": "임신 후기에는 나트륨과 당류 섭취가 과도하게 누적되지 않도록 주의해 주세요.",
}
