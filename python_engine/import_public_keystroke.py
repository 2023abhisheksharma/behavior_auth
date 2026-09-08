"""Import a public, real keystroke benchmark as labeled impostor data."""

import argparse
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from database import DB_PATH


FEATURE_COLUMNS = [
    "mean_dwell",
    "std_dwell",
    "mean_flight",
    "std_flight",
    "typing_speed",
    "mean_velocity",
    "std_velocity",
    "mean_acc",
    "direction_rate",
    "mean_space_d",
    "mean_enter_d",
    "space_freq",
    "enter_freq",
    "activity",
]

MODERN_COLUMNS = [
    "stroke_tortuosity_mean",
    "stroke_jerk_rms",
    "stroke_accel_symmetry",
    "stroke_peak_velocity_mean",
    "click_dwell_mean_ms",
    "htl_mean_ms",
    "dwell_left_hand_ms",
    "dwell_right_hand_ms",
    "dwell_hand_asymmetry",
    "cross_hand_ratio",
    "legato_overlap_ratio",
    "active_context_id",
]


def build_rows(csv_path: Path, label: str):
    frame = pd.read_csv(csv_path)
    dwell_columns = [column for column in frame.columns if column.startswith("H.")]
    flight_columns = [column for column in frame.columns if column.startswith("UD.")]
    if not dwell_columns or not flight_columns:
        raise ValueError("The input is not the CMU keystroke benchmark format")

    dwell = frame[dwell_columns].to_numpy(dtype=float)
    flight = frame[flight_columns].to_numpy(dtype=float)
    valid = np.isfinite(dwell).all(axis=1) & np.isfinite(flight).all(axis=1)
    dwell = dwell[valid]
    flight = flight[valid]

    dwell_mean = dwell.mean(axis=1)
    dwell_std = dwell.std(axis=1)
    flight_mean = flight.mean(axis=1)
    flight_std = flight.std(axis=1)
    typing_speed = len(dwell_columns) / np.maximum(dwell.sum(axis=1) + flight.sum(axis=1), 1e-6)

    legacy = np.column_stack(
        [
            dwell_mean * 1_000_000.0,
            dwell_std * 1_000_000.0,
            flight_mean * 1_000_000.0,
            flight_std * 1_000_000.0,
            typing_speed,
            np.zeros(len(dwell)),
            np.zeros(len(dwell)),
            np.zeros(len(dwell)),
            np.zeros(len(dwell)),
            np.zeros(len(dwell)),
            np.zeros(len(dwell)),
            np.zeros(len(dwell)),
            np.zeros(len(dwell)),
            np.zeros(len(dwell)),
        ]
    )

    rows = []
    for vector in legacy:
        rows.append(
            tuple(vector.tolist())
            + (None,) * len(MODERN_COLUMNS)
            + (label, "public_cmu_keystroke_benchmark", len(dwell_columns), 0)
        )
    return rows, len(dwell)


def import_dataset(csv_path: Path, label: str):
    rows, count = build_rows(csv_path, label)
    columns = FEATURE_COLUMNS + MODERN_COLUMNS + [
        "label",
        "data_source",
        "keyboard_event_count",
        "mouse_event_count",
    ]
    placeholders = ",".join("?" for _ in columns)

    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        "CREATE TABLE IF NOT EXISTS dataset_provenance ("
        "source TEXT PRIMARY KEY, imported_at TEXT NOT NULL, rows INTEGER NOT NULL, path TEXT NOT NULL)"
    )
    conn.executemany(
        f"INSERT INTO features ({','.join(columns)}) VALUES ({placeholders})",
        rows,
    )
    conn.execute(
        "INSERT OR REPLACE INTO dataset_provenance(source, imported_at, rows, path) VALUES (?, ?, ?, ?)",
        (
            "public_cmu_keystroke_benchmark",
            datetime.now(timezone.utc).isoformat(),
            count,
            str(csv_path.resolve()),
        ),
    )
    conn.commit()
    conn.close()
    print(f"Imported {count} real rows from {csv_path} as {label}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("csv_path", type=Path)
    parser.add_argument("--label", default="external_impostor")
    args = parser.parse_args()
    import_dataset(args.csv_path, args.label)


if __name__ == "__main__":
    main()
