import sqlite3
from datetime import date

from backend.nutrition_constants import (
    BASE_ENERGY_KCAL,
    BASE_PROTEIN_G,
    DAILY_CAFFEINE_LIMIT_MG,
    DAILY_CARB_MINIMUM_G,
    DAILY_PROJECTION_NUTRIENTS,
    DAILY_SODIUM_LIMIT_MG,
    DAILY_SUGAR_LIMIT_G,
    DEFAULT_AGE_BRACKET,
    HEADLINE_TIEBREAK_ORDER,
    FAT_ENERGY_RATIO_MAX,
    FAT_ENERGY_RATIO_MIN,
    IRON_RECOMMENDED_MG,
    IRON_UPPER_LIMIT_MG,
    KCAL_PER_GRAM_FAT,
    NUTRIENT_LABELS_KO,
    NUTRIENT_STATUS_TYPE,
    PANEL_NUTRIENT_KEYS,
    SATURATED_FAT_ENERGY_RATIO_MAX,
    TRANS_FAT_ENERGY_RATIO_MAX,
    TRIMESTER_ENERGY_ADD_KCAL,
    TRIMESTER_NOTES,
    TRIMESTER_PROTEIN_ADD_G,
)
from backend.risk import calculate_current_pregnancy_age


def compute_today_intake_totals(user_id: int, db: sqlite3.Connection) -> dict:
    """오늘 누적 섭취량(카페인/당류/나트륨)을 합산한다. /recommendations, 음식 기록 추천 판정에서 공유."""
    cursor = db.cursor()
    today = date.today().isoformat()
    cursor.execute("""
        SELECT
            COALESCE(SUM(caffeine_mg), 0) AS total_caffeine,
            COALESCE(SUM(CASE WHEN caffeine_mg IS NULL THEN 1 ELSE 0 END), 0) AS unknown_caffeine_count,
            COALESCE(SUM(sugar_g), 0)    AS total_sugar,
            COALESCE(SUM(CASE WHEN sugar_g IS NULL THEN 1 ELSE 0 END), 0) AS unknown_sugar_count,
            COALESCE(SUM(sodium_mg), 0)  AS total_sodium,
            COALESCE(SUM(CASE WHEN sodium_mg IS NULL THEN 1 ELSE 0 END), 0) AS unknown_sodium_count
        FROM food_log
        WHERE user_id = ? AND DATE(eaten_at) = ?
    """, (user_id, today))
    row = dict(cursor.fetchone())
    return {
        "caffeine_mg": row["total_caffeine"],
        "sugar_g": row["total_sugar"],
        "sodium_mg": row["total_sodium"],
        "unknown_caffeine_count": row["unknown_caffeine_count"],
        "unknown_sugar_count": row["unknown_sugar_count"],
        "unknown_sodium_count": row["unknown_sodium_count"],
    }


def _is_data_unresolved(known_count: int, logged_count: int) -> bool:
    """오늘 무언가는 기록됐는데(logged_count>0) 이 영양소 값이 하나도 확인되지
    않은 경우(known_count==0)에만 unknown으로 판정한다. 아예 기록이 없는 날
    (logged_count==0)은 이 함수가 관여하지 않고, 호출부의 기존 기본 판정
    (ceiling은 0으로 계산되어 safe, floor/band는 각자의 기존 로직)을 그대로 따른다 —
    그렇지 않으면 음식을 하나도 기록하지 않은 날조차 "정보없음"으로 보이게 된다.
    """
    return logged_count > 0 and known_count == 0


def get_status(value, standard, known_count, logged_count) -> str:
    """단일 영양소 섭취 상태 판정 (safe/caution/avoid/unknown)."""
    if _is_data_unresolved(known_count, logged_count):
        return "unknown"

    if standard <= 0:
        return "unknown"

    ratio = value / standard

    if ratio <= 0.7:
        return "safe"
    elif ratio <= 1.0:
        return "caution"
    else:
        return "avoid"


def compute_overall_status(*statuses) -> str:
    """여러 영양소 상태를 종합한 전체 상태 (avoid > unknown > caution > safe).

    "info"(콜레스테롤처럼 판정 자체가 없는 참고용 수치)는 집계에서 제외한다.
    하한선 미달 상태("insufficient", 탄수화물·단백질·에너지·물 — 이진 판정)와
    "low"(지방 밴드 판정의 하한 쪽 전용)는 caution과 동급으로만 취급하며 avoid로는
    절대 올라가지 않는다 — 미달은 초과보다 약한 신호로 다루기로 한 정책 결정.
    """
    filtered = [s for s in statuses if s is not None and s != "info"]
    if not filtered:
        return "safe"

    if "avoid" in filtered:
        return "avoid"
    if "unknown" in filtered:
        return "unknown"

    CAUTION_EQUIVALENT = {"caution", "low", "insufficient"}
    if any(s in CAUTION_EQUIVALENT for s in filtered):
        return "caution"
    return "safe"


