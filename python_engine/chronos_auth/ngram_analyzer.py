import numpy as np
from collections import defaultdict, deque
from typing import Any, Dict, List, Optional, Tuple

# Evdev scancode mappings for hand zone neuromuscular analysis
LEFT_HAND_KEYS = {
    16, 17, 18, 19, 20,       # Q, W, E, R, T
    30, 31, 32, 33, 34,       # A, S, D, F, G
    44, 45, 46, 47, 48,       # Z, X, C, V, B
    1, 2, 3, 4, 5, 6,         # Esc, 1, 2, 3, 4, 5
    15, 29, 42, 56, 58,       # Tab, L-Ctrl, L-Shift, L-Alt, Caps
}

RIGHT_HAND_KEYS = {
    21, 22, 23, 24, 25, 26, 27,  # Y, U, I, O, P, [, ]
    35, 36, 37, 38, 39, 40, 43,  # H, J, K, L, ;, ', \
    49, 50, 51, 52, 53, 54,      # N, M, ,, ., /, R-Shift
    7, 8, 9, 10, 11, 12, 13, 14, # 6, 7, 8, 9, 0, -, =, Backspace
    28, 97, 100,                 # Enter, R-Ctrl, R-Alt
}

SPECIAL_SPACE = 57
SPECIAL_ENTER = 28
SPECIAL_BACKSPACE = 14
SPECIAL_DELETE = 111

WINDOWS_KEY_TO_LINUX = {
    8: SPECIAL_BACKSPACE,
    9: 15,
    13: SPECIAL_ENTER,
    16: 42,
    17: 29,
    18: 56,
    20: 58,
    27: 1,
    32: SPECIAL_SPACE,
    46: SPECIAL_DELETE,
}
WINDOWS_DIGIT_TO_LINUX = {48: 11, 49: 2, 50: 3, 51: 4, 52: 5, 53: 6, 54: 7, 55: 8, 56: 9, 57: 10}
LINUX_LETTER_CODES = dict(zip("ABCDEFGHIJKLMNOPQRSTUVWXYZ", (30, 48, 46, 32, 18, 33, 34, 35, 23, 36, 37, 38, 50, 49, 24, 25, 16, 19, 31, 20, 22, 47, 17, 45, 21, 44)))
KEY_NAMES = {code: letter for letter, code in LINUX_LETTER_CODES.items()}
KEY_NAMES.update({
    SPECIAL_SPACE: "Space",
    SPECIAL_ENTER: "Enter",
    SPECIAL_BACKSPACE: "Backspace",
    SPECIAL_DELETE: "Delete",
    15: "Tab",
    29: "Ctrl",
    42: "Shift",
    54: "Shift",
    56: "Alt",
    100: "Alt",
    103: "Up",
    104: "PageUp",
    105: "Left",
    106: "Right",
    107: "End",
    108: "Down",
    109: "PageDown",
})


def normalize_windows_key_code(key_code: int) -> int:
    """Maps Windows virtual-key codes to the canonical evdev codes."""
    if 65 <= key_code <= 90:
        return LINUX_LETTER_CODES[chr(key_code)]
    if key_code in WINDOWS_DIGIT_TO_LINUX:
        return WINDOWS_DIGIT_TO_LINUX[key_code]
    return WINDOWS_KEY_TO_LINUX.get(key_code, key_code)


def key_label(key_code: int) -> str:
    """Returns a privacy-minimal, canonical name for profile timing dictionaries."""
    return KEY_NAMES.get(key_code, f"Key_{key_code}")


