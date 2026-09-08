"""Presentation helpers for live biometric feature attribution."""

from __future__ import annotations

from typing import Any, Dict, Iterable, List


SEVERITY_PREFIX = {
    "critical": "🚨",
    "warning": "⚠️",
    "positive": "🟢",
    "info": "ℹ️",
}


def normalize_impacts(impacts: Iterable[Dict[str, Any]], limit: int = 5) -> List[str]:
    """Converts serialized evidence into bounded, plain-language display lines."""
    severity_order = {"critical": 0, "warning": 1, "positive": 2, "info": 3}
    valid_impacts = [imp for imp in impacts if isinstance(imp, dict) and str(imp.get("text", "")).strip()]
    valid_impacts.sort(key=lambda imp: severity_order.get(str(imp.get("severity", "info")).lower(), 99))

    lines: List[str] = []
    for impact in valid_impacts:
        text = str(impact.get("text", "")).strip()
        prefix = SEVERITY_PREFIX.get(str(impact.get("severity", "info")).lower(), "ℹ️")
        lines.append(f"{prefix} {text}")
        if len(lines) >= limit:
            break
    if not lines:
        lines.append("ℹ️ Continuous ML monitoring active — verifying keystroke & motor dynamics in real time.")
    return lines

