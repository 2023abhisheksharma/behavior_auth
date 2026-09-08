"""Context-conditioned, high-entropy behavioral profile scoring."""

from __future__ import annotations

import math
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

import numpy as np

from chronos_auth.runtime_config import config_dir, read_json, secure_write_json


MIN_BASELINE_SAMPLES = 6
MIN_OBSERVATION_SAMPLES = 2


@dataclass
class FeatureImpact:
    """A human-readable explanation for one scoring contribution."""

    signal: str
    severity: str
    text: str
    observed: Optional[float] = None
    baseline_mean: Optional[float] = None
    baseline_std: Optional[float] = None
    z_score: Optional[float] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class HighEntropyAssessment:
    available: bool
    p_impostor: Optional[float]
    confidence: float
    context_source: str
    impacts: List[FeatureImpact]
    critical: bool = False

    def to_dict(self) -> Dict[str, Any]:
        payload = asdict(self)
        payload["impacts"] = [impact.to_dict() for impact in self.impacts]
        return payload


def _finite(value: Any) -> bool:
    try:
        return math.isfinite(float(value))
    except (TypeError, ValueError):
        return False


def _stat_summary(value: Any, count: int = 1) -> Optional[Dict[str, float]]:
    """Converts a scalar or profile statistic into a consistent summary."""
    if isinstance(value, dict):
        try:
            sample_count = int(value.get("count", count))
            mean = float(value["mean_ms"] if "mean_ms" in value else value["mean"])
            std = float(value.get("std_ms", value.get("std", 0.0)))
        except (KeyError, TypeError, ValueError):
            return None
    else:
        try:
            sample_count = int(count)
            mean = float(value)
            std = 0.0
        except (TypeError, ValueError):
            return None
    if sample_count <= 0 or not _finite(mean) or not _finite(std):
        return None
    return {"count": sample_count, "mean": mean, "std": max(0.0, std)}


def _combine_statistics(left: Optional[Dict[str, Any]], right: Dict[str, Any]) -> Dict[str, float]:
    """Combines two population summaries without retaining raw biometric events."""
    incoming = _stat_summary(right)
    if incoming is None:
        return _stat_summary(left or {}) or {"count": 0, "mean": 0.0, "std": 0.0}
    existing = _stat_summary(left or {})
    if existing is None or existing["count"] == 0:
        return incoming

    left_count = existing["count"]
    right_count = incoming["count"]
    total = left_count + right_count
    delta = incoming["mean"] - existing["mean"]
    left_m2 = (existing["std"] ** 2) * left_count
    right_m2 = (incoming["std"] ** 2) * right_count
    merged_mean = existing["mean"] + delta * right_count / total
    merged_m2 = left_m2 + right_m2 + (delta ** 2) * left_count * right_count / total
    return {"count": int(total), "mean": float(merged_mean), "std": float(math.sqrt(max(merged_m2 / total, 0.0)))}


def _profile_stat_to_json(stat: Dict[str, float]) -> Dict[str, float]:
    return {"count": int(stat["count"]), "mean": round(float(stat["mean"]), 6), "std": round(float(stat["std"]), 6)}