class NgramAnalyzer:
    """
    Neuromuscular keystroke timing analyzer.
    Extracts key overlap (legato vs staccato), inter-hemispheric hand alternation latency,
    and finger-zone dwell asymmetries instead of naive global averages.
    """

    def __init__(self, history_len: int = 100):
        self.history_len = history_len
        self.active_presses = {}  # key_code -> press_time_us

        # Recent key releases: (key_code, down_us, up_us)
        self.recent_strokes = deque(maxlen=history_len)

        # Transition metrics
        self.last_press_time = None
        self.last_release_time = None
        self.last_key_code = None

        # Statistics accumulators
        self.pp_intervals = deque(maxlen=history_len)       # Press-to-Press
        self.hp_intervals = deque(maxlen=history_len)       # Hold-to-Press (flight)
        self.legato_overlaps = deque(maxlen=history_len)    # Negative flight (overlap)
        self.same_hand_latencies = deque(maxlen=history_len)
        self.cross_hand_latencies = deque(maxlen=history_len)

        self.left_dwells = deque(maxlen=history_len)
        self.right_dwells = deque(maxlen=history_len)
        self.space_dwells = deque(maxlen=history_len)
        self.enter_dwells = deque(maxlen=history_len)
        self.backspace_dwells = deque(maxlen=history_len)

        # Global aggregate dwell and flight buffers
        self.all_dwells = deque(maxlen=history_len)
        self.all_flights = deque(maxlen=history_len)
        self.space_count = 0
        self.enter_count = 0

        self.backspace_burst_count = 0
        self.current_backspace_streak = 0

        # High-entropy transition timing profiles. These retain timing summaries,
        # not typed text, and are scoped to a bounded recent-event history.
        self.key_press_history = deque(maxlen=max(history_len, 1000))
        self.digraph_latencies: Dict[str, deque] = defaultdict(lambda: deque(maxlen=history_len))
        self.trigraph_latencies: Dict[str, deque] = defaultdict(lambda: deque(maxlen=history_len))

    def register_key_down(self, ts_us: int, key_code: int):
        """Processes KEY_DOWN event."""
        # Ignore OS auto-repeat downs until the matching release arrives.
        if key_code in self.active_presses:
            return
        self.active_presses[key_code] = ts_us

        label = key_label(key_code)
        if self.key_press_history:
            prev_label, prev_ts = self.key_press_history[-1]
            latency_ms = (ts_us - prev_ts) / 1000.0
            if 5.0 < latency_ms < 1000.0:
                self.digraph_latencies[f"{prev_label} → {label}"].append(latency_ms)
        if len(self.key_press_history) >= 2:
            first_label, first_ts = self.key_press_history[-2]
            second_label, _second_ts = self.key_press_history[-1]
            span_ms = (ts_us - first_ts) / 1000.0
            if 10.0 < span_ms < 2000.0:
                self.trigraph_latencies[f"{first_label} → {second_label} → {label}"].append(span_ms)
        self.key_press_history.append((label, ts_us))

        if key_code == SPECIAL_SPACE:
            self.space_count += 1
        elif key_code == SPECIAL_ENTER:
            self.enter_count += 1

        # Press-to-Press (PP) interval (capped to 1.5s to exclude idle pauses)
        if self.last_press_time is not None:
            pp = ts_us - self.last_press_time
            if 1000 < pp < 1500000:  # 1ms to 1.5s
                self.pp_intervals.append(pp / 1000.0)

        # Hold-to-Press (flight) and overlap
        if self.last_release_time is not None:
            flight = ts_us - self.last_release_time
            flight_ms = flight / 1000.0
            # If flight < 0, key overlap occurred (legato typing!)
            self.hp_intervals.append(flight_ms)
            self.legato_overlaps.append(1.0 if flight < 0 else 0.0)
            # Only record genuine motor flight transitions (<= 850ms).
            # Pauses > 850ms are cognitive pauses/thinking time, NOT motor flight!
            if 0 < flight_ms <= 850:
                self.all_flights.append(flight_ms)

        # Hand alternation analysis (inter-hemispheric timing)
        if self.last_key_code is not None:
            prev_hand = 1 if self.last_key_code in LEFT_HAND_KEYS else (2 if self.last_key_code in RIGHT_HAND_KEYS else 0)
            curr_hand = 1 if key_code in LEFT_HAND_KEYS else (2 if key_code in RIGHT_HAND_KEYS else 0)

            if prev_hand > 0 and curr_hand > 0:
                interval_ms = (ts_us - (self.last_press_time or ts_us)) / 1000.0
                if 10 < interval_ms < 1500:
                    if prev_hand == curr_hand:
                        self.same_hand_latencies.append(interval_ms)
                    else:
                        self.cross_hand_latencies.append(interval_ms)

        # Backspace correction tracking
        if key_code == SPECIAL_BACKSPACE:
            self.current_backspace_streak += 1
        else:
            if self.current_backspace_streak > 0:
                self.backspace_burst_count += 1
                self.current_backspace_streak = 0

        self.last_press_time = ts_us
        self.last_key_code = key_code

    def register_key_up(self, ts_us: int, key_code: int) -> Optional[float]:
        """Processes KEY_UP event. Returns dwell time in ms if available."""
        self.last_release_time = ts_us

        down_us = self.active_presses.pop(key_code, None)
        if down_us is None:
            return None

        dwell_us = ts_us - down_us
        dwell_ms = dwell_us / 1000.0
        if not (5 < dwell_ms < 2000):
            return None

        self.recent_strokes.append((key_code, down_us, ts_us))
        self.all_dwells.append(dwell_ms)

        # Classify by hand/zone
        if key_code in LEFT_HAND_KEYS:
            self.left_dwells.append(dwell_ms)
        elif key_code in RIGHT_HAND_KEYS:
            self.right_dwells.append(dwell_ms)

        if key_code == SPECIAL_SPACE:
            self.space_dwells.append(dwell_ms)
        elif key_code == SPECIAL_ENTER:
            self.enter_dwells.append(dwell_ms)
        elif key_code == SPECIAL_BACKSPACE:
            self.backspace_dwells.append(dwell_ms)

        return dwell_ms

    @staticmethod
    def _summarize_profile(values: deque) -> Dict[str, float]:
        array = np.asarray(values, dtype=float)
        return {
            "count": int(array.size),
            "mean_ms": float(np.mean(array)),
            "std_ms": float(np.std(array)),
        }

    def extract_timing_profile(self, min_count: int = 2) -> Dict[str, Dict[str, Dict[str, float]]]:
        """Returns high-frequency digraph/trigraph timing summaries for matching."""
        def summaries(source: Dict[str, deque]) -> Dict[str, Dict[str, float]]:
            ranked = sorted(source.items(), key=lambda item: len(item[1]), reverse=True)
            return {
                key: self._summarize_profile(values)
                for key, values in ranked
                if len(values) >= min_count
            }

        return {
            "digraphs": summaries(self.digraph_latencies),
            "trigraphs": summaries(self.trigraph_latencies),
        }

    def recent_typing_speed(self, sample_count: int = 12) -> float:
        """Returns measured key-down rate from the latest physical key presses during active typing bursts."""
        if len(self.key_press_history) < 2:
            return float("nan")
        recent = list(self.key_press_history)[-sample_count:]
        # Calculate speed over adjacent keystrokes, excluding long idle pauses (> 2.0s)
        intervals_s = []
        for i in range(1, len(recent)):
            dt = (recent[i][1] - recent[i - 1][1]) / 1_000_000.0
            if 0.01 <= dt <= 2.0:
                intervals_s.append(dt)
        if not intervals_s:
            return float("nan")
        avg_interval = sum(intervals_s) / len(intervals_s)
        return float(1.0 / avg_interval) if avg_interval > 0 else float("nan")

    def recent_dwell_std_ms(self, sample_count: int = 12) -> float:
        if len(self.all_dwells) < 2:
            return float("nan")
        return float(np.std(np.asarray(list(self.all_dwells)[-sample_count:], dtype=float)))

    def extract_neuromuscular_features(self) -> Dict[str, float]:
        """Extracts rich neuromuscular timing metrics."""
        global_dwell = float(np.mean(self.all_dwells)) if self.all_dwells else np.nan
        left_mean = float(np.mean(self.left_dwells)) if self.left_dwells else global_dwell
        right_mean = float(np.mean(self.right_dwells)) if self.right_dwells else global_dwell

        # Asymmetry ratio (motor dominance)
        hand_asymmetry = (left_mean - right_mean) / max(left_mean + right_mean, 1e-4)

        pp_mean = float(np.mean(self.pp_intervals)) if self.pp_intervals else np.nan
        pp_std = float(np.std(self.pp_intervals)) if self.pp_intervals else np.nan
        global_flight = float(np.mean(self.all_flights)) if self.all_flights else np.nan

        same_mean = float(np.mean(self.same_hand_latencies)) if self.same_hand_latencies else np.nan
        cross_mean = float(np.mean(self.cross_hand_latencies)) if self.cross_hand_latencies else np.nan

        # Cross-hand coordination ratio
        cross_ratio = cross_mean / max(same_mean, 1e-4) if np.isfinite(same_mean + cross_mean) else np.nan

        # Legato ratio (fraction of overlapping key strokes)
        legato_ratio = float(np.mean(self.legato_overlaps)) if self.legato_overlaps else np.nan

        return {
            "dwell_mean_ms": global_dwell,
            "flight_mean_ms": global_flight,
            "dwell_left_hand_ms": left_mean,
            "dwell_right_hand_ms": right_mean,
            "dwell_hand_asymmetry": hand_asymmetry,
            "cross_hand_ratio": cross_ratio,
            "legato_overlap_ratio": legato_ratio,
            "press_to_press_mean_ms": pp_mean,
            "press_to_press_std_ms": pp_std,
            "space_dwell_ms": float(np.mean(self.space_dwells)) if self.space_dwells else np.nan,
            "enter_dwell_ms": float(np.mean(self.enter_dwells)) if self.enter_dwells else np.nan,
            "backspace_dwell_ms": float(np.mean(self.backspace_dwells)) if self.backspace_dwells else np.nan,
            "backspace_burst_rate": float(self.backspace_burst_count),
            "space_frequency": self.space_count / len(self.all_dwells) if self.all_dwells else np.nan,
            "enter_frequency": self.enter_count / len(self.all_dwells) if self.all_dwells else np.nan,
        }