def get_floor_status(value, minimum, known_count, logged_count) -> str:
    """하한선(최소 섭취 권장량) 기준 상태 판정 — 탄수화물/단백질/에너지처럼
    "초과"가 아니라 "미달"이 문제인 영양소용. get_status()의 상한선 판정과는
    방향이 반대이므로 별도 함수로 분리한다.

    공식 기준이 목표치 하나뿐이라(완충 구간에 대한 별도 기준이 없음) 중간 단계
    없는 이진 판정이다: sufficient: 최소량 이상 / insufficient: 최소량 미만
    """
    if _is_data_unresolved(known_count, logged_count):
        return "unknown"
    if minimum <= 0:
        return "unknown"

    ratio = value / minimum

    if ratio >= 1.0:
        return "sufficient"
    else:
        return "insufficient"


def get_informational_status(value) -> str:
    """공식 상한 기준이 없어 safe/caution/avoid 판정 자체를 하지 않는 영양소용.
    값이 있으면 "info"(참고용 표시), 없으면 "unknown".

    현재 호출하는 곳은 없다(콜레스테롤이 판정 대상에서 제외되며 유일한 사용처가
    사라짐) — 향후 공식 기준이 없는 영양소가 다시 생기면 재사용할 수 있어 남겨둔다."""
    return "unknown" if value is None else "info"


def get_fat_status(value, energy_basis_kcal, ratio_min, ratio_max, known_count, logged_count) -> str:
    """총 지방처럼 상한(ratio_max)과 하한(ratio_min)이 모두 있는 "밴드"형 판정.

    ── energy_basis_kcal에 무엇을 넘길 것인가 (호출부마다 다르다) ──
    이 함수는 "주어진 에너지 기준의 몇 %가 지방인가"만 계산한다. 그 기준을 무엇으로
    잡을지는 호출부의 책임이고, 질문이 다르면 답도 달라야 한다:

    - 하루 누적 판정(홈/Food Diary 요약, 리포트, OCR 확인 화면의 일일 투영):
      반드시 "하루 에너지 목표"(limits["energy_kcal"])를 넘긴다. 출처 기준
      (임신_시기별_영양소_섭취기준)의 15~30%는 "하루치 총 섭취량"에 대한 비율이므로,
      하루가 채 지나지 않은 시점의 누적 섭취량을 분모로 쓰면 기준을 오용하는 것이다 —
      아침에는 분모가 작아서 지방이 조금만 있는 음식 하나에도 상한을 넘겨버린다.
      목표를 분모로 쓰면 그날의 상한이 나트륨 2300mg/당류 50g처럼 고정된 숫자가 된다.

    - 단일 품목 판정(get_item_nutrient_status, /ocr/alternatives): 그 품목 자신의
      에너지를 넘긴다. 여기서 묻는 것은 "오늘 하루가 어떤가"가 아니라 "이 제품이
      지방 위주인가"이고, 그건 사용자의 하루가 아니라 제품의 성질이다. 분자와 분모가
      같은 배율로 움직이므로 인분 크기가 달라져도 판정이 변하지 않는다(의도된 성질,
      test_item_nutrient_status.py에서 검증).

    energy_basis_kcal * ratio는 kcal 단위이므로, food_log에 그램 단위로 저장된
    value와 비교하려면 KCAL_PER_GRAM_FAT(9kcal/g)로 나눠 그램 기준으로 환산해야
    한다 — 환산 없이 비교하면 사실상 도달 불가능한 상한과, 정상 섭취량도 걸리는
    하한이 되어버린다.

    상한 초과는 get_status()의 기존 safe/caution/avoid 티어를 그대로 재사용하고,
    하한 미달은 별도로 "low"를 반환한다 (미달은 초과보다 약한 신호로 다루는 정책상
    avoid로 올라가지 않음 — compute_overall_status 참고).

    energy_basis_kcal <= 0 가드는 단일 품목 경로에서만 도달 가능하다(하루 에너지
    목표는 항상 1900kcal 이상). 라벨에 열량이 없는 품목이 0으로 들어오는 경우다.
    """
    if _is_data_unresolved(known_count, logged_count):
        return "unknown"
    if energy_basis_kcal <= 0:
        return "unknown"

    upper_limit_g = energy_basis_kcal * ratio_max / KCAL_PER_GRAM_FAT
    ceiling_status = get_status(value, upper_limit_g, known_count=1, logged_count=1)
    if ceiling_status in ("caution", "avoid"):
        return ceiling_status

    lower_limit_g = energy_basis_kcal * ratio_min / KCAL_PER_GRAM_FAT
    if value < lower_limit_g:
        return "low"
    return "safe"


def get_iron_status(value, recommended, upper_limit, known_count, logged_count) -> str:
    """철분처럼 권장량(하한)과 상한섭취량이 모두 있는 "밴드"형 판정.
    fat(get_fat_status)과 달리 절대 mg 기준이라 에너지 비율 환산이 필요 없다.
    """
    if _is_data_unresolved(known_count, logged_count):
        return "unknown"

    ceiling_status = get_status(value, upper_limit, known_count=1, logged_count=1)
    if ceiling_status in ("caution", "avoid"):
        return ceiling_status

    if value < recommended:
        return "low"
    return "safe"


