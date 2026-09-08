import os
import sys
import time
import math
import subprocess
import numpy as np
from typing import Dict, Any, Optional, List

from chronos_auth.context_detector import ContextDetector, CONTEXT_NAMES
from chronos_auth.stroke_analyzer import StrokeAnalyzer
from chronos_auth.ngram_analyzer import NgramAnalyzer
from chronos_auth.chord_analyzer import ChordAnalyzer
from chronos_auth.antibot_detector import AntiBotDetector
from chronos_auth.bluetooth_proximity import BluetoothProximityMonitor
from chronos_auth.chronos_features import assemble_chronos_vector, CHRONOS_FEATURE_DIM
from chronos_auth.contrastive_model import ContrastiveBiometricModel
from chronos_auth.sprt_trust_engine import SPRTTrustEngine
from chronos_auth.high_entropy import HighEntropyProfileStore, FastThreatDetector, FeatureImpact
from chronos_auth.runtime_config import (
    SecurityPolicyStore,
    LOCK_MODE_PATH,
    LIVE_STATE_PATH,
    RESET_TRIGGER_PATH,
    LEGACY_LIVE_STATE_PATH,
    LEGACY_RESET_TRIGGER_PATH,
    get_lock_mode,
)
from chronos_auth.calibration import CalibrationSession
from chronos_auth.feature_attribution import normalize_impacts
from chronos_auth.system_actions import lock_workstation
from chronos_auth.remote_service import RemoteAlertDispatcher


