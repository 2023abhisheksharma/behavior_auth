import sqlite3
from pathlib import Path
import pandas as pd
from sklearn.ensemble import IsolationForest
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler
import joblib
import database  # Ensures schema migration is applied.
from settings import (
    DB_PATH,
    MODEL_PATH,
    FEATURE_COLUMNS,
    CONTEXT_MODEL_DIR,
    CONTEXT_MIN_SAMPLES,
    ACTIVITY_LABELS,
)


def build_iforest_pipeline(n_estimators=200):
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

# Load DB
conn = sqlite3.connect(DB_PATH)

df = pd.read_sql("SELECT * FROM features WHERE label='owner'", conn)
conn.close()

# Keep canonical feature order expected by runtime.
df = df.reindex(columns=FEATURE_COLUMNS, fill_value=0)

# Remove almost-idle windows to increase feature diversity.
df = df[(df["typing_speed"] > 0.05) | (df["mean_velocity"] > 0.5)]

print("Dataset shape:", df.shape)

if len(df) < 15:
    raise RuntimeError("Need at least 15 owner samples to train")

if len(df) < 80:
    print("Warning: low sample count; model quality may be weak")

# Train global model
model = build_iforest_pipeline(n_estimators=200)

model.fit(df)

# Save model
joblib.dump(model, MODEL_PATH)

print("Model trained and saved at", MODEL_PATH)

# Train context-specific models.
context_dir = Path(CONTEXT_MODEL_DIR)
context_dir.mkdir(parents=True, exist_ok=True)

for activity_id, activity_name in ACTIVITY_LABELS.items():
    df_ctx = df[df["activity"] == float(activity_id)]
    if len(df_ctx) < CONTEXT_MIN_SAMPLES:
        print(
            f"Skip context model {activity_name}: "
            f"{len(df_ctx)} < {CONTEXT_MIN_SAMPLES} samples"
        )
        continue

    model_ctx = build_iforest_pipeline(n_estimators=150)
    model_ctx.fit(df_ctx)

    ctx_path = context_dir / f"iforest_activity_{activity_id}.pkl"
    joblib.dump(model_ctx, ctx_path)
    print(f"Context model trained: {activity_name} -> {ctx_path}")
