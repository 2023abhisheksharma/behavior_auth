import sqlite3
from pathlib import Path

import database  # Ensures schema migration is applied.
import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from settings import (
    DB_PATH,
    FEATURE_COLUMNS,
    SEQUENCE_LENGTH,
    SEQUENCE_MODEL_PATH,
    CONTEXT_SEQUENCE_MODEL_DIR,
    CONTEXT_MIN_SAMPLES,
    ACTIVITY_LABELS,
)


def build_sequence_rows(df: pd.DataFrame, sequence_length: int):
    if len(df) < sequence_length:
        return np.empty((0, len(FEATURE_COLUMNS) * sequence_length), dtype=float)

    values = df[FEATURE_COLUMNS].to_numpy(dtype=float)
    rows = []

    for i in range(sequence_length - 1, len(values)):
        window = values[i - sequence_length + 1 : i + 1]
        rows.append(window.reshape(-1))

    return np.array(rows, dtype=float)


def build_sequence_pipeline(n_estimators=250):
    return Pipeline([
        ("scaler", StandardScaler()),
        (
            "iforest",
            IsolationForest(
                n_estimators=n_estimators,
                contamination=0.05,
                random_state=42,
            ),
        ),
    ])


def main():
    conn = sqlite3.connect(DB_PATH)
    df = pd.read_sql(
        "SELECT * FROM features WHERE label='owner' ORDER BY id ASC",
        conn,
    )
    conn.close()

    df = df.reindex(columns=FEATURE_COLUMNS, fill_value=0)
    df = df[(df["typing_speed"] > 0.05) | (df["mean_velocity"] > 0.5)]

    # Keep exactly one copy of feature columns after filtering.
    df = df[FEATURE_COLUMNS]

    X = build_sequence_rows(df, SEQUENCE_LENGTH)

    print("Sequence rows:", X.shape)

    if len(X) < 20:
        raise RuntimeError("Need at least 20 sequence rows to train temporal model")

    model = build_sequence_pipeline(n_estimators=250)

    model.fit(X)
    joblib.dump(model, SEQUENCE_MODEL_PATH)

    print("Sequence model trained and saved at", SEQUENCE_MODEL_PATH)

    context_dir = Path(CONTEXT_SEQUENCE_MODEL_DIR)
    context_dir.mkdir(parents=True, exist_ok=True)

    # Build activity-aware sequence models using contiguous windows
    # from each detected context.
    conn_ctx = sqlite3.connect(DB_PATH)
    full_df = pd.read_sql(
        "SELECT * FROM features WHERE label='owner' ORDER BY id ASC",
        conn_ctx,
    )
    conn_ctx.close()
    full_df = full_df.reindex(columns=FEATURE_COLUMNS, fill_value=0)
    full_df = full_df[(full_df["typing_speed"] > 0.05) | (full_df["mean_velocity"] > 0.5)]

    for activity_id, activity_name in ACTIVITY_LABELS.items():
        df_ctx = full_df[full_df["activity"] == float(activity_id)]
        if len(df_ctx) < (CONTEXT_MIN_SAMPLES + SEQUENCE_LENGTH - 1):
            print(
                f"Skip sequence context model {activity_name}: "
                f"{len(df_ctx)} samples not enough"
            )
            continue

        X_ctx = build_sequence_rows(df_ctx[FEATURE_COLUMNS], SEQUENCE_LENGTH)
        if len(X_ctx) < CONTEXT_MIN_SAMPLES:
            print(
                f"Skip sequence context model {activity_name}: "
                f"{len(X_ctx)} rows not enough"
            )
            continue

        model_ctx = build_sequence_pipeline(n_estimators=200)
        model_ctx.fit(X_ctx)

        ctx_path = context_dir / f"sequence_iforest_activity_{activity_id}.pkl"
        joblib.dump(model_ctx, ctx_path)
        print(f"Sequence context model trained: {activity_name} -> {ctx_path}")


if __name__ == "__main__":
    main()
