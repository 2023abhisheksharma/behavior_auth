import math
import time
from typing import Tuple, Dict, Any

class SPRTTrustEngine:
    """
    Wald's Sequential Probability Ratio Test (SPRT) Trust Engine.
    Provides mathematically optimal sequential hypothesis testing for continuous authentication.
    Minimizes detection delay for given False Acceptance (alpha) and False Rejection (beta) bounds.
    """

    def __init__(
        self,
        target_far: float = 0.005,  # 0.5% False Acceptance Rate bound
        target_frr: float = 0.01,   # 1.0% False Rejection Rate bound
        warning_ratio: float = 0.60,
    ):
        self.alpha = target_far
        self.beta = target_frr

        # Wald Decision Boundaries:
        # A: Upper boundary (Accept H1: Impostor -> LOCK)
        # B: Lower boundary (Accept H0: Genuine Owner -> HIGH TRUST)
        self.A = math.log((1.0 - self.beta) / max(self.alpha, 1e-6))
        self.B = math.log(self.beta / max(1.0 - self.alpha, 1e-6))

        # Alert boundary is an intermediate threshold before full lock
        self.W = self.B + warning_ratio * (self.A - self.B)

        # Cumulative log-likelihood ratio: S_t = sum(Delta Lambda_i)
        self.cumulative_llr = self.B  # Start at genuine state
        self.consecutive_anomalies = 0
        self.total_evaluations = 0
        self.last_update_time = time.time()

    def set_sensitivity(self, sensitivity: str = "Balanced", warning_threshold_pct: int = 50):
        """
        Dynamically adjusts Wald SPRT parameters based on user security policy.
        """
        sens = str(sensitivity or "Balanced").strip().title()
        if sens == "Strict":
            self.alpha = 0.001
            self.beta = 0.030
        elif sens == "Relaxed":
            self.alpha = 0.020
            self.beta = 0.005
        else:  # Balanced
            self.alpha = 0.005
            self.beta = 0.010

        self.A = math.log((1.0 - self.beta) / max(self.alpha, 1e-6))
        self.B = math.log(self.beta / max(1.0 - self.alpha, 1e-6))

        warn_pct = max(10, min(95, int(warning_threshold_pct)))
        warning_ratio = max(0.05, min(0.90, 1.0 - (warn_pct / 100.0)))
        self.W = self.B + warning_ratio * (self.A - self.B)

        # Re-clamp cumulative_llr to valid range under new boundaries
        if self.cumulative_llr < self.B:
            self.cumulative_llr = self.B
        elif self.cumulative_llr > self.A + 2.0:
            self.cumulative_llr = self.A + 2.0

    def update(self, log_lr: float, p_impostor: float) -> Tuple[str, float, Dict[str, Any]]:
        """
        Updates the sequential hypothesis accumulator with new observation.

        Returns:
            (decision_action, trust_percentage, debug_stats)
            Actions: 'CONTINUE', 'ALERT', 'LOCK'
        """
        self.total_evaluations += 1
        now = time.time()
        dt = now - self.last_update_time
        self.last_update_time = now

        # If user was idle between events (> 2.0s), gently decay anomalous evidence back towards genuine baseline
        if dt > 2.0 and self.cumulative_llr > self.B:
            idle_pause = min(dt - 1.5, 6.0)
            decay = 0.20 * idle_pause
            self.cumulative_llr = max(self.B, self.cumulative_llr - decay)

        # Dampen extreme bursts to prevent a single sneeze/typo from instant lock
        clipped_increment = max(min(log_lr, 2.5), -2.0)

        # Accumulate log-likelihood ratio
        self.cumulative_llr += clipped_increment

        # Lower bound clamp: Don't accumulate infinite negative debt into the past
        if self.cumulative_llr < self.B:
            self.cumulative_llr = self.B
            self.consecutive_anomalies = 0

        # Upper bound clamp: prevent runaway accumulation beyond lockout threshold
        if self.cumulative_llr > self.A + 2.0:
            self.cumulative_llr = self.A + 2.0

        # Trust score mapping from [B, A] to [100%, 0%]
        span = self.A - self.B
        trust_norm = 1.0 - (self.cumulative_llr - self.B) / max(span, 1e-4)
        trust_pct = max(0.0, min(100.0, trust_norm * 100.0))

        if p_impostor > 0.6:
            self.consecutive_anomalies += 1
        else:
            self.consecutive_anomalies = max(0, self.consecutive_anomalies - 1)

        # Decision Logic based on Wald Boundaries
        if self.cumulative_llr >= self.A:
            action = "LOCK"
        elif self.cumulative_llr >= self.W:
            action = "ALERT"
        else:
            action = "CONTINUE"

        stats = {
            "cumulative_llr": float(self.cumulative_llr),
            "boundary_A_lock": float(self.A),
            "boundary_B_trust": float(self.B),
            "boundary_W_alert": float(self.W),
            "trust_pct": float(trust_pct),
            "p_impostor": float(p_impostor),
            "consecutive_anomalies": self.consecutive_anomalies,
        }

        return action, trust_pct, stats

    def reset_to_owner(self):
        """Resets the evidence accumulator to genuine owner state."""
        self.cumulative_llr = self.B
        self.consecutive_anomalies = 0