class HighEntropyProfileStore:
    """Persists per-context owner timing and ballistic-mouse baseline summaries."""

    def __init__(self, path: Optional[Path] = None):
        self.path = path or config_dir() / "high_entropy_profile.json"

    def load(self) -> Dict[str, Any]:
        profile = read_json(self.path, {"version": 1, "contexts": {}, "global": {}})
        profile.setdefault("version", 1)
        profile.setdefault("contexts", {})
        profile.setdefault("global", {})
        return profile

    def _save(self, profile: Dict[str, Any]) -> None:
        profile["updated_at"] = time.time()
        secure_write_json(self.path, profile)

    @staticmethod
    def _empty_section() -> Dict[str, Dict[str, Dict[str, float]]]:
        return {"digraphs": {}, "trigraphs": {}, "mouse": {}}

    def _merge_section(
        self,
        section: Dict[str, Any],
        ngram_profile: Dict[str, Any],
        mouse_profile: Dict[str, Any],
    ) -> None:
        for group in ("digraphs", "trigraphs"):
            target = section.setdefault(group, {})
            for key, summary in ngram_profile.get(group, {}).items():
                normalized = _stat_summary(summary)
                if normalized is not None:
                    target[key] = _profile_stat_to_json(_combine_statistics(target.get(key), normalized))

        target_mouse = section.setdefault("mouse", {})
        for key, summary in mouse_profile.items():
            normalized = _stat_summary(summary)
            if normalized is not None:
                target_mouse[key] = _profile_stat_to_json(_combine_statistics(target_mouse.get(key), normalized))

    def merge_calibration(
        self,
        context_id: int,
        ngram_profile: Dict[str, Any],
        mouse_profile: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Merges measured calibration data into a context and global owner baseline."""
        profile = self.load()
        context_key = str(context_id)
        context_section = profile["contexts"].setdefault(context_key, self._empty_section())
        global_section = profile.setdefault("global", self._empty_section())
        self._merge_section(context_section, ngram_profile, mouse_profile)
        self._merge_section(global_section, ngram_profile, mouse_profile)
        self._save(profile)
        return profile

    def get_context_baseline(self, context_id: int) -> Tuple[Dict[str, Any], str]:
        profile = self.load()
        context_key = str(context_id)
        context = profile.get("contexts", {}).get(context_key)
        if context:
            return context, f"context:{context_key}"
        return profile.get("global", self._empty_section()), "global"

    def adapt(
        self,
        context_id: int,
        ngram_profile: Dict[str, Any],
        mouse_profile: Dict[str, Any],
        rate: float = 0.015,
    ) -> None:
        """Very slowly moves existing baselines during independently high-trust activity."""
        bounded_rate = max(0.001, min(float(rate), 0.05))
        profile = self.load()

        for section in (
            profile.setdefault("contexts", {}).get(str(context_id)),
            profile.setdefault("global", self._empty_section()),
        ):
            if not section:
                continue
            for group, incoming_values in (("digraphs", ngram_profile.get("digraphs", {})), ("trigraphs", ngram_profile.get("trigraphs", {})), ("mouse", mouse_profile)):
                target = section.setdefault(group, {})
                for key, incoming_value in incoming_values.items():
                    observed = _stat_summary(incoming_value)
                    baseline = _stat_summary(target.get(key, {}))
                    if observed is None or baseline is None or baseline["count"] < MIN_BASELINE_SAMPLES:
                        continue
                    baseline["mean"] = (1.0 - bounded_rate) * baseline["mean"] + bounded_rate * observed["mean"]
                    baseline["std"] = max(
                        1e-3,
                        (1.0 - bounded_rate) * baseline["std"] + bounded_rate * observed["std"],
                    )
                    baseline["count"] = min(int(baseline["count"]) + 1, 100_000)
                    target[key] = _profile_stat_to_json(baseline)
        self._save(profile)

    @staticmethod
    def _impact_text(category: str, key: str, observed: float, baseline: Dict[str, float], z_score: float) -> str:
        if category == "digraphs":
            return (
                f"Digraph latency [{key}] was {observed:.0f} ms "
                f"(baseline: {baseline['mean']:.0f} ms ± {baseline['std']:.0f} ms, {z_score:.1f}σ)"
            )
        if category == "trigraphs":
            return (
                f"Trigraph cadence [{key}] was {observed:.0f} ms "
                f"(baseline: {baseline['mean']:.0f} ms ± {baseline['std']:.0f} ms, {z_score:.1f}σ)"
            )
        readable = key.replace("_", " ")
        return (
            f"Mouse {readable} was {observed:.2f} "
            f"(baseline: {baseline['mean']:.2f} ± {baseline['std']:.2f}, {z_score:.1f}σ)"
        )

    def assess(
        self,
        context_id: int,
        ngram_profile: Dict[str, Any],
        mouse_profile: Dict[str, Any],
    ) -> HighEntropyAssessment:
        """Scores measured, matching n-grams and ballistic features against owner baselines."""
        baseline, source = self.get_context_baseline(context_id)
        weighted_z: List[Tuple[float, float]] = []
        impacts: List[FeatureImpact] = []
        critical_matches = 0

        for category, floor in (("digraphs", 8.0), ("trigraphs", 12.0), ("mouse", 0.02)):
            observed_group = mouse_profile if category == "mouse" else ngram_profile.get(category, {})
            baseline_group = baseline.get(category, {})
            for key, observed_value in observed_group.items():
                observed = _stat_summary(observed_value)
                reference = _stat_summary(baseline_group.get(key, {}))
                if observed is None or reference is None:
                    continue
                if observed["count"] < MIN_OBSERVATION_SAMPLES or reference["count"] < MIN_BASELINE_SAMPLES:
                    continue
                scale = max(reference["std"], floor)
                z_score = abs(observed["mean"] - reference["mean"]) / scale
                weight = min(observed["count"], 8) / 8.0
                weighted_z.append((z_score, weight))
                if z_score >= 2.0:
                    severity = "critical" if z_score >= 4.0 else "warning"
                    impacts.append(
                        FeatureImpact(
                            signal=f"{category}:{key}",
                            severity=severity,
                            text=self._impact_text(category, key, observed["mean"], reference, z_score),
                            observed=observed["mean"],
                            baseline_mean=reference["mean"],
                            baseline_std=reference["std"],
                            z_score=z_score,
                        )
                    )
                    if z_score >= 4.0 and category in {"digraphs", "trigraphs"}:
                        critical_matches += 1

        if not weighted_z:
            return HighEntropyAssessment(False, None, 0.0, source, [])

        total_weight = sum(weight for _, weight in weighted_z)
        average_z = sum(z_score * weight for z_score, weight in weighted_z) / max(total_weight, 1e-6)
        confidence = min(1.0, total_weight / 5.0)
        # The calibrated baseline is the dominant live discriminator once enough
        # matching n-grams exist; global ML remains a fallback/secondary signal.
        p_impostor = 1.0 / (1.0 + math.exp(-1.7 * (average_z - 2.2)))
        impacts.sort(key=lambda item: item.z_score or 0.0, reverse=True)
        return HighEntropyAssessment(
            available=True,
            p_impostor=float(np.clip(p_impostor, 0.0001, 0.9999)),
            confidence=confidence,
            context_source=source,
            impacts=impacts[:6],
            critical=critical_matches >= 3,
        )


class FastThreatDetector:
    """Detects physically implausible input before the cumulative SPRT horizon."""

    def evaluate(
        self,
        *,
        typing_speed: Optional[float],
        dwell_std_ms: Optional[float],
        dwell_count: int,
        mouse_interval_jitter_ms: Optional[float],
        mouse_point_count: int,
        high_entropy: Optional[HighEntropyAssessment] = None,
    ) -> List[FeatureImpact]:
        impacts: List[FeatureImpact] = []
        if _finite(typing_speed) and float(typing_speed) > 25.0:
            impacts.append(
                FeatureImpact(
                    signal="fast:typing_speed",
                    severity="critical",
                    text=f"Physical-impossibility filter: sustained typing speed was {float(typing_speed):.1f} keys/s (>25 keys/s)",
                    observed=float(typing_speed),
                )
            )
        if dwell_count >= 8 and _finite(dwell_std_ms) and float(dwell_std_ms) < 2.0:
            impacts.append(
                FeatureImpact(
                    signal="fast:dwell_jitter",
                    severity="critical",
                    text=f"Physical-impossibility filter: key dwell jitter was {float(dwell_std_ms):.2f} ms (<2 ms)",
                    observed=float(dwell_std_ms),
                )
            )
        if mouse_point_count >= 8 and _finite(mouse_interval_jitter_ms) and float(mouse_interval_jitter_ms) < 2.0:
            impacts.append(
                FeatureImpact(
                    signal="fast:mouse_tremor",
                    severity="critical",
                    text=f"Physical-impossibility filter: mouse timing tremor was {float(mouse_interval_jitter_ms):.2f} ms (<2 ms)",
                    observed=float(mouse_interval_jitter_ms),
                )
            )
        if high_entropy is not None and high_entropy.critical:
            impacts.append(
                FeatureImpact(
                    signal="fast:foreign_digraphs",
                    severity="critical",
                    text="Physical-impossibility filter: multiple common digraphs were far outside the calibrated owner profile",
                )
            )
        return impacts