_CEILING_LABELS = {"safe": "여유", "caution": "안전", "avoid": "위험", "unknown": "정보없음"}
_FLOOR_LABELS = {"sufficient": "충분", "insufficient": "부족", "unknown": "정보없음"}
_BAND_LABELS = {"safe": "여유", "low": "부족", "caution": "안전", "avoid": "위험", "unknown": "정보없음"}


def simplified_status_label(nutrient_type: str, status: str) -> str | None:
    """홈 화면 요약 카드용 간소화 라벨 (여유/안전/위험/정보없음 계열).

    Food Diary용 status_label()(routers/intake.py, caution="주의")과는 별도의
    홈 화면 전용 어휘다.

    nutrient_type:
    - "ceiling": get_status() 결과용 (caffeine/sugar/sodium)
    - "floor": get_floor_status() 결과용 (carbohydrate/protein/energy/water) — 공식
      기준이 목표치 하나뿐이라 완충 구간 없는 이진 판정(충분/부족)이다
    - "band": get_fat_status()/get_iron_status() 결과용 (fat/iron) — safe/caution/avoid는
      ceiling과 같은 어휘, low(하한 미달)는 floor와 같은 의미이므로 같은 단어("부족")를 재사용한다
    - "informational": get_informational_status() 결과용 (공식 상한 기준이 없는 영양소) — "info"는
      판정 자체가 없으므로 라벨 없이 None을 반환한다 (숫자만 표시, 칩 없음). 현재 실제 호출처 없음.
    """
    if nutrient_type == "ceiling":
        return _CEILING_LABELS.get(status, "정보없음")
    if nutrient_type == "floor":
        return _FLOOR_LABELS.get(status, "정보없음")
    if nutrient_type == "band":
        return _BAND_LABELS.get(status, "정보없음")
    if nutrient_type == "informational":
        return None if status == "info" else "정보없음"
    raise ValueError(f"알 수 없는 nutrient_type: {nutrient_type}")


# /intake/summary와 리포트가 공유하는 "사전 해석된" 영양소 항목 정의.
# unit은 여기에 다시 적지 않고 DAILY_PROJECTION_NUTRIENTS의 값을 읽는다 — 단위 문자열이
# 이미 여러 표에 흩어져 있어 새 사본을 하나 더 만들지 않기 위해서다.
# band형(지방/철분)은 부가 인자가 서로 달라 자신만의 판정 함수를 judge_fn으로 들고 다닌다.
NUTRIENT_SUMMARY_FIELDS = {
    "carbohydrate": {"type": "floor",   "limit_key": "carbohydrate_g"},
    "sugar":        {"type": "ceiling", "limit_key": "sugar_g"},
    "energy":       {"type": "floor",   "limit_key": "energy_kcal"},
    "fat":          {"type": "band",    "limit_key": None,
                     "judge_fn": lambda value, known_count, logged_count, limits: get_fat_status(
                         value, limits["energy_kcal"], limits["fat_ratio_min"], limits["fat_ratio_max"],
                         known_count, logged_count)},
    "iron":         {"type": "band",    "limit_key": None,
                     "judge_fn": lambda value, known_count, logged_count, limits: get_iron_status(
                         value, IRON_RECOMMENDED_MG, IRON_UPPER_LIMIT_MG, known_count, logged_count)},
    "protein":      {"type": "floor",   "limit_key": "protein_g"},
    "sodium":       {"type": "ceiling", "limit_key": "sodium_mg"},
    "caffeine":     {"type": "ceiling", "limit_key": "caffeine_mg"},
}


def _summary_percent(value, standard):
    """routers/intake.py의 _get_percent와 같은 규칙(None/0 이하는 0)."""
    if standard is None or standard <= 0:
        return 0
    return round(value / standard * 100, 1)


def build_nutrient_summary_item(
    key: str, value: float, limits: dict, known_count: int, logged_count: int
) -> dict:
    """영양소 하나의 {key,label,total,unit,limit,percent,status,status_label} 항목.

    판정 대상 수치를 호출부가 value로 직접 넘긴다 — 하루 합계를 넘기면 일간 판정이,
    일평균을 넘기면 기간 일평균 판정이 된다. 집계 딕셔너리의 컬럼명이 호출부마다
    달라도(예: total_calories vs total_energy) 이 함수는 영향을 받지 않는다.

    total/percent는 _is_data_unresolved(known_count, logged_count)일 때(무언가는
    기록됐는데 이 영양소만 하나도 확인되지 않음) None을 반환한다 — 정보 없음을
    0으로 노출하지 않기 위해서다(build_daily_projected_statuses의 exposed_value와
    동일한 원칙). 기록 자체가 없는 날(logged_count==0)은 그대로 0을 노출한다.
    """
    spec = NUTRIENT_SUMMARY_FIELDS[key]
    unresolved = _is_data_unresolved(known_count, logged_count)
    exposed_total = None if unresolved else round(value, 2)

    if spec["type"] == "band":
        status = spec["judge_fn"](value, known_count, logged_count, limits)
        limit = None
        percent = None
    else:
        limit = limits[spec["limit_key"]]
        judge = get_status if spec["type"] == "ceiling" else get_floor_status
        status = judge(value, limit, known_count, logged_count)
        percent = None if exposed_total is None else _summary_percent(value, limit)

    return {
        "key": key,
        "label": NUTRIENT_LABELS_KO[key],
        "total": exposed_total,
        "unit": DAILY_PROJECTION_NUTRIENTS[key]["unit"],
        "limit": limit,
        "percent": percent,
        "status": status,
        "status_label": simplified_status_label(spec["type"], status),
    }


