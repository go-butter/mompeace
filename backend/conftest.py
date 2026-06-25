"""
테스트 공용 fixture.

backend/database.py 의 init_db() 는 "mompeace.db" 파일 경로를 하드코딩하고 있어
테스트에서 그대로 호출하면 실제 운영 DB 파일을 건드릴 위험이 있다.
따라서 동일한 스키마를 인메모리(":memory:") SQLite 커넥션에 직접 생성해서 사용한다.
(database.py 자체는 수정하지 않음)
"""
import sqlite3

import pytest


SCHEMA_SQL = """
CREATE TABLE users (
    user_id     INTEGER PRIMARY KEY AUTOINCREMENT,
    nickname    TEXT NOT NULL,
    login_id    TEXT,
    password    TEXT,
    pregnancy_week INTEGER,
    due_date    TEXT,
    allergy_info TEXT,
    interest_ingredients TEXT,
    is_premium  INTEGER DEFAULT 0,
    premium_started_at TEXT,
    premium_updated_at TEXT,
    caffeine_sensitivity_adj REAL DEFAULT 0,
    sugar_sensitivity_adj REAL DEFAULT 0,
    sodium_sensitivity_adj REAL DEFAULT 0,
    created_at  TEXT DEFAULT (datetime('now'))
);

CREATE TABLE food_items (
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
);

CREATE TABLE food_log (
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
    eaten_at      TEXT DEFAULT (datetime('now')),
    created_at    TEXT DEFAULT (datetime('now')),
    feedback      INTEGER DEFAULT 0,
    recommendation_status TEXT,
    reason_nutrient TEXT,
    FOREIGN KEY (user_id) REFERENCES users(user_id)
);

CREATE TABLE user_sensitivity_log (
    log_id         INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id        INTEGER NOT NULL,
    nutrient       TEXT NOT NULL,
    old_adj        REAL NOT NULL,
    new_adj        REAL NOT NULL,
    trigger_reason TEXT,
    created_at     TEXT DEFAULT (datetime('now')),
    FOREIGN KEY (user_id) REFERENCES users(user_id)
);

CREATE TABLE pregnancy_limits (
    limit_id          INTEGER PRIMARY KEY AUTOINCREMENT,
    trimester         TEXT,
    week_min          INTEGER,
    week_max          INTEGER,
    caffeine_limit_mg REAL DEFAULT 200,
    sugar_caution_g   REAL DEFAULT 50,
    sodium_caution_mg REAL DEFAULT 2000,
    note              TEXT
);
"""


@pytest.fixture
def db():
    """
    스키마가 적용된 인메모리 SQLite 커넥션.
    실제 mompeace.db 파일에는 어떤 영향도 주지 않는다.
    """
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA_SQL)
    conn.commit()
    yield conn
    conn.close()


def make_user(db, **overrides):
    """테스트용 사용자 한 명을 생성하고 user_id를 반환한다."""
    defaults = {
        "nickname": "테스트유저",
        "pregnancy_week": 20,
        "caffeine_sensitivity_adj": 0,
        "sugar_sensitivity_adj": 0,
        "sodium_sensitivity_adj": 0,
    }
    defaults.update(overrides)
    cols = ", ".join(defaults.keys())
    placeholders = ", ".join("?" for _ in defaults)
    cursor = db.cursor()
    cursor.execute(
        f"INSERT INTO users ({cols}) VALUES ({placeholders})",
        list(defaults.values()),
    )
    db.commit()
    return cursor.lastrowid


def make_food_log(db, user_id, **overrides):
    """테스트용 food_log 행 한 개를 생성하고 log_id를 반환한다."""
    defaults = {
        "user_id": user_id,
        "food_name": "테스트 음식",
        "feedback": 0,
        "recommendation_status": None,
        "reason_nutrient": None,
    }
    defaults.update(overrides)
    cols = ", ".join(defaults.keys())
    placeholders = ", ".join("?" for _ in defaults)
    cursor = db.cursor()
    cursor.execute(
        f"INSERT INTO food_log ({cols}) VALUES ({placeholders})",
        list(defaults.values()),
    )
    db.commit()
    return cursor.lastrowid
