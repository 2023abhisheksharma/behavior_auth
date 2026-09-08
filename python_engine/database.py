import sqlite3
import math
from settings import DB_PATH

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
        label TEXT DEFAULT 'unverified_live'
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
        "label": "TEXT DEFAULT 'unverified_live'",
        "stroke_tortuosity_mean": "REAL",
        "stroke_jerk_rms": "REAL",
        "stroke_accel_symmetry": "REAL",
        "stroke_peak_velocity_mean": "REAL",
        "click_dwell_mean_ms": "REAL",
        "htl_mean_ms": "REAL",
        "dwell_left_hand_ms": "REAL",
        "dwell_right_hand_ms": "REAL",
        "dwell_hand_asymmetry": "REAL",
        "cross_hand_ratio": "REAL",
        "legato_overlap_ratio": "REAL",
        "active_context_id": "REAL",
        "data_source": "TEXT DEFAULT 'legacy_window'",
        "keyboard_event_count": "INTEGER DEFAULT 0",
        "mouse_event_count": "INTEGER DEFAULT 0",
    }

    for name, definition in required_columns.items():
        if name not in columns:
            cursor.execute(f"ALTER TABLE features ADD COLUMN {name} {definition}")

    # Missing labels are not verified identity evidence.
    cursor.execute("UPDATE features SET label='unverified_live' WHERE label IS NULL OR label='' ")

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS high_entropy_observations (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        created_at REAL NOT NULL,
        context_id INTEGER,
        app_name TEXT,
        label TEXT NOT NULL DEFAULT 'unverified_live',
        data_source TEXT NOT NULL DEFAULT 'local_chronos',
        digraphs_json TEXT NOT NULL,
        trigraphs_json TEXT NOT NULL,
        mouse_json TEXT NOT NULL,
        impacts_json TEXT NOT NULL
    )
    """)

    conn.commit()
    conn.close()


def save_high_entropy_observation(
    ngram_profile,
    mouse_profile,
    impacts,
    *,
    context_id=5,
    app_name="unknown",
    label="unverified_live",
    data_source="local_chronos",
):
    """Stores timing summaries and explanations without retaining typed content."""
    import json
    import time

    conn = _connect()
    try:
        conn.execute(
            """
            INSERT INTO high_entropy_observations (
                created_at, context_id, app_name, label, data_source,
                digraphs_json, trigraphs_json, mouse_json, impacts_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                time.time(),
                int(context_id),
                str(app_name),
                str(label),
                str(data_source),
                json.dumps(ngram_profile.get("digraphs", {}), sort_keys=True),
                json.dumps(ngram_profile.get("trigraphs", {}), sort_keys=True),
                json.dumps(mouse_profile, sort_keys=True),
                json.dumps(impacts, sort_keys=True),
            ),
        )
        conn.commit()
    finally:
        conn.close()


_init_db()


# ---- SAVE FUNCTION ----
def save_features(
    feature_vector,
    label="unverified_live",
    data_source="local",
    keyboard_event_count=0,
    mouse_event_count=0,
):
    """
    Saves a feature vector to the database. Supports both 14-element legacy vectors
    and 26-element full Chronos vectors.
    """
    conn = _connect()
    cursor = conn.cursor()

    def db_value(value):
        if value is None:
            return None
        try:
            value = float(value)
        except (TypeError, ValueError):
            return value
        return value if math.isfinite(value) else None

    if len(feature_vector) == 26:
        values = [db_value(value) for value in feature_vector]
        if mouse_event_count <= 0:
            values[14:20] = [None] * 6
        if keyboard_event_count <= 0:
            values[20:25] = [None] * 5
        values += [label, data_source, keyboard_event_count, mouse_event_count]
        placeholders = ", ".join("?" for _ in values)
        cursor.execute(f"""
        INSERT INTO features (
            mean_dwell, std_dwell, mean_flight, std_flight, typing_speed,
            mean_velocity, std_velocity, mean_acc, direction_rate, mean_space_d,
            mean_enter_d, space_freq, enter_freq, activity,
            stroke_tortuosity_mean, stroke_jerk_rms, stroke_accel_symmetry, stroke_peak_velocity_mean,
            click_dwell_mean_ms, htl_mean_ms, dwell_left_hand_ms, dwell_right_hand_ms,
            dwell_hand_asymmetry, cross_hand_ratio, legato_overlap_ratio, active_context_id,
            label, data_source, keyboard_event_count, mouse_event_count
        )
        VALUES ({placeholders})
        """, values)
    elif len(feature_vector) == 14:
        # Legacy windows only contain keyboard/legacy mouse features. Leave modern
        # modality columns NULL instead of inventing values for absent telemetry.
        values = [db_value(value) for value in feature_vector] + [None] * 12 + [label, data_source, keyboard_event_count, mouse_event_count]
        placeholders = ", ".join("?" for _ in values)
        cursor.execute(f"""
        INSERT INTO features (
            mean_dwell, std_dwell, mean_flight, std_flight, typing_speed,
            mean_velocity, std_velocity, mean_acc, direction_rate, mean_space_d,
            mean_enter_d, space_freq, enter_freq, activity,
            stroke_tortuosity_mean, stroke_jerk_rms, stroke_accel_symmetry, stroke_peak_velocity_mean,
            click_dwell_mean_ms, htl_mean_ms, dwell_left_hand_ms, dwell_right_hand_ms,
            dwell_hand_asymmetry, cross_hand_ratio, legato_overlap_ratio, active_context_id,
            label, data_source, keyboard_event_count, mouse_event_count
        )
        VALUES ({placeholders})
        """, values)
    else:
        conn.close()
        raise ValueError(
            f"feature_vector length {len(feature_vector)} does not match expected 14 or 26"
        )

    conn.commit()
    conn.close()