## 추천 화면 상단 패널 ────────────────────────────────────────
# 카페인(항상) + 사용자가 고른 영양소를 한 리스트로 돌려준다. build_nutrient_summary_item과
# 형제 관계지만 답하는 질문이 다르다: 저쪽은 "오늘 얼마나 먹었나"(total/percent 중심),
# 이쪽은 "앞으로 얼마나 더 먹어도/먹어야 하나"(remaining 중심)다. 방향은 새로 정의하지
# 않고 NUTRIENT_SUMMARY_FIELDS의 type을 그대로 읽는다 — NUTRIENT_STATUS_TYPE에는 카페인이
# 없어서(nutrition_constants.py 상단 주석 참고) 그쪽을 쓰면 카페인만 특례가 되어야 한다.


def _band_bounds(key: str, limits: dict) -> tuple[float, float]:
    """band형 영양소의 (하한, 상한). 새 기준값을 만들지 않고 기존 상수/한도에서 유도한다 —
    철분은 KDRI 권장량/상한섭취량 상수를 그대로, 지방은 get_fat_status가 쓰는 것과 똑같은
    식(하루 에너지 목표 * 비율 / 9kcal)을 쓴다."""
    if key == "iron":
        return IRON_RECOMMENDED_MG, IRON_UPPER_LIMIT_MG
    if key == "fat":
        energy = limits["energy_kcal"]
        return (
            energy * limits["fat_ratio_min"] / KCAL_PER_GRAM_FAT,
            energy * limits["fat_ratio_max"] / KCAL_PER_GRAM_FAT,
        )
    raise ValueError(f"band형이 아닌 영양소입니다: {key}")


def build_panel_nutrients(selected_keys: list[str], totals: dict, limits: dict) -> list[dict]:
    """카페인 + selected_keys를 하나의 리스트로. 카페인이 항상 첫 번째다.

    각 항목이 자기 방향을 직접 들고 다니므로 호출부(앱)는 어떤 영양소가 상한형이고
    어떤 것이 하한형인지 따로 알 필요가 없다:
    - ceiling: remaining = 남은 허용량, limit 동봉, 0이면 exceeded=True
    - floor:   remaining = 목표까지 더 필요한 양, target 동봉 (limit이라는 이름을 재사용하지
               않는다 — 방향이 반대인 값에 같은 이름을 쓰면 읽는 쪽이 반드시 헷갈린다)
    - band:    remaining=None. 경계가 둘이라 remaining 하나로는 반드시 한쪽을 속이게 된다.
               대신 lower/upper를 동봉해 화면이 숫자를 그릴 수 있게 한다.
    exceeded는 ceiling형에만 True가 될 수 있다. 하한 미달은 "초과"가 아니라 status
    "insufficient"이며, 이 둘을 한 필드로 합치면 방향 구분이 사라진다.
    """
    logged_count = totals["logged_count"]
    keys = ["caffeine"] + [k for k in selected_keys if k != "caffeine"]

    items = []
    for key in keys:
        if key not in PANEL_NUTRIENT_KEYS:
            continue
        spec = NUTRIENT_SUMMARY_FIELDS[key]
        projection = DAILY_PROJECTION_NUTRIENTS[key]
        nutrient_type = spec["type"]
        value = totals[projection["total_key"]]
        known_count = totals[projection["known_key"]]

        # "정보 없음"의 두 가지 경로. 어느 쪽이든 0으로 노출하지 않는다.
        # 1) 오늘 기록은 있는데 이 영양소만 한 번도 확인되지 않음 (_is_data_unresolved).
        # 2) 오늘 아무것도 기록하지 않음(logged_count == 0) — 단, floor/band에만 해당한다.
        #    상한형은 정말로 허용량이 통째로 남아 있으므로 그대로 노출하는 게 사실이다.
        #    반면 "부족하다"는 주장은 데이터가 있어야 할 수 있다. 빈 하루는 부족의
        #    증거가 아니라 데이터의 부재이고, 아침에 아무것도 안 먹은 사용자에게
        #    "단백질 부족"이라고 말하는 것은 측정이 아니라 추측이다.
        #    get_floor_status 자체는 건드리지 않는다 — /intake/summary·리포트·OCR 투영이
        #    그 계약을 그대로 쓰고 있고, 이건 이 패널의 표시 정책이다.
        unresolved = _is_data_unresolved(known_count, logged_count)
        empty_day_guard = logged_count == 0 and nutrient_type in ("floor", "band")

        item = {
            "key": key,
            "label": NUTRIENT_LABELS_KO[key],
            "type": nutrient_type,
            "unit": projection["unit"],
        }

        if unresolved or empty_day_guard:
            item.update({"total": None, "remaining": None, "status": "unknown", "exceeded": False})
        elif nutrient_type == "ceiling":
            limit = limits[spec["limit_key"]]
            remaining = round(max(0.0, limit - value), 2)
            item.update({
                "total": round(value, 2),
                "remaining": remaining,
                "status": get_status(value, limit, known_count, logged_count),
                "exceeded": remaining == 0,
            })
        elif nutrient_type == "floor":
            target = limits[spec["limit_key"]]
            item.update({
                "total": round(value, 2),
                "remaining": round(max(0.0, target - value), 2),
                "status": get_floor_status(value, target, known_count, logged_count),
                "exceeded": False,
            })
        else:  # band
            item.update({
                "total": round(value, 2),
                "remaining": None,
                "status": spec["judge_fn"](value, known_count, logged_count, limits),
                "exceeded": False,
            })

        # 경계값은 방향별로 이름이 다르고, 해당 없는 항목에는 아예 넣지 않는다
        # (null로 넣으면 "값이 없다"와 "이 방향에는 그런 개념이 없다"가 섞인다).
        if nutrient_type == "ceiling":
            item["limit"] = limits[spec["limit_key"]]
        elif nutrient_type == "floor":
            item["target"] = limits[spec["limit_key"]]
        else:
            lower, upper = _band_bounds(key, limits)
            item["lower"] = round(lower, 2)
            item["upper"] = round(upper, 2)

        items.append(item)

    return items


