"""Interactive, privacy-preserving calibration session controller."""

from __future__ import annotations

import time
from collections import Counter
from pathlib import Path
from typing import Any, Dict, Optional

from chronos_auth.high_entropy import HighEntropyProfileStore
from chronos_auth.ngram_analyzer import NgramAnalyzer
from chronos_auth.runtime_config import (
    CALIBRATION_CONTROL_PATH,
    CALIBRATION_STATUS_PATH,
    read_json,
    secure_write_json,
)
from chronos_auth.stroke_analyzer import StrokeAnalyzer


class CalibrationSession:
    """Consumes real local events only while a user explicitly starts calibration."""

    def __init__(
        self,
        profile_store: Optional[HighEntropyProfileStore] = None,
        control_path: Path = CALIBRATION_CONTROL_PATH,
        status_path: Path = CALIBRATION_STATUS_PATH,
    ):
        self.profile_store = profile_store or HighEntropyProfileStore()
        self.control_path = control_path
        self.status_path = status_path
        self.last_request_at = 0.0
        self.phase: Optional[str] = None
        self.started_at = 0.0
        self.expires_at = 0.0
        self.typing_analyzer = NgramAnalyzer(history_len=5000)
        self.mouse_analyzer = StrokeAnalyzer()
        self.context_counts: Counter = Counter()
        self.app_names: Counter = Counter()
        self._write_status("idle", "Ready to collect an opt-in owner calibration.")

    def _write_status(self, state: str, message: str, **extra: Any) -> None:
        now = time.time()
        payload = {
            "state": state,
            "phase": self.phase,
            "message": message,
            "started_at": self.started_at or None,
            "expires_at": self.expires_at or None,
            "remaining_seconds": max(0, int(self.expires_at - now)) if self.expires_at else 0,
            "typing_digraphs": len(self.typing_analyzer.extract_timing_profile(min_count=1).get("digraphs", {})),
            "mouse_strokes": len(self.mouse_analyzer.completed_strokes),
        }
        payload.update(extra)
        try:
            secure_write_json(self.status_path, payload)
        except OSError:
            pass

    def poll_control(self) -> None:
        """Handles UI commands from the small local runtime-control file."""
        request = read_json(self.control_path)
        try:
            requested_at = float(request.get("requested_at", 0.0))
        except (TypeError, ValueError):
            requested_at = 0.0
        if requested_at > self.last_request_at:
            self.last_request_at = requested_at
            command = str(request.get("command", "")).lower()
            if command == "start":
                self._start(str(request.get("phase", "typing")).lower(), request.get("duration_seconds"))
            elif command == "finish":
                self.finish()
            elif command == "cancel":
                self.cancel()

        if self.phase and self.expires_at and time.time() >= self.expires_at:
            completed_phase = self.phase
            self.phase = None
            self.expires_at = 0.0
            self._write_status("awaiting_next_step", f"{completed_phase.title()} collection complete. Start the next step or save your profile.")

    def _start(self, phase: str, requested_duration: Any) -> None:
        if phase not in {"typing", "mouse"}:
            self._write_status("error", "Calibration phase must be 'typing' or 'mouse'.")
            return
        default_duration = 120 if phase == "typing" else 90
        maximum_duration = 300 if phase == "typing" else 180
        try:
            duration = int(requested_duration or default_duration)
        except (TypeError, ValueError):
            duration = default_duration
        self.phase = phase
        self.started_at = time.time()
        self.expires_at = self.started_at + max(15, min(duration, maximum_duration))
        self._write_status("collecting", f"Collecting real {phase} timing for this calibration step.")

    def record_event(self, event: Dict[str, Any], context_id: int, app_name: str) -> None:
        self.poll_control()
        if not self.phase:
            return
        self.context_counts[int(context_id)] += 1
        self.app_names[str(app_name)] += 1
        event_type = event.get("type")
        timestamp = int(event.get("timestamp", 0))

        if self.phase == "typing" and event_type in {"KEY_DOWN", "KEY_UP"}:
            key_code = int(event.get("key_code", 0))
            if event_type == "KEY_DOWN":
                self.typing_analyzer.register_key_down(timestamp, key_code)
            else:
                self.typing_analyzer.register_key_up(timestamp, key_code)
        elif self.phase == "mouse":
            if event_type == "MOUSE_MOVE":
                self.mouse_analyzer.add_move(timestamp, int(event.get("dx", 0)), int(event.get("dy", 0)))
            elif event_type in {"MOUSE_DOWN", "MOUSE_UP"}:
                self.mouse_analyzer.register_mouse_button(
                    timestamp,
                    int(event.get("key_code", 0)),
                    event_type == "MOUSE_DOWN",
                )
        self._write_status("collecting", f"Collecting real {self.phase} timing for this calibration step.")

    def finish(self) -> Dict[str, Any]:
        """Saves aggregate timing summaries, never the source text or raw pointer path."""
        self.phase = None
        self.expires_at = 0.0
        if self.mouse_analyzer.current_stroke.point_count >= 3:
            self.mouse_analyzer._finish_stroke()

        ngram_profile = self.typing_analyzer.extract_timing_profile(min_count=1)
        mouse_profile = self.mouse_analyzer.extract_ballistic_profile()
        digraph_samples = sum(item["count"] for item in ngram_profile.get("digraphs", {}).values())
        mouse_samples = sum(item["count"] for item in mouse_profile.values())
        if digraph_samples == 0 and mouse_samples == 0:
            self._write_status("error", "No measurable input was collected; please complete at least one calibration step.")
            return read_json(self.status_path)

        context_id = self.context_counts.most_common(1)[0][0] if self.context_counts else 5
        app_name = self.app_names.most_common(1)[0][0] if self.app_names else "unknown"
        self.profile_store.merge_calibration(context_id, ngram_profile, mouse_profile)

        try:
            from database import save_high_entropy_observation

            save_high_entropy_observation(
                ngram_profile,
                mouse_profile,
                [],
                context_id=context_id,
                app_name=app_name,
                label="calibrated_owner",
                data_source="interactive_calibration",
            )
        except Exception:
            pass

        confidence = min(100, int((digraph_samples + mouse_samples * 2) / 2))
        self._write_status(
            "complete",
            "Owner baseline saved from measured calibration events.",
            context_id=context_id,
            app_name=app_name,
            confidence_pct=confidence,
            digraph_samples=digraph_samples,
            mouse_samples=mouse_samples,
        )
        return read_json(self.status_path)

    def cancel(self) -> None:
        self.phase = None
        self.expires_at = 0.0
        self._write_status("cancelled", "Calibration cancelled; no new owner baseline was saved.")

