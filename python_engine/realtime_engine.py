import joblib
import numpy as np
import pandas as pd
from pathlib import Path
from sequence_engine import SequenceEngine
from settings import (
    MODEL_PATH,
    LOCK_THRESHOLD,
    ALERT_THRESHOLD,
    TRUST_ALPHA,
    CALIBRATION_WINDOWS,
    ENABLE_ADAPTIVE_RETRAIN,
    SEQUENCE_BLEND_WEIGHT,
    CONTEXT_MODEL_DIR,
    ACTIVITY_LABELS,
    FEATURE_COLUMNS,
)


class RealtimeEngine:

    def __init__(self):
        self.model = None
        self.context_models = {}
        self.reload_model()
        self.sequence_engine = SequenceEngine()

        # Global trust and per-activity trust to reduce context mismatch.
        self.trust_score = 1.0
        self.trust_by_activity = {}
        self.alpha = TRUST_ALPHA

        self.lock_threshold = LOCK_THRESHOLD
        self.alert_threshold = ALERT_THRESHOLD

        # Dynamic score bounds; seeded conservatively to avoid divide-by-zero.
        self.min_score = -0.05
        self.max_score = 0.25
        self.calibration_remaining = CALIBRATION_WINDOWS

        # Adaptive learning counter (disabled by default via settings).
        self.high_trust_count = 0

    def predict(self, feature_vector):
        if self.model is None and not self.context_models:
            self.reload_model()
            if self.model is None and not self.context_models:
                print("Model unavailable; skipping prediction")
                return

        X = pd.DataFrame([feature_vector], columns=FEATURE_COLUMNS)
        activity = int(feature_vector[-1]) if feature_vector else 0
        activity_name = ACTIVITY_LABELS.get(activity, "unknown")

        model_used = self.context_models.get(activity, self.model)
        model_source = f"context:{activity_name}" if activity in self.context_models else "global"

        try:
            instant_score = float(model_used.decision_function(X)[0])
        except Exception as e:
            print("Model error, reloading:", e)
            self.reload_model()
            return

        sequence_score = self.sequence_engine.score(feature_vector, activity)
        if sequence_score is None:
            score = instant_score
            mode = "instant"
        else:
            w = max(0.0, min(1.0, SEQUENCE_BLEND_WEIGHT))
            score = (1.0 - w) * instant_score + w * sequence_score
            mode = f"blended({model_source})"

        # Map IF score (usually in [-0.15, 0.15]) to norm [0, 1] 
        # where score=0 is exactly norm=0.5.
        norm = 0.5 + (score * 3.33)
        norm = max(0.0, min(1.0, norm))

        if activity not in self.trust_by_activity:
            self.trust_by_activity[activity] = self.trust_score

        activity_trust = self.trust_by_activity[activity]
        activity_trust = self.alpha * norm + (1 - self.alpha) * activity_trust
        self.trust_by_activity[activity] = activity_trust

        self.trust_score = (
            0.7 * activity_trust +
            0.3 * self.trust_score
        )

        self.decision_logic(score, norm, activity, mode, instant_score, sequence_score, model_source)

        if not ENABLE_ADAPTIVE_RETRAIN:
            return

        if self.trust_score > 0.75:
            self.high_trust_count += 1
        else:
            self.high_trust_count = 0

        if self.high_trust_count >= 100:
            print("Adaptive retraining triggered")

            self.safe_retrain()

            self.high_trust_count = 0

    def safe_retrain(self):
        try:
            from adaptive_trainer import retrain_model

            retrain_model()

            # reload model AFTER validation
            self.reload_model()

        except Exception as e:
            print("Retraining failed:", e)
            print("Keeping old model")

    def reload_model(self):
        try:
            self.model = joblib.load(MODEL_PATH)
            print("Model reloaded")
        except Exception as e:
            self.model = None
            print("Model reload failed:", e)

        self.context_models = {}
        base_dir = Path(CONTEXT_MODEL_DIR)
        for activity_id in ACTIVITY_LABELS.keys():
            model_path = base_dir / f"iforest_activity_{activity_id}.pkl"
            if not model_path.exists():
                continue

            try:
                self.context_models[activity_id] = joblib.load(model_path)
                print(f"Context model loaded: activity={activity_id}")
            except Exception as e:
                print(f"Context model load failed for activity={activity_id}:", e)

    def decision_logic(self, score, norm, activity, mode, instant_score, sequence_score, model_source):
        sequence_text = f"{sequence_score:.3f}" if sequence_score is not None else "n/a"

        if self.calibration_remaining > 0:
            self.calibration_remaining -= 1
            warmup_msg = f"WARMUP({self.calibration_remaining} left)"
        else:
            warmup_msg = "LIVE"

        print(
            f"Trust: {self.trust_score:.2f} | "
            f"Score: {score:.3f} | "
            f"Instant: {instant_score:.3f} | "
            f"Sequence: {sequence_text} | "
            f"Scoring: {mode} | "
            f"Model: {model_source} | "
            f"Norm: {norm:.2f} | "
            f"Activity: {activity} | "
            f"Mode: {warmup_msg}",
            end=" | "
        )

        if score >= 0:
            print("NORMAL")
        else:
            print("ANOMALY")

        if self.calibration_remaining > 0:
            print("🟢 ACTION: CONTINUE (calibration)")
            return

        if self.trust_score < self.lock_threshold:
            print("🔴 ACTION: LOCK SYSTEM")

        elif self.trust_score < self.alert_threshold:
            print("🟡 ACTION: ALERT USER")

        else:
            print("🟢 ACTION: CONTINUE")