_ITEM_NUTRIENT_UNITS = {
    "carbohydrate": "g",
    "sugar": "g",
    "energy": "kcal",
    "fat": "g",
    "iron": "mg",
    "protein": "g",
    "sodium": "mg",
}


def get_item_nutrient_status(
    key: str,
    value: float | None,
    limits: dict,
    item_energy_kcal: float | None,
) -> str:
    """단일 품목(예: OCR 스캔 결과) 영양소 하나의 상태 판정.

    누적 일일 판정(_build_nutrient_summary_item 등)과 달리 "이 음식 하나"의 값만으로
    판정한다. known_count/logged_count는 food_log.py의 기존 단일 항목 판정 패턴
    (_fetch_food_log_for_date의 caffeine_status 등, "1 if value is not None else 0, 1")과
    동일하게 value의 None 여부로 결정한다 — 로그가 이 품목 하나뿐이므로 logged_count=1 고정.

    floor 타입(탄수화물/에너지/단백질)은 "하루 최소 섭취량" 개념이라 단일 품목에는
    적용할 수 없다 — 어떤 음식 하나도 하루치 최소 탄수화물/단백질/에너지를 채우지
    못하는 게 정상이라, get_floor_status를 그대로 쓰면 거의 모든 품목이 "부족"(→위험)이
    되어버려 의미 있는 신호가 아니다. 제품 결정 사항으로 이 경우 항상 "unknown"을
    반환한다 — 누적 하루 판정은 기존 홈/Food Diary 요약 화면에서 그대로 유지된다.
    """
    nutrient_type = NUTRIENT_STATUS_TYPE[key]
    known_count = 0 if value is None else 1
    logged_count = 1

    if nutrient_type == "floor":
        return "unknown"

    if nutrient_type == "ceiling":
        limit_key = {"sugar": "sugar_g", "sodium": "sodium_mg"}[key]
        return get_status(value, limits[limit_key], known_count, logged_count)

    if key == "iron":
        return get_iron_status(value, IRON_RECOMMENDED_MG, IRON_UPPER_LIMIT_MG, known_count, logged_count)

    if key == "fat":
        # get_fat_status()는 energy_total <= 0만 방어하고 None은 방어하지 않는다
        # (기존 유일한 호출부가 항상 COALESCE(...,0) SQL 합계를 넘겨 None일 수 없었기
        # 때문) — 단일 품목은 에너지 값 자체가 라벨에 없을 수 있으므로 여기서 먼저 막는다.
        if item_energy_kcal is None:
            return "unknown"
        return get_fat_status(
            value, item_energy_kcal, limits["fat_ratio_min"], limits["fat_ratio_max"], known_count, logged_count
        )

    raise ValueError(f"알 수 없는 영양소 키: {key}")


