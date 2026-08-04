import sqlite3

DB_PATH = "mompeace.db"


def get_db():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False, timeout=5)
    conn.row_factory = sqlite3.Row  # dict처럼 사용 가능
    try:
        yield conn
    finally:
        conn.close()


def add_column_if_not_exists(cursor, table_name, column_name, column_definition):
    """
    기존 DB에 컬럼이 없으면 자동으로 추가
    """
    cursor.execute(f"PRAGMA table_info({table_name})")
    columns = [column[1] for column in cursor.fetchall()]

    if column_name not in columns:
        cursor.execute(
            f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_definition}"
        )


# ── DB 초기화 (테이블 생성) ──────────────────────────────
def init_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # 1. User 테이블
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id     INTEGER PRIMARY KEY AUTOINCREMENT,
            nickname    TEXT NOT NULL,
            login_id    TEXT,
            password    TEXT,
            pregnancy_week INTEGER,
            pregnancy_day INTEGER,
            pregnancy_entered_at TEXT,
            due_date    TEXT,
            allergy_info TEXT,
            interest_ingredients TEXT,
            created_at  TEXT DEFAULT (datetime('now'))
        )
    """)

    # 기존 users 테이블에 컬럼이 없을 경우 자동 추가
    add_column_if_not_exists(cursor, "users", "login_id", "TEXT")
    add_column_if_not_exists(cursor, "users", "password", "TEXT")
    add_column_if_not_exists(cursor, "users", "pregnancy_week", "INTEGER")
    add_column_if_not_exists(cursor, "users", "pregnancy_day", "INTEGER")
    add_column_if_not_exists(cursor, "users", "pregnancy_entered_at", "TEXT")
    add_column_if_not_exists(cursor, "users", "due_date", "TEXT")
    add_column_if_not_exists(cursor, "users", "allergy_info", "TEXT")
    add_column_if_not_exists(cursor, "users", "interest_ingredients", "TEXT")
    add_column_if_not_exists(cursor, "users", "caffeine_sensitivity_adj", "REAL DEFAULT 0")
    add_column_if_not_exists(cursor, "users", "sugar_sensitivity_adj", "REAL DEFAULT 0")
    add_column_if_not_exists(cursor, "users", "sodium_sensitivity_adj", "REAL DEFAULT 0")
    # 홈 화면 요약에 표시할 선택 영양소 (최대 4개, comma-separated). 미설정(NULL)이면
    # 앱에서 DEFAULT_SELECTED_NUTRIENTS로 취급한다.
    add_column_if_not_exists(cursor, "users", "selected_nutrients", "TEXT")

    # nickname/login_id 중복 방지 (로그인 시 둘 중 하나로 조회 가능해야 하므로 각각 유일해야 함)
    cursor.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_users_nickname ON users(nickname)")
    cursor.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_users_login_id ON users(login_id)")

    # 2. FoodItem 테이블 (음식 기본 정보)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS food_items (
            food_id        INTEGER PRIMARY KEY AUTOINCREMENT,
            food_code      TEXT,
            food_name      TEXT NOT NULL,
            food_name_en   TEXT,
            barcode        TEXT,
            category       TEXT,
            subcategory    TEXT,
            serving_size_g REAL,
            serving_label  TEXT,
            caffeine_mg    REAL DEFAULT 0,
            sugar_g        REAL DEFAULT 0,
            sodium_mg      REAL DEFAULT 0,
            calories_kcal  REAL DEFAULT 0,
            carbohydrate_g REAL,
            protein_g      REAL,
            fat_g          REAL,
            allergen_info  TEXT,
            additive_info  TEXT,
            data_source    TEXT,
            notes          TEXT,
            updated_at     TEXT DEFAULT (datetime('now'))
        )
    """)

    # 기존 food_items 테이블에 컬럼이 없을 경우 자동 추가
    add_column_if_not_exists(cursor, "food_items", "food_code", "TEXT")
    add_column_if_not_exists(cursor, "food_items", "food_name_en", "TEXT")
    add_column_if_not_exists(cursor, "food_items", "subcategory", "TEXT")
    add_column_if_not_exists(cursor, "food_items", "serving_size_g", "REAL")
    add_column_if_not_exists(cursor, "food_items", "serving_label", "TEXT")
    add_column_if_not_exists(cursor, "food_items", "caffeine_mg", "REAL DEFAULT 0")
    add_column_if_not_exists(cursor, "food_items", "sugar_g", "REAL DEFAULT 0")
    add_column_if_not_exists(cursor, "food_items", "sodium_mg", "REAL DEFAULT 0")
    add_column_if_not_exists(cursor, "food_items", "calories_kcal", "REAL DEFAULT 0")
    add_column_if_not_exists(cursor, "food_items", "carbohydrate_g", "REAL")
    add_column_if_not_exists(cursor, "food_items", "protein_g", "REAL")
    add_column_if_not_exists(cursor, "food_items", "fat_g", "REAL")
    add_column_if_not_exists(cursor, "food_items", "saturated_fat_g", "REAL")
    add_column_if_not_exists(cursor, "food_items", "trans_fat_g", "REAL")
    add_column_if_not_exists(cursor, "food_items", "cholesterol_mg", "REAL")
    add_column_if_not_exists(cursor, "food_items", "allergen_info", "TEXT")
    add_column_if_not_exists(cursor, "food_items", "additive_info", "TEXT")
    add_column_if_not_exists(cursor, "food_items", "data_source", "TEXT")
    add_column_if_not_exists(cursor, "food_items", "notes", "TEXT")

    # 2-1. UserFoodItem 테이블 (사용자가 직접 입력한 개인 음식 정보, food_items 카탈로그와 분리)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS user_food_items (
            user_food_item_id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id        INTEGER NOT NULL,
            food_name       TEXT NOT NULL,
            caffeine_mg     REAL,
            sugar_g         REAL DEFAULT 0,
            sodium_mg       REAL DEFAULT 0,
            calories_kcal   REAL DEFAULT 0,
            carbohydrate_g  REAL,
            protein_g       REAL,
            fat_g           REAL,
            saturated_fat_g REAL,
            trans_fat_g     REAL,
            cholesterol_mg  REAL,
            created_at      TEXT DEFAULT (datetime('now', 'localtime')),
            FOREIGN KEY (user_id) REFERENCES users(user_id)
        )
    """)

    # 기존 user_food_items 테이블에 컬럼이 없을 경우 자동 추가
    add_column_if_not_exists(cursor, "user_food_items", "fat_g", "REAL")
    add_column_if_not_exists(cursor, "user_food_items", "saturated_fat_g", "REAL")
    add_column_if_not_exists(cursor, "user_food_items", "trans_fat_g", "REAL")
    add_column_if_not_exists(cursor, "user_food_items", "cholesterol_mg", "REAL")

    # 3. FoodLog 테이블 (사용자 섭취 기록)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS food_log (
            log_id        INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id       INTEGER NOT NULL,
            food_id       INTEGER,
            food_name     TEXT NOT NULL,
            category      TEXT,
            input_type    TEXT,
            amount        REAL DEFAULT 1,
            unit          TEXT DEFAULT '개',
            caffeine_mg    REAL DEFAULT 0,
            sugar_g        REAL DEFAULT 0,
            sodium_mg      REAL DEFAULT 0,
            calories_kcal  REAL DEFAULT 0,
            carbohydrate_g REAL DEFAULT 0,
            protein_g      REAL DEFAULT 0,
            fat_g          REAL,
            saturated_fat_g REAL,
            trans_fat_g    REAL,
            cholesterol_mg REAL,
            risk_level     TEXT DEFAULT 'safe',
            eaten_at      TEXT DEFAULT (datetime('now', 'localtime')),
            created_at    TEXT DEFAULT (datetime('now', 'localtime')),
            FOREIGN KEY (user_id) REFERENCES users(user_id)
        )
    """)

    # 3-1. FoodLogExtraNutrients 테이블 (food_log 항목별 추가 성분)
    # value는 사용자가 입력한 자유 텍스트(단위 포함, 예: "233g", "약간")를
    # 그대로 저장하는 컬럼이라 REAL이 아닌 TEXT여야 한다. 기존에 REAL로
    # 생성된 테이블이 남아있으면 CREATE TABLE IF NOT EXISTS로는 바뀌지
    # 않으므로, 데이터가 없는 구 스키마 테이블은 한 번 드롭하고 새로 만든다.
    cursor.execute("PRAGMA table_info(food_log_extra_nutrients)")
    existing_columns = cursor.fetchall()
    value_column = next((col for col in existing_columns if col[1] == "value"), None)
    if value_column is not None and value_column[2].upper() == "REAL":
        cursor.execute("DROP TABLE food_log_extra_nutrients")

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS food_log_extra_nutrients (
            extra_nutrient_id INTEGER PRIMARY KEY AUTOINCREMENT,
            food_log_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            value TEXT NOT NULL,
            unit TEXT,
            FOREIGN KEY (food_log_id) REFERENCES food_log(log_id)
        )
    """)

    # 기존 food_log 테이블에 컬럼이 없을 경우 자동 추가
    add_column_if_not_exists(cursor, "food_log", "category", "TEXT")
    add_column_if_not_exists(cursor, "food_log", "input_type", "TEXT")
    add_column_if_not_exists(cursor, "food_log", "amount", "REAL DEFAULT 1")
    add_column_if_not_exists(cursor, "food_log", "unit", "TEXT DEFAULT '개'")
    add_column_if_not_exists(cursor, "food_log", "caffeine_mg", "REAL DEFAULT 0")
    add_column_if_not_exists(cursor, "food_log", "sugar_g", "REAL DEFAULT 0")
    add_column_if_not_exists(cursor, "food_log", "sodium_mg", "REAL DEFAULT 0")
    add_column_if_not_exists(cursor, "food_log", "calories_kcal", "REAL DEFAULT 0")
    add_column_if_not_exists(cursor, "food_log", "carbohydrate_g", "REAL DEFAULT 0")
    add_column_if_not_exists(cursor, "food_log", "protein_g", "REAL DEFAULT 0")
    add_column_if_not_exists(cursor, "food_log", "fat_g", "REAL")
    add_column_if_not_exists(cursor, "food_log", "saturated_fat_g", "REAL")
    add_column_if_not_exists(cursor, "food_log", "trans_fat_g", "REAL")
    add_column_if_not_exists(cursor, "food_log", "cholesterol_mg", "REAL")
    add_column_if_not_exists(cursor, "food_log", "risk_level", "TEXT DEFAULT 'safe'")
    add_column_if_not_exists(cursor, "food_log", "eaten_at", "TEXT DEFAULT (datetime('now', 'localtime'))")
    add_column_if_not_exists(cursor, "food_log", "created_at", "TEXT DEFAULT (datetime('now', 'localtime'))")
    add_column_if_not_exists(cursor, "food_log", "feedback", "INTEGER DEFAULT 0")
    add_column_if_not_exists(cursor, "food_log", "recommendation_status", "TEXT")
    add_column_if_not_exists(cursor, "food_log", "reason_nutrient", "TEXT")
    add_column_if_not_exists(cursor, "food_log", "needs_review", "INTEGER DEFAULT 0")

    # 3-2. WaterLog 테이블 (사용자 수분 섭취 기록)
    # amount_ml은 사용자가 직접 입력하는 값(1잔 버튼 또는 커스텀 입력)이라 데이터 소스 결측이
    # 존재하지 않으므로 food_log의 영양소 컬럼과 달리 NOT NULL. 기록이 없는 날의 합계는
    # COALESCE(SUM(amount_ml), 0)으로 계산되는 진짜 0이며, unknown 카운트가 필요 없다.
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS water_log (
            log_id      INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id     INTEGER NOT NULL,
            amount_ml   REAL NOT NULL,
            logged_at   TEXT DEFAULT (datetime('now', 'localtime')),
            created_at  TEXT DEFAULT (datetime('now', 'localtime')),
            FOREIGN KEY (user_id) REFERENCES users(user_id)
        )
    """)

    # 4. UserSensitivityLog 테이블 (사용자별 민감도 조정 이력)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS user_sensitivity_log (
            log_id         INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id        INTEGER NOT NULL,
            nutrient       TEXT NOT NULL,
            old_adj        REAL NOT NULL,
            new_adj        REAL NOT NULL,
            trigger_reason TEXT,
            created_at     TEXT DEFAULT (datetime('now')),
            FOREIGN KEY (user_id) REFERENCES users(user_id)
        )
    """)

    # food_nutrition_api 소스는 카페인 미제공 API임.
    # 구 food_repository.py 가 caffeine_mg = 0 으로 잘못 저장한 레코드를 NULL 로 정정.
    cursor.execute("""
        UPDATE food_items
        SET caffeine_mg = NULL
        WHERE data_source = 'food_nutrition_api'
          AND caffeine_mg = 0
    """)
    migrated = cursor.rowcount
    if migrated > 0:
        print(f"🔧 caffeine_mg 마이그레이션: food_nutrition_api {migrated}행 → NULL 처리")

    conn.commit()
    conn.close()
    print("✅ DB 초기화 완료")
