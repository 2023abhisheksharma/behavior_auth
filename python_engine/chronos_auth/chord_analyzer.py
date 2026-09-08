import json
import numpy as np
from collections import deque
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any

# Universal Linux evdev + Windows Virtual-Key modifier mappings
MODIFIER_KEYS = {
    # Linux evdev scancodes
    29: "Ctrl",
    97: "Ctrl",
    42: "Shift",
    54: "Shift",
    56: "Alt",
    100: "Alt",
    125: "Super",
    126: "Super",
    # Windows Virtual-Key codes
    17: "Ctrl",
    16: "Shift",
    18: "Alt",
    91: "Super",
    92: "Super",
}

LEFT_MODIFIERS = {29, 42, 56, 125, 17, 16, 18, 91}
RIGHT_MODIFIERS = {97, 54, 100, 126, 92}

# Comprehensive scancode dictionary for Linux evdev + Windows VKey
SCANCODE_NAMES = {
    # Special & Control Keys (Linux evdev)
    1: "Esc", 14: "Backspace", 15: "Tab", 28: "Enter", 57: "Space", 58: "Caps",
    29: "Ctrl", 97: "Ctrl (R)", 42: "Shift", 54: "Shift (R)", 56: "Alt", 100: "Alt (R)",
    125: "Super", 126: "Super (R)",
    102: "Home", 103: "Up", 104: "PageUp", 105: "Left", 106: "Right", 107: "End", 108: "Down", 109: "PageDown",
    110: "Insert", 111: "Delete",

    # Windows VKey special overrides
    9: "Tab", 13: "Enter", 27: "Esc", 32: "Space", 20: "Caps",
    8: "Backspace", 46: "Delete", 45: "Insert", 36: "Home", 35: "End",
    33: "PageUp", 34: "PageDown", 37: "Left", 38: "Up", 39: "Right", 40: "Down",

    # Numbers
    2: "1", 3: "2", 4: "3", 5: "4", 6: "5", 7: "6", 8: "7", 9: "8", 10: "9", 11: "0",
    12: "-", 13: "=",

    # Standard QWERTY Letters (Linux evdev)
    16: "Q", 17: "W", 18: "E", 19: "R", 20: "T", 21: "Y", 22: "U", 23: "I", 24: "O", 25: "P",
    26: "[", 27: "]",
    30: "A", 31: "S", 32: "D", 33: "F", 34: "G", 35: "H", 36: "J", 37: "K", 38: "L", 39: ";", 40: "'",
    44: "Z", 45: "X", 46: "C", 47: "V", 48: "B", 49: "N", 50: "M", 51: ",", 52: ".", 53: "/",

    # Windows Virtual-Key letters (0x41 to 0x5A)
    65: "A", 66: "B", 67: "C", 68: "D", 69: "E", 70: "F", 71: "G", 72: "H", 73: "I", 74: "J",
    75: "K", 76: "L", 77: "M", 78: "N", 79: "O", 80: "P", 81: "Q", 82: "R", 83: "S", 84: "T",
    85: "U", 86: "V", 87: "W", 88: "X", 89: "Y", 90: "Z",

    # Function Keys
    59: "F1", 60: "F2", 61: "F3", 62: "F4", 63: "F5", 64: "F6",
    65: "F7", 66: "F8", 67: "F9", 68: "F10", 87: "F11", 88: "F12",
    112: "F1", 113: "F2", 114: "F3", 115: "F4", 116: "F5", 117: "F6",
    118: "F7", 119: "F8", 120: "F9", 121: "F10", 122: "F11", 123: "F12",
}