def build_item_nutrient_statuses(nutrients: dict[str, float | None], limits: dict) -> list[dict]:
    """단일 품목(OCR 스캔 결과 등)의 추적 대상 7개 영양소 전부에 대해
    {key, label, unit, status, status_label}을 계산해 리스트로 반환한다.

    nutrients: {"carbohydrate":, "sugar":, "energy":, "fat":, "iron":, "protein":, "sodium":}
      — 라벨이 제공하지 않은 값은 None. 지방 밴드 판정의 에너지 분모는 오늘 누적이
      아니라 이 품목 자신의 nutrients["energy"]를 쓴다 — 단일 품목 판정이므로 "이
      음식에서 지방이 차지하는 칼로리 비율"이 맥락에 맞고, 분자/분모가 같은 품목의
      같은 스케일로 함께 변하므로 인분 크기와 무관하게 비율이 유지된다(문서 참고).
    limits: get_trimester_limits()의 두 번째 반환값(carbohydrate_g/protein_g/energy_kcal/
      fat_ratio_min/fat_ratio_max/sugar_g/sodium_mg 등 포함).

    라벨이 제공하지 않은 영양소도 항목 자체는 항상 포함하고(정보없음 배지로 표시할
    수 있도록) status만 unknown/정보없음으로 채운다 — 존재하는 값만 골라 리스트를
    줄이지 않는다. 반환은 항상 7개 항목이다.
    """
    item_energy_kcal = nutrients.get("energy")
    items = []
    for key in NUTRIENT_STATUS_TYPE:
        value = nutrients.get(key)
        status = get_item_nutrient_status(key, value, limits, item_energy_kcal)
        items.append({
            "key": key,
            "label": NUTRIENT_LABELS_KO[key],
            "unit": _ITEM_NUTRIENT_UNITS[key],
            "status": status,
            "status_label": simplified_status_label(NUTRIENT_STATUS_TYPE[key], status),
        })
    return items


# ── 일일 투영(daily projection) 판정 ─────────────────────────────
# OCR 확인 화면의 "오늘 섭취 안전도" 카드용. 단일 품목만 보는 기존
# build_item_nutrient_statuses()와 달리, "오늘 이미 저장된 누적분 + 지금 확인 중인
# 품목"을 합산해 하루 기준으로 판정한다 — 카드 제목이 "오늘 섭취 안전도"인데
# 품목 하나만 보고 판정하면 양방향으로 틀린다(이미 1400mg 먹은 날의 1710mg
# 나트륨을 114%로, 한도를 넘긴 날의 800mg을 "안전"으로 표시).

# /intake/summary(routers/intake.py)가 쓰던 집계 쿼리를 그대로 옮긴 것.
# 하루 경계 판정 방식(서버 로컬 날짜 + DATE(eaten_at) 문자열 비교)을 두 화면이
# 정확히 공유해야 자정 무렵에 확인 화면과 요약 화면이 어긋나지 않는다.
_DAILY_TOTALS_SQL = """
    SELECT
        COALESCE(SUM(caffeine_mg), 0) AS total_caffeine,
        COUNT(caffeine_mg) AS known_caffeine_count,
        COALESCE(SUM(sugar_g), 0) AS total_sugar,
        COUNT(sugar_g) AS known_sugar_count,
        COALESCE(SUM(sodium_mg), 0) AS total_sodium,
        COUNT(sodium_mg) AS known_sodium_count,
        COALESCE(SUM(calories_kcal), 0) AS total_calories,
        COUNT(calories_kcal) AS known_energy_count,
        COALESCE(SUM(carbohydrate_g), 0) AS total_carbohydrate,
        COUNT(carbohydrate_g) AS known_carbohydrate_count,
        COALESCE(SUM(protein_g), 0) AS total_protein,
        COUNT(protein_g) AS known_protein_count,
        COALESCE(SUM(fat_g), 0) AS total_fat,
        COUNT(fat_g) AS known_fat_count,
        COALESCE(SUM(iron_mg), 0) AS total_iron,
        COUNT(iron_mg) AS known_iron_count,
        COUNT(*) AS logged_count
    FROM food_log
    WHERE user_id = ? AND DATE(eaten_at) = ?
"""


def fetch_daily_nutrient_totals(user_id: int, target_date: str, db) -> dict:
    """하루치 누적 섭취량 + 영양소별 known 개수 + 총 기록 건수.

    COUNT(col)은 NULL을 세지 않으므로 known_*_count는 "그 영양소 값이 실제로
    확인된 기록 수"가 된다 — SUM은 COALESCE로 0이 되지만, known_count==0이면
    _is_data_unresolved()가 unknown으로 처리해 "정보 없음 ≠ 0"이 유지된다.
    """
    cursor = db.cursor()
    cursor.execute(_DAILY_TOTALS_SQL, (user_id, target_date))
    return dict(cursor.fetchone())


# 판정 코드(status)를 화면이 쓰는 심각도 등급(tier)으로 정규화한다.
#
# "neutral"이 이번에 새로 생긴 등급이다: 하한 미달은 "경고"가 아니라 "아직
# 안 채웠음"이라는 중립 상태로 표시한다. 아침에 스캔하면 하루 최소 섭취량은
# 당연히 미달이라, 이걸 경고로 보여주면 "아직 안 먹었을 뿐"인 사용자에게
# 결핍이라고 말하는 셈이 된다.
# - floor형(탄수화물/에너지/단백질)의 insufficient
# - band형(지방/철분)의 low (하한 미달) — ADDITION B: 상한 초과만 경고 대상이고
#   하한 미달은 floor형과 동일하게 취급한다
_TIER_BY_TYPE = {
    "ceiling": {"safe": "safe", "caution": "caution", "avoid": "avoid", "unknown": "unknown"},
    "floor": {"sufficient": "safe", "insufficient": "neutral", "unknown": "unknown"},
    "band": {"safe": "safe", "low": "neutral", "caution": "caution", "avoid": "avoid", "unknown": "unknown"},
}

