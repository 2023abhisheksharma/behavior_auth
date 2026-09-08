import json
import joblib
import numpy as np
from pathlib import Path
from typing import Optional, Tuple, Any

KEYBOARD_FEATURE_INDICES = (0, 1, 2, 3, 4)
MOUSE_FEATURE_INDICES = (14, 15, 16, 17, 18, 19)


class ContrastiveBiometricModel:
    """Loads the calibrated owner/impostor model used by the live pipeline."""

    def __init__(self, model_dir: Optional[str] = None):
        self.model_dir = Path(model_dir or (Path(__file__).resolve().parent.parent / "models" / "chronos"))
        self.model_dir.mkdir(parents=True, exist_ok=True)
        self.classifier: Optional[Any] = None
        self.mouse_model: Optional[Any] = None
        self.mouse_score_bounds = (-0.1, 0.1)
        self.keyboard_feature_indices = list(KEYBOARD_FEATURE_INDICES)
        self.mouse_feature_indices = list(MOUSE_FEATURE_INDICES)
        self.load_models()

    def load_models(self) -> bool:
        loaded = False
        classifier_path = self.model_dir / "chronos_classifier.pkl"
        mouse_path = self.model_dir / "chronos_mouse_model.pkl"
        meta_path = self.model_dir / "chronos_meta.json"

        if classifier_path.exists():
            self.classifier = joblib.load(classifier_path)
            loaded = True
        else:
            self.classifier = None

        if mouse_path.exists():
            self.mouse_model = joblib.load(mouse_path)
        else:
            self.mouse_model = None

        if meta_path.exists():
            try:
                metadata = json.loads(meta_path.read_text())
                bounds = metadata.get("mouse_score_bounds")
                if bounds and len(bounds) == 2:
                    self.mouse_score_bounds = (float(bounds[0]), float(bounds[1]))
                if "keyboard_feature_indices" in metadata:
                    self.keyboard_feature_indices = list(metadata["keyboard_feature_indices"])
                if "mouse_feature_indices" in metadata:
                    self.mouse_feature_indices = list(metadata["mouse_feature_indices"])
            except (OSError, ValueError, TypeError):
                pass

        return loaded

    def save_models(
        self,
        classifier,
        mouse_model=None,
        mouse_score_bounds=None,
        keyboard_feature_indices=None,
        mouse_feature_indices=None,
    ):
        if keyboard_feature_indices is not None:
            self.keyboard_feature_indices = list(keyboard_feature_indices)
        if mouse_feature_indices is not None:
            self.mouse_feature_indices = list(mouse_feature_indices)

        joblib.dump(classifier, self.model_dir / "chronos_classifier.pkl")
        mouse_path = self.model_dir / "chronos_mouse_model.pkl"
        if mouse_model is not None:
            joblib.dump(mouse_model, mouse_path)
        elif mouse_path.exists():
            mouse_path.unlink()

        metadata = {
            "model_type": "calibrated_owner_impostor_classifier",
            "keyboard_feature_indices": list(self.keyboard_feature_indices),
            "mouse_feature_indices": list(self.mouse_feature_indices),
        }
        if mouse_score_bounds is not None:
            metadata["mouse_score_bounds"] = [float(mouse_score_bounds[0]), float(mouse_score_bounds[1])]
        (self.model_dir / "chronos_meta.json").write_text(json.dumps(metadata, indent=2))
        self.load_models()

    @staticmethod
    def _probability_from_classifier(classifier, features: np.ndarray) -> float:
        if hasattr(classifier, "predict_proba"):
            return float(classifier.predict_proba(features)[0, 1])
        decision = float(classifier.decision_function(features)[0])
        return float(1.0 / (1.0 + np.exp(-np.clip(decision, -30.0, 30.0))))

    def _mouse_impostor_probability(self, vector: np.ndarray) -> Optional[float]:
        if self.mouse_model is None or len(vector) <= max(self.mouse_feature_indices):
            return None
        mouse_features = vector[list(self.mouse_feature_indices)]
        if not np.isfinite(mouse_features).all() or mouse_features[0] <= 0.5:
            return None

        score = float(self.mouse_model.decision_function(mouse_features.reshape(1, -1))[0])
        low, high = self.mouse_score_bounds
        if high <= low:
            return None
        return float(np.clip((high - score) / (high - low), 0.0, 1.0))

    def compute_log_likelihood_ratio(self, feature_vector: np.ndarray) -> Tuple[float, float, str]:
        vector = np.asarray(feature_vector, dtype=np.float32).reshape(-1)
        vector = np.nan_to_num(vector, nan=0.0, posinf=0.0, neginf=0.0)

        if self.classifier is not None:
            keyboard_features = vector[list(self.keyboard_feature_indices)].reshape(1, -1)
            p_imp = self._probability_from_classifier(self.classifier, keyboard_features)
            source = "CalibratedKeyboard"
        else:
            p_imp = 0.5
            source = "ModelUnavailable"

        mouse_probability = self._mouse_impostor_probability(vector)
        if mouse_probability is not None:
            p_imp = 0.85 * p_imp + 0.15 * mouse_probability
            source += "+MeasuredMouse"

        p_imp = float(np.clip(p_imp, 1e-4, 1.0 - 1e-4))
        return float(np.log(p_imp / (1.0 - p_imp))), p_imp, source

    def explain_features(self, feature_vector: np.ndarray) -> List[Dict[str, Any]]:
        """
        Extracts real-time explainable attribution impacts directly from the trained ML pipeline.
        Compares observed keystroke and motor kinematics against the learned baseline distributions.
        """
        impacts: List[Dict[str, Any]] = []
        if self.classifier is None:
            return impacts

        vector = np.asarray(feature_vector, dtype=np.float32).reshape(-1)

        scaler = None
        try:
            if hasattr(self.classifier, "calibrated_classifiers_") and self.classifier.calibrated_classifiers_:
                estimator = self.classifier.calibrated_classifiers_[0].estimator
                scaler = estimator.named_steps.get("scaler")
            elif hasattr(self.classifier, "named_steps"):
                scaler = self.classifier.named_steps.get("scaler")
        except Exception:
            pass

        if scaler is not None and hasattr(scaler, "mean_") and hasattr(scaler, "scale_"):
            kb_indices = list(self.keyboard_feature_indices)
            kb_values = vector[kb_indices]

            feature_meta = [
                ("dwell_mean", "Key Dwell Time", 1000.0, "ms", 1.5, 2.5),
                ("dwell_std", "Dwell Consistency", 1000.0, "ms", 1.5, 2.5),
                ("flight_mean", "Flight Latency", 1000.0, "ms", 1.5, 2.5),
                ("flight_std", "Rhythm Consistency", 1000.0, "ms", 1.5, 2.5),
                ("typing_speed", "Typing Cadence", 1.0, "keys/s", 1.8, 3.0),
            ]

            for i, (sig_id, label, div, unit, warn_z, crit_z) in enumerate(feature_meta):
                if i >= len(kb_values) or i >= len(scaler.mean_):
                    continue
                obs_raw = kb_values[i]
                if not np.isfinite(obs_raw) or obs_raw <= 0:
                    continue

                mu_raw = scaler.mean_[i]
                sigma_raw = scaler.scale_[i]
                z_score = (obs_raw - mu_raw) / max(sigma_raw, 1e-6)
                abs_z = abs(z_score)

                obs_disp = obs_raw / div
                mu_disp = mu_raw / div
                sigma_disp = sigma_raw / div

                if abs_z < warn_z:
                    severity = "positive"
                    text = f"{label} ({obs_disp:.0f} {unit}) aligns with owner baseline ({mu_disp:.0f} ± {sigma_disp:.0f} {unit})"
                elif abs_z < crit_z:
                    severity = "warning"
                    diff_type = "higher" if z_score > 0 else "lower"
                    text = f"{label} ({obs_disp:.0f} {unit}) is {diff_type} than baseline ({mu_disp:.0f} {unit}, {abs_z:.1f}σ)"
                else:
                    severity = "critical"
                    text = f"{label} anomaly ({obs_disp:.0f} {unit} vs expected {mu_disp:.0f} {unit}, {abs_z:.1f}σ deviation)"

                impacts.append({
                    "signal": f"ml:{sig_id}",
                    "severity": severity,
                    "text": text,
                    "observed": float(obs_disp),
                    "baseline_mean": float(mu_disp),
                    "baseline_std": float(sigma_disp),
                    "z_score": float(abs_z),
                })

        return impacts