class ChordAnalyzer:
    """
    Open-Vocabulary Shortcut Dynamics Engine.
    Dynamically learns whatever personal shortcuts and key commands ANY user presses
    (e.g., Ctrl+C, Alt+Tab, custom IDE hotkeys, Blender/Photoshop/Vim key commands),
    profiling their individual muscle memory interval timing and evaluating trust impact.
    """

    def __init__(self, history_len: int = 100, storage_path: Optional[str] = None):
        self.history_len = history_len
        self.storage_path = Path(storage_path or (Path(__file__).parent.parent / "shortcuts_profile.json"))

        # Active held modifiers: key_code -> press_time_us
        self.active_modifiers: Dict[int, int] = {}

        # General aggregate history
        self.chord_lead_times = deque(maxlen=history_len)       # ms
        self.chord_overlap_times = deque(maxlen=history_len)    # ms
        self.left_modifier_count = 0
        self.right_modifier_count = 0

        # Pending key chords: (char_code) -> (mod_combo_str, mod_ts, char_ts)
        self.pending_chords: Dict[int, Tuple[str, int, int]] = {}

        # Dynamic Shortcut Dictionary: "Ctrl+C" -> {"count": N, "mean_lead_ms": M, ...}
        self.custom_shortcuts: Dict[str, Dict[str, Any]] = {}
        if self.storage_path.exists():
            self._load_persisted_profile()

    def _load_persisted_profile(self):
        """Loads learned shortcut memory from disk without fake mock counts."""
        if self.storage_path.exists():
            try:
                with open(self.storage_path, "r") as f:
                    data = json.load(f)
                for name, info in data.items():
                    count = info.get("count", 0)
                    mean_lead = info.get("mean_lead_ms", 65.0)
                    std_lead = info.get("std_lead_ms", 12.0)
                    self.custom_shortcuts[name] = {
                        "count": count,
                        "mean_lead_ms": float(mean_lead),
                        "std_lead_ms": float(std_lead),
                        "last_seen": info.get("last_seen", 0.0),
                        "lead_times": deque([mean_lead] * min(count, 10), maxlen=30),
                    }
            except Exception:
                pass

    def save_profile(self):
        """Persists learned shortcuts to disk."""
        try:
            dump_data = {}
            for name, info in self.custom_shortcuts.items():
                dump_data[name] = {
                    "count": info["count"],
                    "mean_lead_ms": info["mean_lead_ms"],
                    "std_lead_ms": info["std_lead_ms"],
                    "last_seen": info["last_seen"],
                }
            with open(self.storage_path, "w") as f:
                json.dump(dump_data, f, indent=2)
        except Exception:
            pass

    def register_key_down(self, ts_us: int, key_code: int):
        """Processes key down for modifiers and chorded characters."""
        if key_code in MODIFIER_KEYS:
            self.active_modifiers[key_code] = ts_us
            if key_code in LEFT_MODIFIERS:
                self.left_modifier_count += 1
            elif key_code in RIGHT_MODIFIERS:
                self.right_modifier_count += 1
        else:
            if self.active_modifiers:
                # Build compound modifier name, e.g. "Ctrl", "Ctrl+Shift"
                mod_names = sorted(list({MODIFIER_KEYS[k] for k in self.active_modifiers.keys()}))
                mod_combo = "+".join(mod_names)

                char_name = SCANCODE_NAMES.get(key_code, f"Key_{key_code}")
                full_shortcut_name = f"{mod_combo}+{char_name}"

                # Measure lead time from earliest held modifier
                first_mod_ts = min(self.active_modifiers.values())
                lead_ms = (ts_us - first_mod_ts) / 1000.0

                if 10 < lead_ms < 2500:
                    self.chord_lead_times.append(lead_ms)
                    self.pending_chords[key_code] = (full_shortcut_name, first_mod_ts, ts_us)

                    # Update dynamic personal vocabulary
                    if full_shortcut_name not in self.custom_shortcuts:
                        self.custom_shortcuts[full_shortcut_name] = {
                            "count": 0,
                            "lead_times": deque(maxlen=30),
                            "mean_lead_ms": lead_ms,
                            "std_lead_ms": 20.0,
                            "last_seen": ts_us / 1e6,
                        }

                    entry = self.custom_shortcuts[full_shortcut_name]
                    entry["count"] += 1
                    entry["lead_times"].append(lead_ms)
                    entry["mean_lead_ms"] = float(np.mean(entry["lead_times"]))
                    entry["std_lead_ms"] = float(np.std(entry["lead_times"])) if len(entry["lead_times"]) > 1 else 15.0
                    entry["last_seen"] = ts_us / 1e6

                    self.save_profile()

    def register_key_up(self, ts_us: int, key_code: int):
        """Processes key release for modifier or chorded character."""
        if key_code in MODIFIER_KEYS:
            self.active_modifiers.pop(key_code, None)

        if key_code in self.pending_chords:
            shortcut_name, mod_ts, char_ts = self.pending_chords.pop(key_code)
            overlap_ms = (ts_us - char_ts) / 1000.0
            if 10 < overlap_ms < 2500:
                self.chord_overlap_times.append(overlap_ms)

    def extract_chord_features(self) -> Dict[str, float]:
        """Returns statistical metrics for keyboard chording habits."""
        lead_mean = float(np.mean(self.chord_lead_times)) if self.chord_lead_times else float("nan")
        lead_std = float(np.std(self.chord_lead_times)) if self.chord_lead_times else float("nan")
        overlap_mean = float(np.mean(self.chord_overlap_times)) if self.chord_overlap_times else float("nan")

        total_mods = self.left_modifier_count + self.right_modifier_count
        left_ratio = float(self.left_modifier_count / total_mods) if total_mods > 0 else float("nan")

        return {
            "chord_lead_mean_ms": lead_mean,
            "chord_lead_std_ms": lead_std,
            "chord_overlap_mean_ms": overlap_mean,
            "left_modifier_ratio": left_ratio,
            "chords_detected": float(len(self.chord_lead_times)),
            "distinct_shortcuts_known": float(len(self.custom_shortcuts)),
            "shortcut_delta_llr": 0.0,
        }


    def get_top_shortcuts(self, top_n: int = 10) -> List[Dict[str, Any]]:
        """Returns the user's top personal shortcuts with muscle-memory lead time stats."""
        return self.get_all_stored_shortcuts()[:top_n]

    def get_all_stored_shortcuts(self) -> List[Dict[str, Any]]:
        """Returns all dynamically registered and persisted shortcuts."""
        sorted_shortcuts = sorted(
            self.custom_shortcuts.items(),
            key=lambda item: item[1]["count"],
            reverse=True,
        )
        results = []
        for name, info in sorted_shortcuts:
            mean = round(info["mean_lead_ms"], 1)
            std = round(info["std_lead_ms"], 1)
            consistency = "High (Reflexive)" if std < 8 else ("Normal (Muscle)" if std < 16 else "Variable")
            results.append({
                "shortcut": name,
                "count": info["count"],
                "mean_lead_ms": mean,
                "std_lead_ms": std,
                "consistency": consistency,
                "last_seen": info.get("last_seen", 0.0),
            })
        return results

    def record_custom_shortcut(self, name: str, lead_ms: float):
        """Allows recording or testing a shortcut directly."""
        import time
        if name in self.custom_shortcuts:
            entry = self.custom_shortcuts[name]
            entry["count"] += 1
            entry["lead_times"].append(lead_ms)
            entry["mean_lead_ms"] = float(np.mean(entry["lead_times"]))
            entry["std_lead_ms"] = float(np.std(entry["lead_times"])) if len(entry["lead_times"]) > 1 else 5.0
            entry["last_seen"] = time.time()
        else:
            self.custom_shortcuts[name] = {
                "count": 1,
                "mean_lead_ms": float(lead_ms),
                "std_lead_ms": 5.0,
                "last_seen": time.time(),
                "lead_times": deque([lead_ms], maxlen=30),
            }
        self.save_profile()
