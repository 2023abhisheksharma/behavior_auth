from collections import deque
from pathlib import Path

import joblib
import numpy as np

from settings import (
    FEATURE_COLUMNS,
    SEQUENCE_MODEL_PATH,
    SEQUENCE_LENGTH,
    CONTEXT_SEQUENCE_MODEL_DIR,
    ACTIVITY_LABELS,
)


class SequenceEngine:
    def __init__(self):
        self.model = None
        self.context_models = {}
        self.global_buffer = deque(maxlen=SEQUENCE_LENGTH)
        self.context_buffers = {
            activity_id: deque(maxlen=SEQUENCE_LENGTH)
            for activity_id in ACTIVITY_LABELS.keys()
        }
        self.reload_model()

    def reload_model(self):
        try:
            self.model = joblib.load(SEQUENCE_MODEL_PATH)
            print("Sequence model reloaded")
        except Exception as e:
            self.model = None
            print("Sequence model unavailable:", e)

        self.context_models = {}
        base_dir = Path(CONTEXT_SEQUENCE_MODEL_DIR)
        for activity_id in ACTIVITY_LABELS.keys():
            model_path = base_dir / f"sequence_iforest_activity_{activity_id}.pkl"
            if not model_path.exists():
                continue

            try:
                self.context_models[activity_id] = joblib.load(model_path)
                print(f"Sequence context model loaded: activity={activity_id}")
            except Exception as e:
                print(f"Sequence context model load failed for activity={activity_id}:", e)

    def _normalize_feature_vector(self, feature_vector):
        if len(feature_vector) != len(FEATURE_COLUMNS):
            raise ValueError(
                f"feature_vector length {len(feature_vector)} does not match expected {len(FEATURE_COLUMNS)}"
            )
        return np.array(feature_vector, dtype=float)

    def _build_sequence_row(self):
        stacked = np.concatenate(list(self.global_buffer), axis=0)
        return stacked.reshape(1, -1)

    def _build_context_sequence_row(self, activity_id):
        stacked = np.concatenate(list(self.context_buffers[activity_id]), axis=0)
        return stacked.reshape(1, -1)

    def score(self, feature_vector, activity_id):
        vector = self._normalize_feature_vector(feature_vector)

        self.global_buffer.append(vector)
        if activity_id in self.context_buffers:
            self.context_buffers[activity_id].append(vector)

        if self.model is None:
            global_score = None
        elif len(self.global_buffer) < SEQUENCE_LENGTH:
            global_score = None
        else:
            row = self._build_sequence_row()

            try:
                global_score = float(self.model.decision_function(row)[0])
            except Exception as e:
                print("Sequence model error; reloading:", e)
                self.reload_model()
                global_score = None

        ctx_model = self.context_models.get(activity_id)
        if ctx_model is None or len(self.context_buffers.get(activity_id, [])) < SEQUENCE_LENGTH:
            return global_score

        row_ctx = self._build_context_sequence_row(activity_id)
        try:
            ctx_score = float(ctx_model.decision_function(row_ctx)[0])
        except Exception as e:
            print("Sequence context model error; reloading:", e)
            self.reload_model()
            return global_score

        if global_score is None:
            return ctx_score

        return 0.5 * global_score + 0.5 * ctx_score
