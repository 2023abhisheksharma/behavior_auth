import numpy as np
from collections import deque
from typing import Tuple, Dict, Any, List

class AntiBotDetector:
    """
    Detects synthetic, robotic, and hardware injection attacks:
    - USB Rubber Ducky / Flipper Zero BadUSB
    - Software macro scripts (pyautogui, xdotool, xte)
    - Replay attacks and zero-tremor mouse teleportation
    """

    def __init__(self, buffer_size: int = 25):
        self.buffer_size = buffer_size

        # Keystroke timing buffers
        self.recent_dwells = deque(maxlen=buffer_size)      # ms
        self.recent_flights = deque(maxlen=buffer_size)     # ms
        self.recent_key_timestamps = deque(maxlen=buffer_size)

        # Mouse timing buffers
        self.recent_mouse_tortuosities = deque(maxlen=buffer_size)
        self.recent_mouse_speeds = deque(maxlen=buffer_size)

        self.last_attack_reason = ""
        self.bot_score = 0.0  # 0.0 = natural human, 1.0 = synthetic attack

    def record_key_stroke(self, dwell_ms: float, flight_ms: float, ts_us: int):
        """Records completed key stroke timing for robotic anomaly detection."""
        self.recent_dwells.append(dwell_ms)
        self.recent_flights.append(flight_ms)
        self.recent_key_timestamps.append(ts_us)

    def record_mouse_stroke(self, tortuosity: float, peak_speed: float, dt_sec: float):
        """Records completed mouse stroke for synthetic linearity analysis."""
        self.recent_mouse_tortuosities.append(tortuosity)
        self.recent_mouse_speeds.append(peak_speed)

    def check_attack(self) -> Tuple[bool, str, float]:
        """
        Evaluates recent interaction stream for superhuman or robotic artifacts.

        Returns:
            (is_attack_detected, attack_type, confidence)
        """
        # 1. Zero-Jitter Keystroke Dwell Attack (Rubber Ducky / BadUSB)
        # Humans have neuromuscular dwell variance std >= 12ms.
        # Programmatic injection has std < 2.0ms across 8+ keys.
        if len(self.recent_dwells) >= 8:
            dwell_std = float(np.std(list(self.recent_dwells)[-8:]))
            if dwell_std < 2.5:
                self.last_attack_reason = f"Zero-Jitter Keystroke Injection (std={dwell_std:.2f}ms)"
                self.bot_score = 1.0
                return True, "RUBBER_DUCKY_ZERO_JITTER", 0.99

        # 2. Fixed Delay Quantization (e.g. scripts with constant DELAY 20, DELAY 50)
        if len(self.recent_flights) >= 10:
            flights = list(self.recent_flights)[-10:]
            flight_std = float(np.std(flights))
            if flight_std < 2.5:
                self.last_attack_reason = f"Fixed Programmatic Key Delay (std={flight_std:.2f}ms)"
                self.bot_score = 1.0
                return True, "BADUSB_FIXED_DELAY", 0.98

        # 3. Superhuman Typing Speed Sustained
        if len(self.recent_key_timestamps) >= 12:
            dt_sec = (self.recent_key_timestamps[-1] - self.recent_key_timestamps[-12]) / 1e6
            if 0.01 < dt_sec < 0.40:  # 12 keys in < 400ms = > 30 keys/sec (180+ WPM without pause)
                self.last_attack_reason = f"Superhuman Keystroke Velocity ({12 / dt_sec:.1f} keys/s)"
                self.bot_score = 1.0
                return True, "SUPERHUMAN_KEY_INJECTION", 0.95

        # 4. Perfectly Linear Mouse Trajectory (Automated Bot / Teleport)
        # Humans cannot move a cursor in a mathematically perfect straight line without tremor.
        if len(self.recent_mouse_tortuosities) >= 4:
            recent_t = list(self.recent_mouse_tortuosities)[-4:]
            if all(abs(t - 1.0) < 0.0001 for t in recent_t):
                self.last_attack_reason = "Zero-Tremor Robotic Mouse Trajectory (Tortuosity=1.0000)"
                self.bot_score = 1.0
                return True, "ROBOTIC_MOUSE_INJECTION", 0.92

        self.bot_score = 0.0
        return False, "NONE", 0.0
