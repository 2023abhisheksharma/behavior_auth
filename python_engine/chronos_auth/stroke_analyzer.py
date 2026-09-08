import math
import numpy as np
from collections import deque
from typing import List, Dict, Any, Optional

class MouseStroke:
    """Represents a single continuous goal-directed mouse movement stroke."""
    def __init__(self):
        self.points = []  # list of (timestamp_us, dx, dy)
        self.start_time = 0
        self.end_time = 0
        self.click_dwell_us = 0
        self.has_click = False
        self.hand_transition_latency_us = 0.0
        self.pre_click_deceleration_us = 0.0
        self.pre_click_pause_us = 0.0

    def add_point(self, ts_us: int, dx: int, dy: int):
        if not self.points:
            self.start_time = ts_us
        self.end_time = ts_us
        self.points.append((ts_us, dx, dy))

    @property
    def point_count(self) -> int:
        return len(self.points)


class StrokeAnalyzer:
    """
    Decomposes continuous mouse telemetry into discrete ballistic strokes and
    extracts fine-grained kinematic features (Bézier tortuosity, jerk, velocity profiles).
    """

    def __init__(self, pause_threshold_us: int = 60000):  # 60ms pause delimits strokes
        self.pause_threshold = pause_threshold_us
        self.current_stroke = MouseStroke()
        self.completed_strokes = deque(maxlen=50)

        self.last_move_time = 0
        self.last_key_up_time = None  # for Hand-Transition Latency (HTL)

        self.pending_clicks = {}  # btn_code -> down_time_us

    def register_key_up(self, ts_us: int):
        """Notified whenever a keyboard key is released to track hand transitions."""
        self.last_key_up_time = ts_us

    def register_mouse_button(self, ts_us: int, btn_code: int, is_down: bool):
        """Notified on mouse button press or release."""
        if is_down:
            self.pending_clicks[btn_code] = ts_us
            self._record_pre_click_dynamics(ts_us)
        else:
            if btn_code in self.pending_clicks:
                dwell = ts_us - self.pending_clicks.pop(btn_code)
                if self.current_stroke.point_count > 0:
                    self.current_stroke.has_click = True
                    self.current_stroke.click_dwell_us = dwell
                self._finish_stroke()

    def _record_pre_click_dynamics(self, click_ts_us: int):
        """Captures measured deceleration and pause immediately before a click."""
        points = self.current_stroke.points
        if len(points) < 3:
            return

        velocity_samples = []
        for index in range(1, len(points)):
            prev_t, _prev_dx, _prev_dy = points[index - 1]
            current_t, dx, dy = points[index]
            dt_sec = (current_t - prev_t) / 1_000_000.0
            if dt_sec > 1e-5:
                velocity_samples.append((current_t, math.hypot(dx, dy) / dt_sec))
        if not velocity_samples:
            return

        peak_index = max(range(len(velocity_samples)), key=lambda index: velocity_samples[index][1])
        peak_time, peak_velocity = velocity_samples[peak_index]
        last_velocity = velocity_samples[-1][1]
        if peak_index < len(velocity_samples) - 1 and last_velocity < peak_velocity:
            self.current_stroke.pre_click_deceleration_us = max(0.0, float(click_ts_us - peak_time))
        self.current_stroke.pre_click_pause_us = max(0.0, float(click_ts_us - points[-1][0]))

    def add_move(self, ts_us: int, dx: int, dy: int):
        """Processes raw MOUSE_MOVE event with microsecond timestamp."""
        if (dx == 0 and dy == 0):
            return

        # Check for pause segmentation
        if self.last_move_time > 0 and (ts_us - self.last_move_time) > self.pause_threshold:
            self._finish_stroke()

        if self.current_stroke.point_count == 0:
            # First movement in stroke: measure hand transition latency from keyboard
            if self.last_key_up_time is not None:
                htl = ts_us - self.last_key_up_time
                if 0 < htl < 5000000:  # Valid transition within 5 seconds
                    self.current_stroke.hand_transition_latency_us = float(htl)

        self.current_stroke.add_point(ts_us, dx, dy)
        self.last_move_time = ts_us

    def _finish_stroke(self):
        if self.current_stroke.point_count >= 3:
            self.completed_strokes.append(self.current_stroke)
        self.current_stroke = MouseStroke()

    def extract_kinematic_features(self, strokes: Optional[List[MouseStroke]] = None) -> Dict[str, float]:
        """
        Extracts kinematic metrics across recent completed strokes.
        Returns a dictionary of fine-grained motor control biometrics.
        """
        if strokes is None:
            strokes = list(self.completed_strokes)

        if not strokes:
            self._last_ballistic_samples = {}
            return {
                "stroke_tortuosity_mean": np.nan,
                "stroke_jerk_rms": np.nan,
                "stroke_accel_symmetry": np.nan,
                "stroke_peak_velocity_mean": np.nan,
                "click_dwell_mean_ms": np.nan,
                "htl_mean_ms": np.nan,
                "mean_velocity": np.nan,
                "std_velocity": np.nan,
                "mean_acc": np.nan,
                "direction_rate": np.nan,
                "ballistic_accel_peaks_mean": np.nan,
                "trajectory_curvature_entropy": np.nan,
                "bezier_inflection_count_mean": np.nan,
                "pre_click_deceleration_ms": np.nan,
                "pre_click_pause_ms": np.nan,
                "mouse_interval_jitter_ms": np.nan,
                "mouse_point_count": 0.0,
                "completed_stroke_count": 0.0,
            }

        tortuosities = []
        jerks = []
        symmetries = []
        peak_vels = []
        click_dwells = []
        htls = []
        all_velocities = []
        all_accelerations = []
        direction_changes = 0
        direction_samples = 0
        acceleration_peaks = []
        curvature_entropies = []
        inflection_counts = []
        pre_click_decelerations = []
        pre_click_pauses = []
        interval_jitters = []

        for stroke in strokes:
            pts = stroke.points
            if len(pts) < 3:
                continue

            dt_total_sec = max((stroke.end_time - stroke.start_time) / 1e6, 1e-4)

            # Cumulative trajectory vs Euclidean displacement
            cum_dist = 0.0
            cum_x = 0
            cum_y = 0

            velocities = []
            vel_times = []
            prev_t = pts[0][0]

            for t, dx, dy in pts:
                step_dist = math.hypot(dx, dy)
                cum_dist += step_dist
                cum_x += dx
                cum_y += dy

                dt = (t - prev_t) / 1e6
                if dt > 1e-5:
                    v = step_dist / dt
                    velocities.append(v)
                    all_velocities.append(v)
                    vel_times.append((t - stroke.start_time) / 1e6)
                    if len(velocities) > 1:
                        dt_v = max(vel_times[-1] - vel_times[-2], 1e-4)
                        all_accelerations.append((velocities[-1] - velocities[-2]) / dt_v)
                prev_t = t

            point_intervals_ms = [
                (pts[index][0] - pts[index - 1][0]) / 1000.0
                for index in range(1, len(pts))
                if pts[index][0] > pts[index - 1][0]
            ]
            if len(point_intervals_ms) >= 2:
                interval_jitters.append(float(np.std(point_intervals_ms)))

            previous_angle = None
            previous_turn_sign = 0
            stroke_inflections = 0
            curvature_deltas = []
            movement_vectors = []
            for _t, dx, dy in pts:
                if dx == 0 and dy == 0:
                    continue
                angle = math.atan2(dy, dx)
                if previous_angle is not None:
                    direction_samples += 1
                    angle_delta = abs(angle - previous_angle)
                    angle_delta = min(angle_delta, (2.0 * math.pi) - angle_delta)
                    curvature_deltas.append(angle_delta)
                    if angle_delta > math.pi / 4:
                        direction_changes += 1
                previous_angle = angle
                movement_vectors.append((dx, dy))

            for index in range(1, len(movement_vectors)):
                left_dx, left_dy = movement_vectors[index - 1]
                right_dx, right_dy = movement_vectors[index]
                cross = left_dx * right_dy - left_dy * right_dx
                if abs(cross) < 1e-6:
                    continue
                turn_sign = 1 if cross > 0 else -1
                if previous_turn_sign and turn_sign != previous_turn_sign:
                    stroke_inflections += 1
                previous_turn_sign = turn_sign
            if curvature_deltas:
                histogram, _ = np.histogram(curvature_deltas, bins=6, range=(0.0, math.pi))
                probabilities = histogram[histogram > 0] / max(histogram.sum(), 1)
                entropy = -float(np.sum(probabilities * np.log(probabilities)))
                curvature_entropies.append(entropy / math.log(6.0))
            inflection_counts.append(float(stroke_inflections))

            net_disp = math.hypot(cum_x, cum_y)
            tortuosity = cum_dist / max(net_disp, 1.0)
            tortuosities.append(min(tortuosity, 5.0))  # clip outliers

            if velocities:
                peak_v = max(velocities)
                peak_vels.append(peak_v)

                # Symmetry: fraction of stroke duration before peak velocity
                peak_idx = velocities.index(peak_v)
                peak_time = vel_times[peak_idx] if peak_idx < len(vel_times) else 0.0
                symmetry = peak_time / dt_total_sec
                symmetries.append(min(max(symmetry, 0.0), 1.0))

            # Jerk calculation (3rd derivative)
            if len(velocities) >= 3:
                accels = []
                for i in range(1, len(velocities)):
                    dt_v = max(vel_times[i] - vel_times[i - 1], 1e-4)
                    accels.append((velocities[i] - velocities[i - 1]) / dt_v)

                jerk_vals = []
                for i in range(1, len(accels)):
                    dt_a = max(vel_times[i + 1] - vel_times[i], 1e-4)
                    jerk_vals.append((accels[i] - accels[i - 1]) / dt_a)

                if jerk_vals:
                    rms_jerk = float(np.sqrt(np.mean(np.square(jerk_vals))))
                    jerks.append(min(rms_jerk, 1e6))

                if len(accels) >= 3:
                    magnitudes = np.abs(np.asarray(accels, dtype=float))
                    peak_threshold = float(np.percentile(magnitudes, 65))
                    peak_count = sum(
                        1
                        for index in range(1, len(magnitudes) - 1)
                        if magnitudes[index] > peak_threshold
                        and magnitudes[index] >= magnitudes[index - 1]
                        and magnitudes[index] >= magnitudes[index + 1]
                    )
                    acceleration_peaks.append(float(peak_count))

            if stroke.has_click and stroke.click_dwell_us > 0:
                click_dwells.append(stroke.click_dwell_us / 1000.0)
            if stroke.pre_click_deceleration_us > 0:
                pre_click_decelerations.append(stroke.pre_click_deceleration_us / 1000.0)
            if stroke.pre_click_pause_us > 0:
                pre_click_pauses.append(stroke.pre_click_pause_us / 1000.0)

            if stroke.hand_transition_latency_us > 0:
                htls.append(stroke.hand_transition_latency_us / 1000.0)

        ballistic_samples = {
            "ballistic_accel_peaks_mean": acceleration_peaks,
            "trajectory_curvature_entropy": curvature_entropies,
            "bezier_inflection_count_mean": inflection_counts,
            "pre_click_deceleration_ms": pre_click_decelerations,
            "pre_click_pause_ms": pre_click_pauses,
            "mouse_interval_jitter_ms": interval_jitters,
        }
        self._last_ballistic_samples = ballistic_samples
        return {
            "stroke_tortuosity_mean": float(np.mean(tortuosities)) if tortuosities else np.nan,
            "stroke_jerk_rms": float(np.mean(jerks)) if jerks else np.nan,
            "stroke_accel_symmetry": float(np.mean(symmetries)) if symmetries else np.nan,
            "stroke_peak_velocity_mean": float(np.mean(peak_vels)) if peak_vels else np.nan,
            "click_dwell_mean_ms": float(np.mean(click_dwells)) if click_dwells else np.nan,
            "htl_mean_ms": float(np.mean(htls)) if htls else np.nan,
            "mean_velocity": float(np.mean(all_velocities)) if all_velocities else np.nan,
            "std_velocity": float(np.std(all_velocities)) if all_velocities else np.nan,
            "mean_acc": float(np.mean(all_accelerations)) if all_accelerations else np.nan,
            "direction_rate": direction_changes / direction_samples if direction_samples else np.nan,
            "ballistic_accel_peaks_mean": float(np.mean(acceleration_peaks)) if acceleration_peaks else np.nan,
            "trajectory_curvature_entropy": float(np.mean(curvature_entropies)) if curvature_entropies else np.nan,
            "bezier_inflection_count_mean": float(np.mean(inflection_counts)) if inflection_counts else np.nan,
            "pre_click_deceleration_ms": float(np.mean(pre_click_decelerations)) if pre_click_decelerations else np.nan,
            "pre_click_pause_ms": float(np.mean(pre_click_pauses)) if pre_click_pauses else np.nan,
            "mouse_interval_jitter_ms": float(np.mean(interval_jitters)) if interval_jitters else np.nan,
            "mouse_point_count": float(sum(stroke.point_count for stroke in strokes)),
            "completed_stroke_count": float(len(strokes)),
        }

    def extract_ballistic_profile(self, strokes: Optional[List[MouseStroke]] = None) -> Dict[str, Dict[str, float]]:
        """Returns measured per-stroke summaries for owner-baseline calibration."""
        self.extract_kinematic_features(strokes)
        profile = {}
        for key, values in getattr(self, "_last_ballistic_samples", {}).items():
            array = np.asarray(values, dtype=float)
            if array.size:
                profile[key] = {
                    "count": int(array.size),
                    "mean": float(np.mean(array)),
                    "std": float(np.std(array)),
                }
        return profile
