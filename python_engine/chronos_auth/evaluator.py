import numpy as np
from sklearn.metrics import roc_curve, roc_auc_score
from typing import Dict, Any, Tuple

def compute_biometric_metrics(y_true: np.ndarray, y_score: np.ndarray) -> Dict[str, float]:
    """
    Computes standard biometric evaluation metrics:
    - EER (Equal Error Rate)
    - AUC (Area Under the ROC Curve)
    - FAR at fixed FRR thresholds
    """
    # y_true: 0 for genuine owner, 1 for impostor
    # y_score: higher score means more likely impostor
    fpr, tpr, thresholds = roc_curve(y_true, y_score, pos_label=1)
    fnr = 1.0 - tpr

    # EER is where FPR == FNR
    abs_diffs = np.abs(fpr - fnr)
    min_idx = np.argmin(abs_diffs)
    eer = float((fpr[min_idx] + fnr[min_idx]) / 2.0)
    eer_threshold = float(thresholds[min_idx])

    auc = float(roc_auc_score(y_true, y_score))

    # FAR at FRR <= 1% (security-first)
    valid_idx = np.where(fnr <= 0.01)[0]
    far_at_1pct_frr = float(fpr[valid_idx[-1]]) if len(valid_idx) > 0 else float(fpr[0])

    # FRR at FAR <= 1% (usability-first)
    valid_idx_far = np.where(fpr <= 0.01)[0]
    frr_at_1pct_far = float(fnr[valid_idx_far[0]]) if len(valid_idx_far) > 0 else float(fnr[-1])

    return {
        "EER": eer,
        "EER_threshold": eer_threshold,
        "AUC": auc,
        "FAR_at_1pct_FRR": far_at_1pct_frr,
        "FRR_at_1pct_FAR": frr_at_1pct_far,
    }


def simulate_sprt_lockout_latency(
    model,
    sprt_engine_factory,
    impostor_samples: np.ndarray,
) -> Tuple[float, float]:
    """
    Simulates consecutive impostor attacks to compute:
    - Average Time to Lockout (in bursts/actions)
    - Successful Lockout Rate (%)
    """
    lockout_steps = []
    locked_count = 0

    for sample in impostor_samples:
        sprt = sprt_engine_factory()
        locked = False
        for step in range(1, 20):  # max 20 steps
            log_lr, p_imp, _ = model.compute_log_likelihood_ratio(sample)
            action, trust, _ = sprt.update(log_lr, p_imp)
            if action == "LOCK":
                lockout_steps.append(step)
                locked = True
                locked_count += 1
                break
        if not locked:
            lockout_steps.append(20)

    avg_steps = float(np.mean(lockout_steps)) if lockout_steps else 20.0
    lock_rate = float(locked_count / max(len(impostor_samples), 1)) * 100.0

    return avg_steps, lock_rate
