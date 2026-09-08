import sqlite3
import sys
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.calibration import CalibratedClassifierCV
from sklearn.ensemble import IsolationForest
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import classification_report, roc_auc_score
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))

from chronos_auth.chronos_features import CHRONOS_FEATURE_COLUMNS
from chronos_auth.contrastive_model import KEYBOARD_FEATURE_INDICES, MOUSE_FEATURE_INDICES, ContrastiveBiometricModel
from settings import DB_PATH


def load_labeled_rows():
    conn = sqlite3.connect(DB_PATH)
    frame = pd.read_sql_query("SELECT * FROM features", conn)
    conn.close()

    if frame.empty:
        raise RuntimeError("The feature database is empty")

    owner = frame[
        (frame["label"] == "owner")
        & (~frame["data_source"].isin(["local_chronos", "local_legacy_window"]))
    ].copy()
    impostor = frame[frame["label"].isin(["external_impostor", "impostor"])].copy()
    if owner.empty or impostor.empty:
        raise RuntimeError(
            "Training requires both owner rows and real impostor rows. "
            "Import a labeled public dataset first."
        )

    keyboard_columns = [CHRONOS_FEATURE_COLUMNS[index] for index in KEYBOARD_FEATURE_INDICES]
    owner = owner.dropna(subset=keyboard_columns)
    impostor = impostor.dropna(subset=keyboard_columns)
    quality = (
        (frame["mean_dwell"] >= 5_000)
        & (frame["mean_dwell"] <= 2_000_000)
        & (frame["mean_flight"] >= 0)
        & (frame["mean_flight"] <= 3_000_000)
        & (frame["typing_speed"] >= 0.1)
        & (frame["typing_speed"] <= 20.0)
    )
    owner = owner[quality.loc[owner.index]]
    impostor = impostor[quality.loc[impostor.index]]
    if owner.empty or impostor.empty:
        raise RuntimeError("No complete labeled keyboard samples remain after quality filtering")

    # Balance impostor sample size to prevent extreme Bayesian prior distortion (34:1 skew)
    impostor_sampled = impostor.sample(n=min(len(impostor), len(owner)), random_state=42)
    combined = pd.concat([owner, impostor_sampled], ignore_index=True)
    X = combined[keyboard_columns].to_numpy(dtype=np.float64)
    y = (combined["label"] != "owner").astype(np.int32).to_numpy()
    return frame, combined, X, y


def train_mouse_profile(owner_frame):
    mouse_columns = [CHRONOS_FEATURE_COLUMNS[index] for index in MOUSE_FEATURE_INDICES]
    measured = owner_frame[mouse_columns].dropna()
    measured = measured[measured[mouse_columns[0]] > 0.5]
    if len(measured) < 20:
        print("Measured mouse profile: unavailable (<20 measured owner samples)")
        return None, None

    mouse_model = Pipeline(
        [
            ("scaler", StandardScaler()),
            ("iforest", IsolationForest(n_estimators=200, contamination=0.05, random_state=42)),
        ]
    )
    values = measured.to_numpy(dtype=np.float64)
    mouse_model.fit(values)
    scores = mouse_model.decision_function(values)
    bounds = (float(np.quantile(scores, 0.01)), float(np.quantile(scores, 0.99)))
    print(f"Measured mouse profile: {len(values)} owner samples")
    return mouse_model, bounds


def main():
    print("Chronos-Auth: training from real owner and impostor rows")
    full_frame, labeled_frame, X, y = load_labeled_rows()
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.20, random_state=42, stratify=y
    )

    base_classifier = Pipeline(
        [
            ("scaler", StandardScaler()),
            (
                "classifier",
                LogisticRegression(max_iter=2000, class_weight="balanced", random_state=42),
            ),
        ]
    )
    classifier = CalibratedClassifierCV(base_classifier, method="sigmoid", cv=3)
    classifier.fit(X_train, y_train)

    probabilities = classifier.predict_proba(X_test)[:, 1]
    print(f"Owner rows: {int((y == 0).sum())}")
    print(f"Real impostor rows: {int((y == 1).sum())}")
    print(f"Held-out AUC: {roc_auc_score(y_test, probabilities):.4f}")
    print(classification_report(y_test, probabilities >= 0.5, target_names=["owner", "impostor"], zero_division=0))

    owner_frame = full_frame[
        (full_frame["label"] == "owner")
        & (~full_frame["data_source"].isin(["local_chronos", "local_legacy_window"]))
    ]
    mouse_model, mouse_bounds = train_mouse_profile(owner_frame)

    model = ContrastiveBiometricModel()
    model.save_models(
        classifier,
        mouse_model=mouse_model,
        mouse_score_bounds=mouse_bounds,
        keyboard_feature_indices=list(KEYBOARD_FEATURE_INDICES),
    )
    print(f"Saved calibrated model to {model.model_dir}")


if __name__ == "__main__":
    main()
