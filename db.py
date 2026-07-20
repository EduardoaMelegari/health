import os
import sqlite3

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.environ.get("DB_PATH", os.path.join(BASE_DIR, "data", "health.db"))

SCHEMA = """
CREATE TABLE IF NOT EXISTS config (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS weight_log (
    id        INTEGER PRIMARY KEY,
    date      TEXT NOT NULL UNIQUE,
    weight_kg REAL NOT NULL,
    note      TEXT
);

CREATE TABLE IF NOT EXISTS task_template (
    id       INTEGER PRIMARY KEY,
    title    TEXT NOT NULL,
    category TEXT NOT NULL,
    weekdays TEXT NOT NULL,
    sort     INTEGER DEFAULT 0,
    active   INTEGER DEFAULT 1
);

CREATE TABLE IF NOT EXISTS task_done (
    id          INTEGER PRIMARY KEY,
    template_id INTEGER NOT NULL REFERENCES task_template(id),
    date        TEXT NOT NULL,
    done_at     TEXT NOT NULL,
    UNIQUE(template_id, date)
);

CREATE TABLE IF NOT EXISTS exercise (
    id          INTEGER PRIMARY KEY,
    workout     TEXT NOT NULL,
    name        TEXT NOT NULL,
    target_sets INTEGER DEFAULT 4,
    target_reps INTEGER DEFAULT 8,
    sort        INTEGER DEFAULT 0,
    active      INTEGER DEFAULT 1
);

CREATE TABLE IF NOT EXISTS set_log (
    id          INTEGER PRIMARY KEY,
    exercise_id INTEGER NOT NULL REFERENCES exercise(id),
    date        TEXT NOT NULL,
    set_number  INTEGER NOT NULL,
    weight_kg   REAL,
    reps        INTEGER
);

CREATE TABLE IF NOT EXISTS meal (
    id   INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    sort INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS meal_option (
    id          INTEGER PRIMARY KEY,
    meal_id     INTEGER NOT NULL REFERENCES meal(id),
    name        TEXT NOT NULL,
    description TEXT,
    sort        INTEGER DEFAULT 0,
    active      INTEGER DEFAULT 1
);

CREATE TABLE IF NOT EXISTS meal_item (
    id         INTEGER PRIMARY KEY,
    option_id  INTEGER NOT NULL REFERENCES meal_option(id),
    food       TEXT NOT NULL,
    grams      REAL NOT NULL,
    raw_factor REAL DEFAULT 1.0,
    protein_g  REAL DEFAULT 0,
    carbs_g    REAL DEFAULT 0,
    fat_g      REAL DEFAULT 0,
    kcal       REAL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS meal_choice (
    id        INTEGER PRIMARY KEY,
    date      TEXT NOT NULL,
    meal_id   INTEGER NOT NULL REFERENCES meal(id),
    option_id INTEGER NOT NULL REFERENCES meal_option(id),
    UNIQUE(date, meal_id)
);

CREATE TABLE IF NOT EXISTS chat_message (
    id           INTEGER PRIMARY KEY,
    role         TEXT NOT NULL,
    content_json TEXT NOT NULL,
    text         TEXT,
    created_at   TEXT NOT NULL,
    active       INTEGER DEFAULT 1
);

CREATE TABLE IF NOT EXISTS food_log (
    id          INTEGER PRIMARY KEY,
    date        TEXT NOT NULL,
    meal        TEXT,
    description TEXT NOT NULL,
    protein_g   REAL DEFAULT 0,
    carbs_g     REAL DEFAULT 0,
    fat_g       REAL DEFAULT 0,
    kcal        REAL DEFAULT 0,
    option_id   INTEGER REFERENCES meal_option(id),
    source      TEXT DEFAULT 'manual',
    created_at  TEXT NOT NULL
);
"""


def connect():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db():
    conn = connect()
    conn.executescript(SCHEMA)
    conn.commit()
    conn.close()
