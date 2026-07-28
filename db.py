import os
import sqlite3
from datetime import date

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.environ.get("DB_PATH", os.path.join(BASE_DIR, "data", "health.db"))
BACKUP_DIR = os.path.join(os.path.dirname(DB_PATH), "backups")
BACKUP_KEEP = 14  # mantém as últimas N cópias diárias

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
    kind        TEXT NOT NULL DEFAULT 'weight',  -- 'weight' (kg × reps) ou 'time' (segundos, peso do corpo)
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
    id       INTEGER PRIMARY KEY,
    name     TEXT NOT NULL,
    sort     INTEGER DEFAULT 0,
    shopping INTEGER NOT NULL DEFAULT 1,  -- entra na lista de compras semanal (0 p/ "Extra")
    time     TEXT                         -- horário previsto "HH:MM" (opcional)
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
    conn = sqlite3.connect(DB_PATH, timeout=15)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    # WAL: leituras não bloqueiam escritas — necessário com 2 workers do gunicorn
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA busy_timeout = 15000")
    return conn


def _column_exists(conn, table, column):
    return any(r["name"] == column for r in conn.execute(f"PRAGMA table_info({table})"))


def migrate(conn):
    """Ajustes de schema em bancos já existentes (CREATE TABLE IF NOT EXISTS não
    adiciona colunas novas). Idempotente."""
    if not _column_exists(conn, "exercise", "kind"):
        conn.execute("ALTER TABLE exercise ADD COLUMN kind TEXT NOT NULL DEFAULT 'weight'")
        # exercícios isométricos por tempo (ex.: prancha) medem segundos, não carga
        conn.execute("UPDATE exercise SET kind = 'time' WHERE name LIKE '%segundo%'")
    if not _column_exists(conn, "meal", "shopping"):
        conn.execute("ALTER TABLE meal ADD COLUMN shopping INTEGER NOT NULL DEFAULT 1")
        conn.execute("UPDATE meal SET shopping = 0 WHERE name LIKE 'Extra%'")
    if not _column_exists(conn, "meal", "time"):
        # horário previsto da refeição ("HH:MM") — aparece nas ações futuras da Hoje;
        # backfill pelos nomes do plano original (refeições novas ficam sem horário)
        conn.execute("ALTER TABLE meal ADD COLUMN time TEXT")
        for like, t in [("Café%", "07:00"), ("Almoço%", "12:00"),
                        ("Lanche%", "16:00"), ("Jantar%", "19:30")]:
            conn.execute("UPDATE meal SET time = ? WHERE name LIKE ?", (t, like))
    # tabela de um design anterior ao food_log; nunca foi usada pelo código
    conn.execute("DROP TABLE IF EXISTS meal_choice")
    conn.commit()


def backup(conn):
    """Cópia diária consistente do banco (VACUUM INTO data/backups/). Mantém as
    últimas BACKUP_KEEP; no-op se a cópia de hoje já existe."""
    os.makedirs(BACKUP_DIR, exist_ok=True)
    path = os.path.join(BACKUP_DIR, f"health-{date.today().isoformat()}.db")
    if os.path.exists(path):
        return
    conn.execute("VACUUM INTO ?", (path,))
    old = sorted(f for f in os.listdir(BACKUP_DIR)
                 if f.startswith("health-") and f.endswith(".db"))
    for name in old[:-BACKUP_KEEP]:
        os.remove(os.path.join(BACKUP_DIR, name))


def init_db():
    conn = connect()
    conn.executescript(SCHEMA)
    migrate(conn)
    conn.commit()
    conn.close()
