"""Explicit local operating-system actions used by authorized security controls."""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Optional, Tuple


def lock_workstation() -> Tuple[bool, str]:
    """Locks the current desktop session without relying on remote shell commands."""
    if os.name == "nt":
        try:
            result = subprocess.run(
                ["rundll32.exe", "user32.dll,LockWorkStation"],
                timeout=3.0,
                capture_output=True,
            )
            return result.returncode == 0, "Windows LockWorkStation requested"
        except OSError as exc:
            return False, f"Windows lock failed: {exc}"

    for command in (
        ["loginctl", "lock-session"],
        ["xdg-screensaver", "lock"],
        ["gnome-screensaver-command", "-l"],
    ):
        if not shutil.which(command[0]):
            continue
        try:
            result = subprocess.run(command, timeout=3.0, capture_output=True)
            if result.returncode == 0:
                return True, f"Lock requested through {command[0]}"
        except OSError:
            continue
    return False, "No supported desktop lock command succeeded"


def capture_webcam_snapshot() -> Tuple[Optional[Path], str]:
    """Captures one local frame only after an authorized remote snapshot request."""
    descriptor, temp_name = tempfile.mkstemp(prefix="chronos-snapshot-", suffix=".jpg")
    os.close(descriptor)
    output = Path(temp_name)
    try:
        try:
            import cv2  # Optional dependency; avoids enabling a camera by default.

            camera = cv2.VideoCapture(0)
            try:
                ok, frame = camera.read()
                if ok and cv2.imwrite(str(output), frame):
                    return output, "Webcam snapshot captured"
            finally:
                camera.release()
        except (ImportError, OSError):
            pass

        if shutil.which("fswebcam"):
            result = subprocess.run(
                ["fswebcam", "--no-banner", str(output)],
                timeout=12.0,
                capture_output=True,
            )
            if result.returncode == 0 and output.exists() and output.stat().st_size > 0:
                return output, "Webcam snapshot captured"
        output.unlink(missing_ok=True)
        return None, "No supported webcam capture backend is available"
    except OSError as exc:
        output.unlink(missing_ok=True)
        return None, f"Webcam snapshot failed: {exc}"

