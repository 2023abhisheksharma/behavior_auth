import numpy as np
from typing import Dict, List, Any, Optional

CHRONOS_FEATURE_COLUMNS = [
    # Legacy Telemetry Features (for backward compatibility & baseline comparison)
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
    # Novel Kinematic & Neuromuscular Modalities (2024-2026 SOTA)
    "stroke_tortuosity_mean",
    "stroke_jerk_rms",
    "stroke_accel_symmetry",
    "stroke_peak_velocity_mean",
    "click_dwell_mean_ms",
    "htl_mean_ms",              # Hand-Transition Latency
    "dwell_left_hand_ms",
    "dwell_right_hand_ms",
    "dwell_hand_asymmetry",
    "cross_hand_ratio",
    "legato_overlap_ratio",
    "active_context_id",        # OS Application Context (0-5)
]

CHRONOS_FEATURE_DIM = len(CHRONOS_FEATURE_COLUMNS)  # 26


def assemble_chronos_vector(
    legacy_features: List[float],
    kinematic_features: Dict[str, float],
    neuromuscular_features: Dict[str, float],
    active_context_id: int = 5,
) -> List[float]:
    """Combines legacy metrics with novel kinematic, neuromuscular, and context features."""
    vec = list(legacy_features)

    def measured(mapping, name):
        value = mapping.get(name)
        return float(value) if value is not None else float("nan")

    vec.append(measured(kinematic_features, "stroke_tortuosity_mean"))
    vec.append(measured(kinematic_features, "stroke_jerk_rms"))
    vec.append(measured(kinematic_features, "stroke_accel_symmetry"))
    vec.append(measured(kinematic_features, "stroke_peak_velocity_mean"))
    vec.append(measured(kinematic_features, "click_dwell_mean_ms"))
    vec.append(measured(kinematic_features, "htl_mean_ms"))

    vec.append(measured(neuromuscular_features, "dwell_left_hand_ms"))
    vec.append(measured(neuromuscular_features, "dwell_right_hand_ms"))
    vec.append(measured(neuromuscular_features, "dwell_hand_asymmetry"))
    vec.append(measured(neuromuscular_features, "cross_hand_ratio"))
    vec.append(measured(neuromuscular_features, "legato_overlap_ratio"))
    vec.append(float(active_context_id))

    return vec