# 헤드라인 후보가 될 수 있는 등급 — 나쁜 순서대로. neutral/unknown은 없다.
_HEADLINE_TIERS = ("avoid", "caution", "safe")


def tier_of_status(nutrient_type: str, status: str) -> str:
    """status 코드 → 심각도 등급(avoid/caution/safe/neutral/unknown)."""
    return _TIER_BY_TYPE[nutrient_type].get(status, "unknown")


def _project(daily_totals: dict, spec: dict, pending_value: float | None) -> tuple[float, int]:
    """오늘 누적분 + 확인 중인 품목 = 투영값. pending이 None이면 값은 그대로 두고
    known_count도 올리지 않는다 (정보 없음 ≠ 0)."""
    total = daily_totals[spec["total_key"]] + (pending_value or 0)
    known = daily_totals[spec["known_key"]] + (0 if pending_value is None else 1)
    return total, known


def build_daily_projected_statuses(
    pending_values: dict[str, float | None], daily_totals: dict, limits: dict
) -> list[dict]:
    """추적 대상 8개 영양소(DAILY_PROJECTION_NUTRIENTS) 전부에 대해
    "오늘 누적 + 확인 중인 품목" 기준 상태를 계산한다. 항상 8개를 반환한다.

    logged_count에 +1을 하는 이유: 확인 중인 품목도 한 건의 기록으로 세어야
    "오늘 기록이 하나도 없는데 이 품목 값도 없음" 상황이 unknown으로 판정된다
    (_is_data_unresolved는 logged_count>0 && known_count==0일 때만 unknown).
    """
    logged_count = daily_totals["logged_count"] + 1

    items = []
    for key, spec in DAILY_PROJECTION_NUTRIENTS.items():
        nutrient_type = spec["type"]
        value, known_count = _project(daily_totals, spec, pending_values.get(key))

        if nutrient_type == "ceiling":
            limit = limits[spec["limit_key"]]
            status = get_status(value, limit, known_count, logged_count)
        elif nutrient_type == "floor":
            limit = limits[spec["limit_key"]]
            status = get_floor_status(value, limit, known_count, logged_count)
        elif key == "iron":
            # limit은 "경고 기준"인 상한섭취량이다 — 헤드라인 비율 계산도 이 값을 쓴다.
            limit = IRON_UPPER_LIMIT_MG
            status = get_iron_status(
                value, IRON_RECOMMENDED_MG, IRON_UPPER_LIMIT_MG, known_count, logged_count
            )
        elif key == "fat":
            # 분모는 "오늘 누적 에너지"가 아니라 "하루 에너지 목표"다. 기준(15~30%)이
            # 하루치 총 섭취량에 대한 비율이라, 하루가 끝나지 않은 시점의 누적값을
            # 분모로 쓰면 아침에 지방 있는 음식 하나만 먹어도 상한을 넘겨버린다.
            # 목표를 쓰면 그날의 상한이 나트륨 2300mg처럼 고정된 숫자가 된다.
            # 목표는 항상 1900kcal 이상이므로 여기서 0 방어는 필요 없다.
            limit = limits["energy_kcal"] * limits["fat_ratio_max"] / KCAL_PER_GRAM_FAT
            status = get_fat_status(
                value, limits["energy_kcal"], limits["fat_ratio_min"], limits["fat_ratio_max"],
                known_count, logged_count,
            )
        else:
            raise ValueError(f"알 수 없는 영양소 키: {key}")

        # known_count==0이면 값 자체가 없는 것이라 0을 노출하지 않는다 (정보 없음 ≠ 0).
        exposed_value = None if known_count == 0 else round(value, 2)
        percent = (
            round(exposed_value / limit * 100, 1)
            if exposed_value is not None and limit is not None and limit > 0
            else None
        )

        items.append({
            "key": key,
            "label": NUTRIENT_LABELS_KO[key],
            "unit": spec["unit"],
            "value": exposed_value,
            "limit": round(limit, 2) if limit is not None else None,
            "percent": percent,
            "status": status,
            "status_label": simplified_status_label(nutrient_type, status),
            "tier": tier_of_status(nutrient_type, status),
        })
    return items


