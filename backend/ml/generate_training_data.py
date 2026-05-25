"""
합성 학습 데이터 생성기

food_items 테이블의 실제 API 기반 식품 데이터로 합성 시나리오를 생성하고
규칙 기반 라벨을 부여하여 RandomForest 초기 학습 데이터를 만든다.

주의:
- GI CSV 소스(식약처+Sydney GI, 추정)는 제외
- caffeine_mg = None 은 missing 으로 처리 (절대 0으로 변환하지 않음)
- 이 데이터는 공식 의학 기준이 아닌 앱 내부 보수적 판정 기준 기반임
"""
import csv
import random
import sqlite3
from collections import Counter
from pathlib import Path

# 프로젝트 루트 기준 경로
_HERE = Path(__file__).resolve()
PROJECT_ROOT = _HERE.parent.parent.parent
DB_PATH = PROJECT_ROOT / "mompeace.db"
OUTPUT_PATH = _HERE.parent / "training_recommendation_data.csv"

# 학습 허용 소스 (allowlist 방식)
ALLOWED_TRAINING_SOURCES = {"dish_db_download", "food_qr_api"}
# 학습 제외 소스 (참고용): 식약처+Sydney GI, 추정, processed_food_db_download, food_nutrition_api

# 트라이메스터별 1일 허용 기준 (앱 내부 보수적 기준)
DAILY_LIMITS = {
    "early":  {"caffeine": 200.0, "sugar": 30.0,  "sodium": 2000.0},
    "middle": {"caffeine": 200.0, "sugar": 40.0,  "sodium": 2000.0},
    "late":   {"caffeine": 200.0, "sugar": 30.0,  "sodium": 1800.0},
}

TRIMESTER_ENCODE = {"early": 0, "middle": 1, "late": 2}

# 시나리오 파라미터
WEEK_SCENARIOS = [10, 21, 32]               # early / middle / late 대표 주차
INTAKE_RATIOS = [0.0, 0.3, 0.5, 0.8, 1.1]  # 오늘 누적 섭취 비율 (0%~110%)
ALLERGY_POSITIVE_RATE = 0.3                 # allergy_match = 1 확률

FEATURE_COLUMNS = [
    "pregnancy_week",
    "trimester_encoded",
    "food_caffeine_mg",
    "food_sugar_g",
    "food_sodium_mg",
    "food_carbohydrate_g",
    "food_protein_g",
    "caffeine_missing",
    "sugar_missing",
    "sodium_missing",
    "caffeine_keyword_detected",
    "today_caffeine_mg",
    "today_sugar_g",
    "today_sodium_mg",
    "remaining_caffeine_mg",
    "remaining_sugar_g",
    "remaining_sodium_mg",
    "after_caffeine_ratio",
    "after_sugar_ratio",
    "after_sodium_ratio",
    "allergy_match",
]

CAFFEINE_KEYWORDS = [
    "커피", "카페", "카페인", "에스프레소", "라떼", "모카", "콜드브루",
    "녹차", "말차", "홍차", "초콜릿", "초코", "코코아", "콜라",
    "에너지드링크", "과라나",
]


def _detect_caffeine_keywords(food_name: str) -> list:
    if not food_name:
        return []
    return [kw for kw in CAFFEINE_KEYWORDS if kw in food_name]


def _get_trimester(week: int) -> str:
    if week <= 12:
        return "early"
    elif week <= 27:
        return "middle"
    return "late"


def _generate_label(row: dict) -> str:
    """규칙 기반 라벨 생성 (우선순위 순서대로 적용)"""
    if row["allergy_match"] == 1:
        return "avoid"

    # 알려진 영양소 기준 초과 → avoid
    if (row["after_caffeine_ratio"] > 1.0 or
            row["after_sugar_ratio"] > 1.0 or
            row["after_sodium_ratio"] > 1.0):
        return "avoid"

    # 알려진 비율이 70% 이상 → caution
    if (row["after_caffeine_ratio"] > 0.7 or
            row["after_sugar_ratio"] > 0.7 or
            row["after_sodium_ratio"] > 0.7):
        return "caution"

    # 카페인 unknown + 음식명 키워드 → caution (함량 확인 필요)
    if row["caffeine_missing"] == 1 and row["caffeine_keyword_detected"] == 1:
        return "caution"

    # 당류 또는 나트륨 정보 없음 → caution
    if row["sugar_missing"] == 1 or row["sodium_missing"] == 1:
        return "caution"

    return "possible"


