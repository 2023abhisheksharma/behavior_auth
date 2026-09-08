"""Local, permission-restricted configuration and runtime-control helpers."""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import secrets
import tempfile
import time
from pathlib import Path
from typing import Any, Dict, Iterable, Optional


DEFAULT_CONFIG_DIR = Path.home() / ".config" / "chronos-auth"


def config_dir() -> Path:
    return Path(os.getenv("CHRONOS_AUTH_CONFIG_DIR", str(DEFAULT_CONFIG_DIR)))


def runtime_dir() -> Path:
    """Returns a secure, user-isolated directory for runtime state and control files."""
    env_dir = os.getenv("CHRONOS_RUNTIME_DIR")
    if env_dir:
        p = Path(env_dir)
    else:
        p = config_dir()
    p.mkdir(parents=True, exist_ok=True)
    if os.name == "posix":
        try:
            os.chmod(p, 0o700)
        except OSError:
            pass
    return p


# Per-user isolated paths
LOCK_MODE_PATH = runtime_dir() / "lock_mode"
CALIBRATION_CONTROL_PATH = runtime_dir() / "calibration_control.json"
CALIBRATION_STATUS_PATH = runtime_dir() / "calibration_status.json"
REMOTE_RELOAD_PATH = runtime_dir() / "remote_reload"
LIVE_STATE_PATH = runtime_dir() / "live_state.json"
RESET_TRIGGER_PATH = runtime_dir() / "reset_trigger"

# Legacy fallback paths in /tmp
LEGACY_LOCK_MODE_PATH = Path("/tmp/chronos_lock_mode")
LEGACY_LIVE_STATE_PATH = Path("/tmp/chronos_live_state.json")
LEGACY_RESET_TRIGGER_PATH = Path("/tmp/chronos_reset_trigger")


def get_lock_mode() -> str:
    """Reads the current lock mode ('simulate' or 'enforce'), checking per-user path first."""
    for path in (LOCK_MODE_PATH, LEGACY_LOCK_MODE_PATH):
        try:
            if path.exists():
                return path.read_text(encoding="utf-8").strip()
        except OSError:
            pass
    return "simulate"


def set_lock_mode(mode: str) -> None:
    """Writes lock mode to runtime_dir and updates legacy /tmp for backward compatibility."""
    normalized = "enforce" if mode.strip().lower() == "enforce" else "simulate"
    try:
        LOCK_MODE_PATH.write_text(normalized, encoding="utf-8")
    except OSError:
        pass
    try:
        LEGACY_LOCK_MODE_PATH.write_text(normalized, encoding="utf-8")
    except OSError:
        pass


def _secure_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if os.name == "posix" and path.parent != Path("/tmp"):
        os.chmod(path.parent, 0o700)


