import sqlite3
from settings import DB_PATH, FEATURE_COLUMNS

def _connect():
    return sqlite3.connect(DB_PATH)


def _init_db():
    conn = _connect()
    cursor = conn.cursor()

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS features (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        mean_dwell REAL,
        std_dwell REAL,
        mean_flight REAL,
        std_flight REAL,
        typing_speed REAL,
        mean_velocity REAL,
        std_velocity REAL,
        mean_acc REAL,
        direction_rate REAL,
        mean_space_d REAL,
        mean_enter_d REAL,
        space_freq REAL,
        enter_freq REAL,
        activity REAL DEFAULT 0,
        label TEXT
    )
    """)

    # Migration-safe add in case table exists from older schema.
    cursor.execute("PRAGMA table_info(features)")
    columns = {row[1] for row in cursor.fetchall()}

    required_columns = {
        "mean_dwell": "REAL DEFAULT 0",
        "std_dwell": "REAL DEFAULT 0",
        "mean_flight": "REAL DEFAULT 0",
        "std_flight": "REAL DEFAULT 0",
        "typing_speed": "REAL DEFAULT 0",
        "mean_velocity": "REAL DEFAULT 0",
        "std_velocity": "REAL DEFAULT 0",
        "mean_acc": "REAL DEFAULT 0",
        "direction_rate": "REAL DEFAULT 0",
        "mean_space_d": "REAL DEFAULT 0",
        "mean_enter_d": "REAL DEFAULT 0",
        "space_freq": "REAL DEFAULT 0",
        "enter_freq": "REAL DEFAULT 0",
        "activity": "REAL DEFAULT 0",
        "label": "TEXT DEFAULT 'owner'",
    }

    for name, definition in required_columns.items():
        if name not in columns:
            cursor.execute(f"ALTER TABLE features ADD COLUMN {name} {definition}")

    # Normalize missing labels in old rows.
    cursor.execute("UPDATE features SET label='owner' WHERE label IS NULL OR label='' ")

    conn.commit()
    conn.close()


_init_db()


# ---- SAVE FUNCTION ----
def save_features(feature_vector, label="owner"):
    if len(feature_vector) != len(FEATURE_COLUMNS):
        raise ValueError(
            f"feature_vector length {len(feature_vector)} does not match expected {len(FEATURE_COLUMNS)}"
        )

    conn = _connect()
    cursor = conn.cursor()

    cursor.execute("""
    INSERT INTO features (
        mean_dwell,
        std_dwell,
        mean_flight,
        std_flight,
        typing_speed,
        mean_velocity,
        std_velocity,
        mean_acc,
        direction_rate,
        mean_space_d,
        mean_enter_d,
        space_freq,
        enter_freq,
        activity,
        label
    )
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, feature_vector + [label])  # 🔥 correct order

    conn.commit()
    conn.close()