def _generate_scenarios(food: dict) -> list:
    """식품 1개로 15개 시나리오 생성 (3 trimesters × 5 intake levels)"""
    rows = []
    food_name = food.get("food_name") or ""
    caffeine_keywords = _detect_caffeine_keywords(food_name)
    caffeine_keyword_detected = 1 if caffeine_keywords else 0

    # 허용 소스(dish_db_download, food_qr_api)만 학습에 사용:
    # caffeine_mg is None → missing, 실수 값 → 실제 카페인
    raw_caffeine = food.get("caffeine_mg")
    caffeine_missing = 1 if raw_caffeine is None else 0
    food_caffeine = raw_caffeine if raw_caffeine is not None else 0.0

    # sugar_g / sodium_mg: DB 에 0 으로 저장된 경우 실제 0 으로 처리
    raw_sugar = food.get("sugar_g")
    sugar_missing = 1 if raw_sugar is None else 0
    food_sugar = raw_sugar if raw_sugar is not None else 0.0

    raw_sodium = food.get("sodium_mg")
    sodium_missing = 1 if raw_sodium is None else 0
    food_sodium = raw_sodium if raw_sodium is not None else 0.0

    food_carb = food.get("carbohydrate_g") or 0.0
    food_protein = food.get("protein_g") or 0.0

    for week in WEEK_SCENARIOS:
        trimester = _get_trimester(week)
        trimester_encoded = TRIMESTER_ENCODE[trimester]
        limits = DAILY_LIMITS[trimester]
        caffeine_limit = limits["caffeine"]
        sugar_limit = limits["sugar"]
        sodium_limit = limits["sodium"]

        for idx, intake_ratio in enumerate(INTAKE_RATIOS):
            random.seed((food.get("food_id") or 0) * 1000 + WEEK_SCENARIOS.index(week) * 10 + idx)
            allergy_match = 1 if random.random() < ALLERGY_POSITIVE_RATE else 0

            today_caffeine = round(caffeine_limit * intake_ratio, 2)
            today_sugar = round(sugar_limit * intake_ratio, 2)
            today_sodium = round(sodium_limit * intake_ratio, 2)

            remaining_caffeine = max(0.0, caffeine_limit - today_caffeine)
            remaining_sugar = max(0.0, sugar_limit - today_sugar)
            remaining_sodium = max(0.0, sodium_limit - today_sodium)

            # ratio: missing 영양소는 0 으로 수치 계산하되 missing flag 별도 유지
            caffeine_for_ratio = food_caffeine if not caffeine_missing else 0.0
            sugar_for_ratio = food_sugar if not sugar_missing else 0.0
            sodium_for_ratio = food_sodium if not sodium_missing else 0.0

            after_caffeine_ratio = (today_caffeine + caffeine_for_ratio) / caffeine_limit
            after_sugar_ratio = (today_sugar + sugar_for_ratio) / sugar_limit
            after_sodium_ratio = (today_sodium + sodium_for_ratio) / sodium_limit

            row = {
                "pregnancy_week": week,
                "trimester_encoded": trimester_encoded,
                "food_caffeine_mg": food_caffeine,
                "food_sugar_g": food_sugar,
                "food_sodium_mg": food_sodium,
                "food_carbohydrate_g": food_carb,
                "food_protein_g": food_protein,
                "caffeine_missing": caffeine_missing,
                "sugar_missing": sugar_missing,
                "sodium_missing": sodium_missing,
                "caffeine_keyword_detected": caffeine_keyword_detected,
                "today_caffeine_mg": today_caffeine,
                "today_sugar_g": today_sugar,
                "today_sodium_mg": today_sodium,
                "remaining_caffeine_mg": remaining_caffeine,
                "remaining_sugar_g": remaining_sugar,
                "remaining_sodium_mg": remaining_sodium,
                "after_caffeine_ratio": round(after_caffeine_ratio, 4),
                "after_sugar_ratio": round(after_sugar_ratio, 4),
                "after_sodium_ratio": round(after_sodium_ratio, 4),
                "allergy_match": allergy_match,
            }
            row["label"] = _generate_label(row)
            rows.append(row)

    return rows


def main():
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    # 허용 소스만 사용 (allowlist 방식)
    placeholders = ",".join("?" for _ in ALLOWED_TRAINING_SOURCES)
    cursor.execute(
        f"SELECT * FROM food_items WHERE data_source IN ({placeholders})",
        list(ALLOWED_TRAINING_SOURCES),
    )
    foods = [dict(row) for row in cursor.fetchall()]
    conn.close()

    print(f"학습 대상 food_items 수: {len(foods)}")
    source_counts = Counter(f.get("data_source") or "unknown" for f in foods)
    print("소스별 food_items 수:")
    for src, cnt in sorted(source_counts.items()):
        print(f"  {src}: {cnt}개")
    if "dish_db_download" not in source_counts:
        print("⚠️  dish_db_download 데이터가 없습니다. import_dish_db.py를 먼저 실행하세요.")

    if len(foods) < 5:
        print("⚠️  경고: 식품 데이터가 5개 미만입니다.")
        print("   현재 데이터만으로 진행하지만 모델 품질이 매우 낮을 수 있습니다.")

    all_rows = []
    for food in foods:
        all_rows.extend(_generate_scenarios(food))

    if not all_rows:
        print("❌ 생성된 학습 데이터가 없습니다. food_items에 유효한 데이터가 필요합니다.")
        return

    columns = FEATURE_COLUMNS + ["label"]
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)

    with open(OUTPUT_PATH, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=columns)
        writer.writeheader()
        writer.writerows(all_rows)

    dist = Counter(r["label"] for r in all_rows)
    print(f"총 학습 데이터 수: {len(all_rows)}")
    print(f"라벨 분포: {dict(dist)}")
    print(f"저장 완료: {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