def read_json(path: Path, default: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Loads a JSON object, returning a copy of ``default`` on invalid input."""
    fallback = dict(default or {})
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return fallback
    return data if isinstance(data, dict) else fallback


def secure_write_json(path: Path, payload: Dict[str, Any]) -> None:
    """Atomically writes local secrets/config with owner-only POSIX permissions."""
    _secure_parent(path)
    descriptor, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=str(path.parent))
    temp_path = Path(temp_name)
    try:
        if os.name == "posix":
            os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, sort_keys=True)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_path, path)
        if os.name == "posix":
            os.chmod(path, 0o600)
    finally:
        try:
            temp_path.unlink(missing_ok=True)
        except OSError:
            pass


class SecurityPolicyStore:
    """Stores local monitoring policy, allowlists, and a salted local snooze PIN."""

    DEFAULT_POLICY = {
        "sensitivity": "Balanced",
        "warning_threshold": 50,
        "excluded_apps": [],
        "snooze_until": 0.0,
        "adaptive_baselines": True,
        "pin": {},
    }

    def __init__(self, path: Optional[Path] = None):
        self.path = path or config_dir() / "policy.json"

    def load(self) -> Dict[str, Any]:
        policy = dict(self.DEFAULT_POLICY)
        policy.update(read_json(self.path, self.DEFAULT_POLICY))
        sensitivity = str(policy.get("sensitivity", "Balanced")).title()
        policy["sensitivity"] = sensitivity if sensitivity in {"Strict", "Balanced", "Relaxed"} else "Balanced"
        try:
            policy["warning_threshold"] = int(policy.get("warning_threshold", 50))
        except (TypeError, ValueError):
            policy["warning_threshold"] = 50
        policy["warning_threshold"] = max(10, min(95, policy["warning_threshold"]))
        policy["excluded_apps"] = [str(item).strip().lower() for item in policy.get("excluded_apps", []) if str(item).strip()]
        try:
            policy["snooze_until"] = float(policy.get("snooze_until", 0.0))
        except (TypeError, ValueError):
            policy["snooze_until"] = 0.0
        policy["adaptive_baselines"] = bool(policy.get("adaptive_baselines", True))
        policy["pin"] = policy.get("pin") if isinstance(policy.get("pin"), dict) else {}
        return policy

    def save(self, policy: Dict[str, Any]) -> Dict[str, Any]:
        normalized = dict(self.DEFAULT_POLICY)
        normalized.update(policy)
        secure_write_json(self.path, normalized)
        return self.load()

    def update(self, **changes: Any) -> Dict[str, Any]:
        policy = self.load()
        policy.update(changes)
        return self.save(policy)

    def set_pin(self, pin: str) -> None:
        if len(pin) < 4:
            raise ValueError("Choose a PIN with at least four characters")
        salt = secrets.token_bytes(16)
        iterations = 240_000
        digest = hashlib.pbkdf2_hmac("sha256", pin.encode("utf-8"), salt, iterations)
        self.update(pin={"salt": salt.hex(), "hash": digest.hex(), "iterations": iterations})

    def has_pin(self) -> bool:
        pin = self.load().get("pin", {})
        return bool(pin.get("salt") and pin.get("hash"))

    def verify_pin(self, pin: str) -> bool:
        stored = self.load().get("pin", {})
        try:
            salt = bytes.fromhex(stored["salt"])
            expected = bytes.fromhex(stored["hash"])
            iterations = int(stored.get("iterations", 240_000))
        except (KeyError, TypeError, ValueError):
            return False
        actual = hashlib.pbkdf2_hmac("sha256", pin.encode("utf-8"), salt, iterations)
        return hmac.compare_digest(actual, expected)

    def enable_snooze(self, minutes: int) -> Dict[str, Any]:
        bounded_minutes = max(1, min(int(minutes), 240))
        return self.update(snooze_until=time.time() + bounded_minutes * 60)

    def clear_snooze(self) -> Dict[str, Any]:
        return self.update(snooze_until=0.0)

    @staticmethod
    def is_snoozed(policy: Dict[str, Any]) -> bool:
        return float(policy.get("snooze_until", 0.0)) > time.time()

    @staticmethod
    def is_excluded_app(policy: Dict[str, Any], app_name: str) -> bool:
        app = app_name.lower()
        return any(pattern in app for pattern in policy.get("excluded_apps", []))


class CredentialsStore:
    """Stores Telegram and SMTP credentials in a local 0600 file."""

    DEFAULT_CREDENTIALS = {"telegram": {}, "smtp": {}}

    def __init__(self, path: Optional[Path] = None):
        self.path = path or config_dir() / "credentials.json"

    def load(self) -> Dict[str, Any]:
        credentials = dict(self.DEFAULT_CREDENTIALS)
        credentials.update(read_json(self.path, self.DEFAULT_CREDENTIALS))
        credentials["telegram"] = credentials.get("telegram") if isinstance(credentials.get("telegram"), dict) else {}
        credentials["smtp"] = credentials.get("smtp") if isinstance(credentials.get("smtp"), dict) else {}
        return credentials

    def save(self, credentials: Dict[str, Any]) -> Dict[str, Any]:
        payload = dict(self.DEFAULT_CREDENTIALS)
        payload.update(credentials)
        secure_write_json(self.path, payload)
        request_remote_reload()
        return self.load()

    def update_telegram(self, token: str, chat_id: str, enabled: bool = True) -> Dict[str, Any]:
        credentials = self.load()
        credentials["telegram"] = {
            "token": token.strip(),
            "chat_id": str(chat_id).strip(),
            "enabled": bool(enabled),
        }
        return self.save(credentials)

    def update_smtp(self, **smtp: Any) -> Dict[str, Any]:
        credentials = self.load()
        credentials["smtp"] = {key: value for key, value in smtp.items() if value not in (None, "")}
        return self.save(credentials)


def request_remote_reload() -> None:
    try:
        REMOTE_RELOAD_PATH.write_text(str(time.time()), encoding="utf-8")
    except OSError:
        pass


def write_calibration_control(command: str, **payload: Any) -> None:
    data = {"command": command, "requested_at": time.time()}
    data.update(payload)
    secure_write_json(CALIBRATION_CONTROL_PATH, data)
