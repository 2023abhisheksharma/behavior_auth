import sqlite3
import pandas as pd
from sklearn.ensemble import IsolationForest
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler
import joblib
import os
import shutil
import database  # Ensures schema migration is applied.
from settings import DB_PATH, MODEL_PATH, MODEL_BACKUP_PATH, RETRAIN_MIN_SAMPLES, FEATURE_COLUMNS

BACKUP_PATH = MODEL_BACKUP_PATH
MIN_SAMPLES = RETRAIN_MIN_SAMPLES


def retrain_model():
    # -------- LOAD DATA --------
    conn = sqlite3.connect(DB_PATH)
    df = pd.read_sql_query("SELECT * FROM features WHERE label='owner'", conn)
    conn.close()

    if len(df) < MIN_SAMPLES:
        print("Not enough data to retrain")
        return

    df = df.reindex(columns=FEATURE_COLUMNS, fill_value=0)

    # remove weak/noisy data
    df = df[(df["typing_speed"] > 0.1) | (df["mean_velocity"] > 0.5)]

    if len(df) < MIN_SAMPLES:
        print("Not enough high-quality samples after filtering")
        return

    print(f"Retraining on {len(df)} samples")

    # -------- BACKUP CURRENT MODEL --------
    if os.path.exists(MODEL_PATH):
        shutil.copy(MODEL_PATH, BACKUP_PATH)
        print("Backup created")

    # -------- TRAIN NEW MODEL --------
    model = Pipeline([
        ("scaler", StandardScaler()),
        (
            "iforest",
            IsolationForest(
                n_estimators=250,
                contamination=0.05,
                random_state=42,
            ),
        ),
    ])

    model.fit(df)

    joblib.dump(model, MODEL_PATH)
    print("New model saved")

    # -------- VALIDATION STEP --------
    validate_and_maybe_rollback(df)


def validate_and_maybe_rollback(df):
    model = joblib.load(MODEL_PATH)

    scores = model.decision_function(df)

    mean_score = scores.mean()
    min_score = scores.min()

    print(f"Validation → mean: {mean_score:.3f}, min: {min_score:.3f}")

    # -------- VALIDATION LOGIC --------
    # If too many negatives → model is bad
    anomaly_ratio = (scores < 0).sum() / len(scores)

    print(f"Anomaly ratio: {anomaly_ratio:.2f}")

    if anomaly_ratio > 0.25:
        print("❌ Bad model detected → Rolling back")

        if os.path.exists(BACKUP_PATH):
            shutil.copy(BACKUP_PATH, MODEL_PATH)
            print("Rollback successful")
        else:
            print("No backup found, cannot rollback")

    else:
        print("✅ Model validated and accepted")