def _headline_ratio(item: dict) -> float:
    """헤드라인 동점 처리용 "한도 대비 비율". 207%가 102%를 이긴다.

    한도를 모르거나 0 이하면 0.0을 돌려준다 — 0으로 나누는 것을 막기 위한 방어다.
    실제로 도달 가능한 경로가 있다: 지방의 상한은 투영 에너지에서 계산되므로
    에너지가 0이면 상한도 0이 된다.

    하한 미달(band형 "low")용 역비율은 두지 않는다 — ADDITION B로 하한 미달은
    항상 tier="neutral"이 되어 헤드라인 후보 필터에서 걸러지므로, 역비율을
    계산할 일이 애초에 생기지 않는다(도달 불가능한 코드).
    """
    value = item.get("value")
    limit = item.get("limit")
    if value is None or limit is None or limit <= 0:
        return 0.0
    return value / limit


def select_headline_nutrient(statuses: list[dict], preferred_keys) -> dict | None:
    """안전도 카드가 이름을 내걸 영양소 하나를 고른다. 완전히 결정론적이다 —
    입력이 같으면 항상 같은 결과가 나온다(무작위 없음). recompute가 타이핑마다
    디바운스로 재호출되는데 무작위 타이브레이크를 쓰면 글자를 칠 때마다 헤드라인이
    다른 영양소로 튄다.

    순서:
    1. 상한형(cap-type)만 후보 — HEADLINE_TIEBREAK_ORDER에 있는 키만 본다.
       floor형은 애초에 그 튜플에 없고, band형 하한 미달은 tier=="neutral"이라
       아래 등급 필터에서 걸러진다 (두 겹의 독립적인 방어).
    2. 가장 나쁜 등급부터: avoid → caution → safe
    3. 같은 등급 안에서는 사용자가 고른 관심성분 우선
    4. 그래도 같으면 한도 대비 비율이 높은 쪽
    5. 그래도 같으면 HEADLINE_TIEBREAK_ORDER의 고정 순서
    """
    preferred = set(preferred_keys or ())
    candidates = [
        item for item in statuses
        if item["key"] in HEADLINE_TIEBREAK_ORDER and item["tier"] in _HEADLINE_TIERS
    ]
    if not candidates:
        return None

    for tier in _HEADLINE_TIERS:
        at_tier = [item for item in candidates if item["tier"] == tier]
        if not at_tier:
            continue
        best = min(at_tier, key=lambda item: (
            0 if item["key"] in preferred else 1,
            -_headline_ratio(item),
            HEADLINE_TIEBREAK_ORDER.index(item["key"]),
        ))
        return {"key": best["key"], "tier": best["tier"], "label": best["label"]}
    return None


TRIMESTER_LABELS = {"early": "임신 초기", "middle": "임신 중기", "late": "임신 후기"}


def get_trimester_limits(pregnancy_week: int, age_bracket: str = DEFAULT_AGE_BRACKET) -> tuple[str, dict]:
    """트라이메스터 판별 및 1일 허용 기준 조회.

    절대 기준값(카페인/당류/나트륨)은 트라이메스터와 무관하게 항상 동일하다(nutrition_constants 참고).
    에너지/단백질만 age_bracket("19-29"/"30-49")에 따라 baseline이 달라진다.
    트라이메스터별로 달라지는 것은 (에너지/단백질 가산량과) note(안내 문구)다.
    """
    if pregnancy_week <= 12:
        trimester = "early"
    elif pregnancy_week <= 27:
        trimester = "middle"
    else:
        trimester = "late"
    return trimester, {
        "caffeine_mg": DAILY_CAFFEINE_LIMIT_MG,
        "sugar_g":     DAILY_SUGAR_LIMIT_G,
        "sodium_mg":   DAILY_SODIUM_LIMIT_MG,
        "carbohydrate_g": DAILY_CARB_MINIMUM_G,
        "protein_g":   BASE_PROTEIN_G[age_bracket] + TRIMESTER_PROTEIN_ADD_G[trimester],
        "energy_kcal": BASE_ENERGY_KCAL[age_bracket] + TRIMESTER_ENERGY_ADD_KCAL[trimester],
        "fat_ratio_min": FAT_ENERGY_RATIO_MIN,
        "fat_ratio_max": FAT_ENERGY_RATIO_MAX,
        "saturated_fat_ratio_max": SATURATED_FAT_ENERGY_RATIO_MAX,
        "trans_fat_ratio_max": TRANS_FAT_ENERGY_RATIO_MAX,
        "note":        TRIMESTER_NOTES[trimester],
    }


def resolve_user_nutrition_context(user: dict) -> tuple[int, str]:
    """사용자 row에서 get_trimester_limits()에 바로 넘길 (임신 주차, 나이대)를 계산한다.

    임신 주차는 calculate_current_pregnancy_age()로 "오늘" 기준 값을 계산하고,
    미입력이면 20주로 대체한다. 나이대는 미입력(NULL)이면 DEFAULT_AGE_BRACKET으로
    대체한다 — 기존 고정 baseline과 동일해 회귀가 없다.
    """
    computed_age = calculate_current_pregnancy_age(
        user.get("pregnancy_week"), user.get("pregnancy_day"), user.get("pregnancy_entered_at")
    )
    week = computed_age["week"] or 20
    age_bracket = user.get("age_bracket") or DEFAULT_AGE_BRACKET
    return week, age_bracket