class ChronosRealtimePipeline:
    """
    Sub-Second Dual-Horizon Continuous Authentication Engine.
    Processes live hardware telemetry, extracts kinematic & neuromuscular biometrics,
    profiles high-entropy n-gram timing and ballistic trajectories, monitors Bluetooth proximity,
    detects automated injection attacks, and executes Wald's Sequential Probability Ratio Test (SPRT).
    """

    def __init__(self, simulate_lock: Optional[bool] = None):
        if simulate_lock is None:
            self.simulate_lock = (get_lock_mode() != "enforce")
        else:
            self.simulate_lock = simulate_lock
        self.default_simulate_lock = self.simulate_lock

        self.context_detector = ContextDetector()
        self.stroke_analyzer = StrokeAnalyzer()
        self.ngram_analyzer = NgramAnalyzer()
        self.chord_analyzer = ChordAnalyzer()
        self.antibot_detector = AntiBotDetector()
        self.bluetooth_monitor = BluetoothProximityMonitor()

        self.model = ContrastiveBiometricModel()
        self.policy_store = SecurityPolicyStore()
        self.profile_store = HighEntropyProfileStore()
        self.fast_threat_detector = FastThreatDetector()
        self.calibration_session = CalibrationSession(profile_store=self.profile_store)
        self.sprt = SPRTTrustEngine(target_far=0.005, target_frr=0.01)
        self.remote_dispatcher = RemoteAlertDispatcher(policy_store=self.policy_store)

        self.event_counter = 0
        self.last_eval_time = time.time()
        self.eval_interval_seconds = 1.5  # Sub-second fast-path evaluation

        # Recent key count in current window
        self.key_presses_since_eval = 0
        self.last_key_press_time = None
        self.lock_mode_path = str(LOCK_MODE_PATH)

    def process_event(self, event: Dict[str, Any]):
        """Ingests raw event from event_processor."""
        self.simulate_lock = (get_lock_mode() != "enforce")

        self.event_counter += 1
        ts = event["timestamp"]
        ev_type = event["type"]

        if self.calibration_session.phase:
            app_name = self.context_detector.get_active_app()
            context_id = self.context_detector.cached_context_id
            self.calibration_session.record_event(event, context_id=context_id, app_name=app_name)
        else:
            self.calibration_session.poll_control()

        if ev_type == "KEY_DOWN":
            code = event.get("key_code", 0)
            self.ngram_analyzer.register_key_down(ts, code)
            self.chord_analyzer.register_key_down(ts, code)
            self.key_presses_since_eval += 1
            self.last_key_press_time = ts

        elif ev_type == "KEY_UP":
            code = event.get("key_code", 0)
            dwell_ms = self.ngram_analyzer.register_key_up(ts, code)
            self.chord_analyzer.register_key_up(ts, code)
            self.stroke_analyzer.register_key_up(ts)
            if dwell_ms is not None:
                flight_ms = float((ts - (self.last_key_press_time or ts)) / 1000.0)
                self.antibot_detector.record_key_stroke(dwell_ms, flight_ms, ts)

        elif ev_type == "MOUSE_MOVE":
            dx = event.get("dx", 0)
            dy = event.get("dy", 0)
            self.stroke_analyzer.add_move(ts, dx, dy)

        elif ev_type in ("MOUSE_DOWN", "MOUSE_UP"):
            code = event.get("key_code", 0)
            is_down = (ev_type == "MOUSE_DOWN")
            self.stroke_analyzer.register_mouse_button(ts, code, is_down)

        # Check for user-initiated reset trigger (isolated or legacy path)
        for trig in (RESET_TRIGGER_PATH, LEGACY_RESET_TRIGGER_PATH):
            if trig.exists():
                try:
                    trig.unlink(missing_ok=True)
                    self.sprt.reset_to_owner()
                    print("[Chronos] SPRT trust accumulator reset to Genuine Owner state.", flush=True)
                except Exception:
                    pass

        # Check if it's time for an SPRT evaluation:
        # Evaluates whenever:
        # 1. 8 keystrokes have occurred, OR
        # 2. A mouse stroke finished, OR
        # 3. 1.5 seconds have elapsed since last check with active events
        now = time.time()
        dt = now - self.last_eval_time

        should_eval = (
            self.key_presses_since_eval >= 8 or
            (len(self.stroke_analyzer.completed_strokes) >= 2) or
            (dt >= self.eval_interval_seconds and (self.key_presses_since_eval > 0 or self.stroke_analyzer.current_stroke.point_count > 0))
        )

        if should_eval:
            self.evaluate_subsecond()
            self.last_eval_time = now
            self.key_presses_since_eval = 0

    def evaluate_subsecond(self):
        """Extracts multi-modal features, fuses high-entropy baselines, and executes SPRT."""
        if not self.ngram_analyzer.all_dwells:
            return

        # Load security policy and update SPRT sensitivity/thresholds
        policy = self.policy_store.load()
        sensitivity = policy.get("sensitivity", "Balanced")
        warning_thresh = policy.get("warning_threshold", 50)
        self.sprt.set_sensitivity(sensitivity, warning_thresh)

        # Active application context & policy rules
        app_name = self.context_detector.get_active_app()
        context_id = self.context_detector.cached_context_id
        context_name = CONTEXT_NAMES.get(context_id, "Unknown")
        active_app_lower = app_name.lower()

        now = time.time()
        snooze_until = float(policy.get("snooze_until", 0.0))
        is_snoozed = now < snooze_until
        excluded_apps = policy.get("excluded_apps", [])
        is_excluded = any(ex and ex in active_app_lower for ex in excluded_apps)

        # 0. Check for Hardware Injection / Rubber Ducky / Superhuman Bot
        is_bot, bot_type, bot_conf = self.antibot_detector.check_attack()

        # 1. Check for Bluetooth Proximity / Walk-Away Lock
        prox_score, is_connected, walk_away = self.bluetooth_monitor.get_status()
        now_us = int(time.time() * 1_000_000)
        quiet_us = (
            now_us - self.last_key_press_time
            if self.last_key_press_time is not None
            else 8_000_001
        )

        # 2. Kinematic mouse stroke features
        kinematics = self.stroke_analyzer.extract_kinematic_features()
        if self.stroke_analyzer.completed_strokes:
            last_stroke = self.stroke_analyzer.completed_strokes[-1]
            dt_stroke = max((last_stroke.end_time - last_stroke.start_time) / 1e6, 0.001)
            self.antibot_detector.record_mouse_stroke(
                kinematics["stroke_tortuosity_mean"],
                kinematics["stroke_peak_velocity_mean"],
                dt_stroke,
            )

        # 3. Neuromuscular keystroke timing
        neuromuscular = self.ngram_analyzer.extract_neuromuscular_features()

        dwell_ms = neuromuscular["dwell_mean_ms"]
        flight_ms = neuromuscular["flight_mean_ms"]
        dwell_values = np.asarray(self.ngram_analyzer.all_dwells, dtype=float)
        flight_values = np.asarray(self.ngram_analyzer.all_flights, dtype=float)
        typing_speed = self.ngram_analyzer.recent_typing_speed()
        if not np.isfinite(typing_speed):
            elapsed_ms = float(dwell_values.sum() + flight_values.sum())
            typing_speed = len(dwell_values) / (elapsed_ms / 1000.0) if elapsed_ms > 0 else np.nan
        dwell_std_ms = self.ngram_analyzer.recent_dwell_std_ms()
        if not np.isfinite(dwell_std_ms) and len(dwell_values) >= 2:
            dwell_std_ms = float(np.std(dwell_values))

        # 4. High-Entropy Biometrics & Fast Threat Assessment
        ngram_profile = self.ngram_analyzer.extract_timing_profile(min_count=2)
        mouse_profile = self.stroke_analyzer.extract_ballistic_profile()
        he_assessment = self.profile_store.assess(context_id, ngram_profile, mouse_profile)

        fast_threats = self.fast_threat_detector.evaluate(
            typing_speed=typing_speed,
            dwell_std_ms=dwell_std_ms,
            dwell_count=len(dwell_values),
            mouse_interval_jitter_ms=kinematics.get("mouse_interval_jitter_ms"),
            mouse_point_count=int(kinematics.get("mouse_point_count", 0)),
            high_entropy=he_assessment,
        )

        # Check for immediate critical attacks (hardware injection / impossible physics)
        has_critical_threat = bool(fast_threats) or is_bot or (walk_away and quiet_us > 8_000_000)

        # Robust baselines for sparse typing / low sample counts
        # When typing very little, sample variance is uncomputable (0 or nan).
        # We supply the neutral owner baseline values so sparse typing does not falsely trigger impostor weights.
        neutral_std_dwell_us = 106689.0
        neutral_flight_us = 250000.0
        neutral_std_flight_us = 1466852.0
        neutral_speed = 1.15

        dwell_us = dwell_ms * 1000.0 if np.isfinite(dwell_ms) else 150000.0
        dwell_std_us = float(np.std(dwell_values) * 1000.0) if len(dwell_values) >= 3 else neutral_std_dwell_us
        flight_us = flight_ms * 1000.0 if (np.isfinite(flight_ms) and len(flight_values) >= 1) else neutral_flight_us
        flight_std_us = float(np.std(flight_values) * 1000.0) if len(flight_values) >= 3 else neutral_std_flight_us
        speed_val = typing_speed if (np.isfinite(typing_speed) and typing_speed > 0.1) else neutral_speed

        # 5. Assemble full 26D Chronos Vector & Contrastive Model Scoring
        legacy_features = [
            dwell_us,
            dwell_std_us,
            flight_us,
            flight_std_us,
            speed_val,
            kinematics["mean_velocity"],
            kinematics["std_velocity"],
            kinematics["mean_acc"],
            kinematics["direction_rate"],
            neuromuscular["space_dwell_ms"] * 1000.0 if np.isfinite(neuromuscular["space_dwell_ms"]) else np.nan,
            neuromuscular["enter_dwell_ms"] * 1000.0 if np.isfinite(neuromuscular["enter_dwell_ms"]) else np.nan,
            neuromuscular["space_frequency"],
            neuromuscular["enter_frequency"],
            float(context_id),
        ]

        vector = assemble_chronos_vector(
            legacy_features=legacy_features,
            kinematic_features=kinematics,
            neuromuscular_features=neuromuscular,
            active_context_id=context_id,
        )

        # Compute Log-Likelihood Ratio from contrastive representation
        log_lr, p_imp, model_source = self.model.compute_log_likelihood_ratio(vector)

        # Shortcut dynamics delta
        chord_stats = self.chord_analyzer.extract_chord_features()
        shortcut_delta = 0.0
        if chord_stats["chords_detected"] >= 2:
            lead_std = chord_stats.get("chord_lead_std_ms", float("nan"))
            if np.isfinite(lead_std) and lead_std < 15.0:
                # Highly practiced muscle memory shortcut execution: cushion evidence
                shortcut_delta = -0.25
                log_lr += shortcut_delta

        # Apply phone proximity cushion
        if is_connected and prox_score >= 0.8:
            # Phone confirmed beside user: cushion against false rejections
            log_lr = log_lr - 0.35

        # High-entropy fusion: When calibrated owner baseline is available,
        # fuse high-entropy impostor probability proportionally to its confidence
        if he_assessment.available and he_assessment.p_impostor is not None:
            he_p = he_assessment.p_impostor
            he_conf = he_assessment.confidence
            weight = min(0.85, he_conf * 0.9)
            p_imp = float(np.clip((1.0 - weight) * p_imp + weight * he_p, 0.0001, 0.9999))
            he_log_lr = math.log(he_p / max(1.0 - he_p, 1e-6))
            log_lr = (1.0 - weight) * log_lr + weight * he_log_lr
            model_source = f"{model_source}+HighEntropy({he_assessment.context_source})"

        # Evidence-Gated Accumulation for Sparse Typing:
        # If user types very little (< 5 keys in this window) and no critical bot/injection threat exists:
        # We do NOT accumulate impostor debt against the legitimate user!
        # High confidence impostor evidence requires statistical sample mass.
        # Genuine evidence (log_lr < 0) is freely credited.
        recent_keys = self.key_presses_since_eval
        if not has_critical_threat and log_lr > 0:
            if recent_keys < 5:
                # Sparse typing: user typed very few keys. Do not penalize with impostor debt!
                log_lr = min(log_lr, 0.0)
                p_imp = min(p_imp, 0.50)
            else:
                confidence = min(1.0, recent_keys / 8.0)
                log_lr = log_lr * confidence

        # If an impossible physical threat or bot injection was caught, force immediate high impostor evidence
        if has_critical_threat:
            p_imp = 0.9999
            log_lr = max(log_lr, self.sprt.A + 1.0)

        # Update Wald's SPRT Accumulator
        action, trust_pct, stats = self.sprt.update(log_lr, p_imp)

        # Snooze / Excluded App Override: prevent lockout but maintain telemetry
        if is_snoozed:
            action = "CONTINUE"
        elif is_excluded:
            action = "CONTINUE"

        # Adaptive baseline update: If user is verified genuine, adapt slowly
        if policy.get("adaptive_baselines", True) and not is_snoozed and not is_excluded:
            if action == "CONTINUE" and p_imp < 0.30 and trust_pct > 75.0:
                self.profile_store.adapt(context_id, ngram_profile, mouse_profile, rate=0.015)

        # Save continuous telemetry to SQLite
        if self.event_counter % 5 == 0:
            try:
                from database import save_features
                save_features(
                    vector,
                    label="unverified_live",
                    data_source="local_chronos",
                    keyboard_event_count=len(self.ngram_analyzer.all_dwells),
                    mouse_event_count=len(self.stroke_analyzer.completed_strokes),
                )
            except Exception:
                pass

        if self.event_counter % 10 == 0:
            try:
                from database import save_high_entropy_observation
                save_high_entropy_observation(
                    ngram_profile,
                    mouse_profile,
                    [impact.to_dict() for impact in he_assessment.impacts],
                    context_id=context_id,
                    app_name=app_name,
                    label="unverified_live",
                    data_source="local_chronos",
                )
            except Exception:
                pass

        # Collect and format human-readable feature attribution impacts
        all_impacts: List[Dict[str, Any]] = []
        if is_snoozed:
            remaining_min = max(0, int((snooze_until - now) / 60))
            all_impacts.append({
                "signal": "policy:snooze",
                "severity": "info",
                "text": f"Snooze active (~{remaining_min}m remaining); automated lockouts paused",
            })
        elif is_excluded:
            all_impacts.append({
                "signal": "policy:excluded_app",
                "severity": "info",
                "text": f"Application '{app_name}' is on the security exclusion list",
            })

        for threat in fast_threats:
            all_impacts.append(threat.to_dict())

        if is_bot:
            all_impacts.append({
                "signal": "antibot:injection",
                "severity": "critical",
                "text": f"Hardware/Synthetic Keystroke Injection: {bot_type} ({self.antibot_detector.last_attack_reason})",
            })

        if walk_away and quiet_us > 8_000_000:
            all_impacts.append({
                "signal": "bluetooth:walk_away",
                "severity": "critical",
                "text": "Walk-away triggered: paired Bluetooth device out of range",
            })

        # Real ML classifier feature attributions (keystroke dynamics vs learned owner baseline)
        ml_impacts = self.model.explain_features(vector)
        for imp in ml_impacts:
            all_impacts.append(imp)

        # Kinematic mouse movement attribution if mouse was moved
        if len(self.stroke_analyzer.completed_strokes) > 0:
            tort = kinematics.get("stroke_tortuosity_mean")
            if tort is not None and np.isfinite(tort):
                all_impacts.append({
                    "signal": "ml:mouse_tortuosity",
                    "severity": "positive" if 1.02 <= tort <= 2.5 else "warning",
                    "text": f"Motor kinematics: natural curved mouse trajectory (tortuosity {tort:.2f}) with human tremor",
                })

        if he_assessment.available:
            for imp in he_assessment.impacts:
                all_impacts.append(imp.to_dict())
            if not any(i.get("signal", "").startswith("high_entropy") for i in all_impacts):
                all_impacts.append({
                    "signal": "high_entropy:match",
                    "severity": "positive",
                    "text": f"High-entropy baseline matched ({he_assessment.context_source}): rhythm conforms to owner profile",
                })

        impact_lines = normalize_impacts(all_impacts, limit=5)

        # Format and display real-time telemetry
        action_icons = {
            "CONTINUE": "🟢 [CONTINUE]",
            "ALERT": "🟡 [ALERT]",
            "LOCK": "🔴 [LOCK WORKSTATION]",
        }
        icon = action_icons.get(action, "[STATUS]")

        print(
            f"[CHRONOS-AUTH] Trust: {trust_pct:5.1f}% | "
            f"Instant: {(1.0 - p_imp) * 100.0:5.1f}% | "
            f"LLR: {stats['cumulative_llr']:+5.2f} (A={stats['boundary_A_lock']:.1f}, B={stats['boundary_B_trust']:.1f}) | "
            f"P(Imp): {p_imp:.2f} | "
            f"Dwell: {dwell_ms:.1f}ms | Flight: {flight_ms:.1f}ms | "
            f"Context: {context_name:<14} | "
            f"{icon}",
            flush=True
        )

        try:
            import json
            instant_owner_pct = (1.0 - p_imp) * 100.0
            def live_number(value, digits):
                return round(float(value), digits) if np.isfinite(value) else None

            live_payload = {
                "timestamp": time.time(),
                "trust_pct": round(trust_pct, 1),
                "instant_score_pct": round(instant_owner_pct, 2),
                "cumulative_llr": round(stats["cumulative_llr"], 2),
                "boundary_a": round(stats["boundary_A_lock"], 2),
                "boundary_b": round(stats["boundary_B_trust"], 2),
                "boundary_w": round(stats["boundary_W_alert"], 2),
                "log_lr": round(log_lr, 2),
                "p_imp": round(p_imp, 6),
                "p_owner": round(1.0 - p_imp, 6),
                "model_source": model_source,
                "keyboard_events": len(self.ngram_analyzer.all_dwells),
                "mouse_strokes": len(self.stroke_analyzer.completed_strokes),
                "mouse_evidence_used": model_source.endswith("+MeasuredMouse"),
                "high_entropy_available": bool(he_assessment.available),
                "high_entropy_confidence": round(float(he_assessment.confidence), 2),
                "high_entropy_context": he_assessment.context_source,
                "action": action,
                "status_text": f"Snoozed ({int((snooze_until - now)/60)}m)" if is_snoozed else (f"Excluded ({app_name})" if is_excluded else action),
                "snoozed": is_snoozed,
                "excluded": is_excluded,
                "sensitivity": sensitivity,
                "warning_threshold": warning_thresh,
                "context": context_name,
                "app_name": app_name,
                "jerk_rms": live_number(kinematics.get("stroke_jerk_rms", np.nan), 2),
                "tortuosity": live_number(kinematics.get("stroke_tortuosity_mean", np.nan), 2),
                "curvature_entropy": live_number(kinematics.get("trajectory_curvature_entropy", np.nan), 2),
                "dwell_mean_ms": live_number(dwell_ms, 1),
                "flight_mean_ms": live_number(flight_ms, 1),
                "typing_speed": live_number(typing_speed, 1),
                "dwell_std_ms": live_number(dwell_std_ms, 2),
                "shortcut_delta": shortcut_delta,
                "phone_connected": is_connected,
                "phone_rssi": self.bluetooth_monitor.last_rssi,
                "phone_score": prox_score,
                "event_counter": self.event_counter,
                "impacts": all_impacts,
                "impact_lines": impact_lines,
            }
            state_json = json.dumps(live_payload)
            for state_target in (LIVE_STATE_PATH, LEGACY_LIVE_STATE_PATH):
                try:
                    state_target.parent.mkdir(parents=True, exist_ok=True)
                    tmp_file = state_target.with_suffix(".tmp")
                    tmp_file.write_text(state_json, encoding="utf-8")
                    tmp_file.replace(state_target)
                except OSError:
                    pass
        except Exception:
            pass

        # Dispatch remote alerts & lockouts
        if not is_snoozed and not is_excluded:
            if action == "LOCK":
                self.remote_dispatcher.notify_lockout(
                    reason="Cumulative log-likelihood crossed Wald lockout barrier",
                    impact_lines=impact_lines,
                    capture_snapshot=True,
                )
                self._trigger_lockout()
            elif action == "ALERT" or trust_pct < float(warning_thresh):
                self.remote_dispatcher.notify_warning(
                    trust_pct=trust_pct,
                    threshold=float(warning_thresh),
                    impact_lines=impact_lines,
                    instant_score=instant_owner_pct,
                )
            elif walk_away and quiet_us > 8_000_000:
                self.remote_dispatcher.notify_walkaway()

    def _trigger_lockout(self):
        """Executes actual or simulated screen lock."""
        print("\n" + "=" * 60)
        print(" 🚨 CRITICAL SECURITY ALERT: BEHAVIORAL MISMATCH DETECTED!")
        print(" 🚨 Workstation Lock Triggered by Chronos-Auth SPRT Engine")
        print("=" * 60 + "\n")

        if self.simulate_lock:
            print("[Chronos] (Simulation mode: screen locking command suppressed)")
            return

        ok, reason = lock_workstation()
        print(f"[Chronos] Lock workstation result: {ok} ({reason})")
