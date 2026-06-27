import sqlite3

DB_PATH = "mompeace.db"


def get_db():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
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
    add_column_if_not_exists(cursor, "users", "is_premium",         "INTEGER DEFAULT 0")
    add_column_if_not_exists(cursor, "users", "premium_started_at", "TEXT")
    add_column_if_not_exists(cursor, "users", "premium_updated_at", "TEXT")
    add_column_if_not_exists(cursor, "users", "caffeine_sensitivity_adj", "REAL DEFAULT 0")
    add_column_if_not_exists(cursor, "users", "sugar_sensitivity_adj", "REAL DEFAULT 0")
    add_column_if_not_exists(cursor, "users", "sodium_sensitivity_adj", "REAL DEFAULT 0")

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
    add_column_if_not_exists(cursor, "food_items", "allergen_info", "TEXT")
    add_column_if_not_exists(cursor, "food_items", "additive_info", "TEXT")
    add_column_if_not_exists(cursor, "food_items", "data_source", "TEXT")
    add_column_if_not_exists(cursor, "food_items", "notes", "TEXT")

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
            risk_level     TEXT DEFAULT 'safe',
            eaten_at      TEXT DEFAULT (datetime('now', 'localtime')),
            created_at    TEXT DEFAULT (datetime('now', 'localtime')),
            FOREIGN KEY (user_id) REFERENCES users(user_id)
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
    add_column_if_not_exists(cursor, "food_log", "risk_level", "TEXT DEFAULT 'safe'")
    add_column_if_not_exists(cursor, "food_log", "eaten_at", "TEXT DEFAULT (datetime('now', 'localtime'))")
    add_column_if_not_exists(cursor, "food_log", "created_at", "TEXT DEFAULT (datetime('now', 'localtime'))")
    add_column_if_not_exists(cursor, "food_log", "feedback", "INTEGER DEFAULT 0")
    add_column_if_not_exists(cursor, "food_log", "recommendation_status", "TEXT")
    add_column_if_not_exists(cursor, "food_log", "reason_nutrient", "TEXT")

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

    # 5. PregnancyLimit 테이블 (임신 주차별 앱 내부 기준)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS pregnancy_limits (
            limit_id          INTEGER PRIMARY KEY AUTOINCREMENT,
            trimester         TEXT,
            week_min          INTEGER,
            week_max          INTEGER,
            caffeine_limit_mg REAL DEFAULT 200,
            sugar_caution_g   REAL DEFAULT 50,
            sodium_caution_mg REAL DEFAULT 2000,
            note              TEXT
        )
    """)

    # 기존 pregnancy_limits 테이블에 컬럼이 없을 경우 자동 추가
    add_column_if_not_exists(cursor, "pregnancy_limits", "trimester", "TEXT")
    add_column_if_not_exists(cursor, "pregnancy_limits", "week_min", "INTEGER")
    add_column_if_not_exists(cursor, "pregnancy_limits", "week_max", "INTEGER")
    add_column_if_not_exists(cursor, "pregnancy_limits", "caffeine_limit_mg", "REAL DEFAULT 200")
    add_column_if_not_exists(cursor, "pregnancy_limits", "sugar_caution_g", "REAL DEFAULT 50")
    add_column_if_not_exists(cursor, "pregnancy_limits", "sodium_caution_mg", "REAL DEFAULT 2000")
    add_column_if_not_exists(cursor, "pregnancy_limits", "note", "TEXT")

    # 기본 임신 주차별 기준 데이터 삽입/갱신
    # 주의: 아래 수치는 공식 임신 주차별 의학 기준이 아니라,
    # 공신력 있는 1일 권고량을 바탕으로 앱 내부에서 보수적으로 설정한 판정 기준임.
    cursor.execute("DELETE FROM pregnancy_limits")

    cursor.executemany("""
        INSERT INTO pregnancy_limits
        (
            trimester,
            week_min,
            week_max,
            caffeine_limit_mg,
            sugar_caution_g,
            sodium_caution_mg,
            note
        )
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, [
        (
            "early",
            1,
            12,
            200,
            30,
            2000,
            "임신 초기에는 카페인 섭취량과 알레르기 유발 성분을 특히 꼼꼼히 확인해 주세요."
        ),
        (
            "middle",
            13,
            27,
            200,
            40,
            2000,
            "임신 중기에는 당류 섭취가 누적되지 않도록 확인하고, 카페인 섭취량도 함께 관리해 주세요."
        ),
        (
            "late",
            28,
            42,
            200,
            30,
            1800,
            "임신 후기에는 나트륨과 당류 섭취가 과도하게 누적되지 않도록 주의해 주세요."
        ),
    ])

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


def cleanup_expired_food_logs(db):
    """
    프리미엄 여부에 따라 만료된 food_log 행을 삭제한다.
    - 일반 사용자(is_premium=0 또는 NULL): 24시간 초과 삭제
    - 프리미엄 사용자(is_premium=1): 7일 초과 삭제
    food_items 는 절대 삭제하지 않는다.
    """
    cursor = db.cursor()
    cursor.execute("""
        DELETE FROM food_log
        WHERE user_id IN (
            SELECT user_id FROM users WHERE is_premium = 0 OR is_premium IS NULL
        )
        AND eaten_at < datetime('now', 'localtime', '-1 day')
    """)
    cursor.execute("""
        DELETE FROM food_log
        WHERE user_id IN (
            SELECT user_id FROM users WHERE is_premium = 1
        )
        AND eaten_at < datetime('now', 'localtime', '-7 days')
    """)
    db.commit()