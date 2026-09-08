"""
Chronos-Auth System Tray Manager & Visual Asset Generator
Provides cross-platform background system tray presence, dynamic status
shield icon rendering (safe, warning, threat/lockout, snoozed), desktop
menu actions, and asset generation.
"""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Callable, Dict, Optional, Tuple

try:
    from PIL import Image, ImageDraw
    HAS_PIL = True
except ImportError:
    HAS_PIL = False

try:
    import pystray
    from pystray import Menu, MenuItem as item
    HAS_PYSTRAY = True
except ImportError:
    HAS_PYSTRAY = False

logger = logging.getLogger("chronos.tray")


# =============================================================================
# DYNAMIC SHIELD ICON RENDERING (PIL)
# =============================================================================

def render_shield_icon(status: str = "safe", size: int = 64) -> Optional["Image.Image"]:
    """
    Renders a crisp, anti-aliased security shield icon reflecting system security state:
    - 'safe' / 'active': Emerald Green (#10B981) with Checkmark emblem.
    - 'warning': Amber Orange (#F59E0B) with Exclamation emblem.
    - 'lockout' / 'threat': Crimson Red (#EF4444) with Padlock emblem.
    - 'snoozed' / 'paused': Slate Gray (#64748B) with Pause emblem.
    
    Rendered at 4x internal resolution and downscaled with LANCZOS resampling
    for smooth vector-like antialiased curves.
    """
    if not HAS_PIL:
        return None

    # Palette definitions: (main_color, dark_hemisphere, emblem_color)
    palette: Dict[str, Tuple[Tuple[int, int, int], Tuple[int, int, int], Tuple[int, int, int]]] = {
        "safe": ((16, 185, 129), (5, 150, 105), (6, 95, 70)),
        "active": ((16, 185, 129), (5, 150, 105), (6, 95, 70)),
        "warning": ((245, 158, 11), (217, 119, 6), (146, 64, 14)),
        "lockout": ((239, 68, 68), (220, 38, 38), (153, 27, 27)),
        "threat": ((239, 68, 68), (220, 38, 38), (153, 27, 27)),
        "snoozed": ((148, 163, 184), (100, 116, 139), (51, 65, 85)),
        "paused": ((148, 163, 184), (100, 116, 139), (51, 65, 85)),
    }

    status_key = status.lower()
    col_main, col_dark, col_emblem = palette.get(status_key, palette["safe"])

    # Render at 4x resolution for anti-aliasing
    scale = 4
    canvas_size = size * scale
    s = float(canvas_size)

    img = Image.new("RGBA", (canvas_size, canvas_size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # 1. Subtle Outer Glow / Shadow
    shadow_poly = [
        (s * 0.50, s * 0.10),
        (s * 0.86, s * 0.20),
        (s * 0.86, s * 0.57),
        (s * 0.50, s * 0.94),
        (s * 0.14, s * 0.57),
        (s * 0.14, s * 0.20),
    ]
    draw.polygon(shadow_poly, fill=(0, 0, 0, 35))

    # 2. Left Hemisphere (Light Accent)
    poly_left = [
        (s * 0.50, s * 0.08),
        (s * 0.15, s * 0.18),
        (s * 0.15, s * 0.55),
        (s * 0.50, s * 0.92),
    ]
    draw.polygon(poly_left, fill=col_main)

    # 3. Right Hemisphere (Shaded Depth)
    poly_right = [
        (s * 0.50, s * 0.08),
        (s * 0.85, s * 0.18),
        (s * 0.85, s * 0.55),
        (s * 0.50, s * 0.92),
    ]
    draw.polygon(poly_right, fill=col_dark)

    # 4. Metallic Shield Outer Stroke
    poly_full = [
        (s * 0.50, s * 0.08),
        (s * 0.85, s * 0.18),
        (s * 0.85, s * 0.55),
        (s * 0.50, s * 0.92),
        (s * 0.15, s * 0.55),
        (s * 0.15, s * 0.18),
    ]
    stroke_w = max(2, int(s * 0.03))
    draw.polygon(poly_full, outline=(255, 255, 255, 230), width=stroke_w)

    # 5. Circular Center Hub
    cx, cy = s * 0.50, s * 0.48
    r = s * 0.22
    draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=(255, 255, 255, 245), outline=(255, 255, 255, 255), width=max(1, int(s * 0.015)))

    # 6. Status Emblem Inside Hub
    lw = max(3, int(s * 0.045))
    if status_key in ("safe", "active"):
        # Checkmark
        pts = [
            (cx - r * 0.45, cy - r * 0.05),
            (cx - r * 0.10, cy + r * 0.35),
            (cx + r * 0.50, cy - r * 0.35),
        ]
        draw.line(pts, fill=col_emblem, width=lw, joint="curve")
    elif status_key == "warning":
        # Exclamation Mark
        draw.line([(cx, cy - r * 0.50), (cx, cy + r * 0.10)], fill=col_emblem, width=lw)
        dot_r = max(2.5, s * 0.024)
        draw.ellipse([cx - dot_r, cy + r * 0.40 - dot_r, cx + dot_r, cy + r * 0.40 + dot_r], fill=col_emblem)
    elif status_key in ("lockout", "threat"):
        # Padlock
        shackle_w = max(2, int(s * 0.035))
        draw.rectangle([cx - r * 0.40, cy - r * 0.08, cx + r * 0.40, cy + r * 0.50], fill=col_emblem)
        draw.arc([cx - r * 0.26, cy - r * 0.52, cx + r * 0.26, cy + r * 0.05], start=180, end=0, fill=col_emblem, width=shackle_w)
    else:
        # Snoozed: Dual Pause Bars
        pw = max(3, int(r * 0.22))
        draw.rectangle([cx - r * 0.36 - pw // 2, cy - r * 0.42, cx - r * 0.36 + pw // 2, cy + r * 0.42], fill=col_emblem)
        draw.rectangle([cx + r * 0.36 - pw // 2, cy - r * 0.42, cx + r * 0.36 + pw // 2, cy + r * 0.42], fill=col_emblem)

    # Downsample cleanly to destination size
    return img.resize((size, size), Image.Resampling.LANCZOS)


# =============================================================================
# DESKTOP ASSETS EXPORT (PNG & SVG)
# =============================================================================

def generate_and_save_assets(target_dir: Path) -> Dict[str, Path]:
    """
    Generates high-resolution application icons and SVG vectors into target_dir.
    Returns dictionary of generated file paths.
    """
    target_dir.mkdir(parents=True, exist_ok=True)
    generated = {}

    if HAS_PIL:
        for sz in [256, 128, 64, 32]:
            icon_img = render_shield_icon(status="safe", size=sz)
            if icon_img:
                filename = f"chronos-auth-{sz}.png" if sz != 256 else "chronos-auth.png"
                out_path = target_dir / filename
                icon_img.save(out_path, format="PNG")
                generated[f"png_{sz}"] = out_path

        # Generate status variants at 64px for tray/UI states
        for st in ["safe", "warning", "lockout", "snoozed"]:
            st_img = render_shield_icon(status=st, size=64)
            if st_img:
                st_path = target_dir / f"chronos-shield-{st}.png"
                st_img.save(st_path, format="PNG")
                generated[f"shield_{st}"] = st_path

    # Export crisp Scalable Vector Graphics (SVG)
    svg_content = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 128 128" width="128" height="128">
  <defs>
    <filter id="drop-shadow" x="-10%" y="-10%" width="130%" height="130%">
      <feDropShadow dx="0" dy="4" stdDeviation="4" flood-color="#000" flood-opacity="0.3"/>
    </filter>
    <linearGradient id="shieldLeft" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0%" stop-color="#34D399"/>
      <stop offset="100%" stop-color="#10B981"/>
    </linearGradient>
    <linearGradient id="shieldRight" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0%" stop-color="#10B981"/>
      <stop offset="100%" stop-color="#059669"/>
    </linearGradient>
  </defs>
  <g filter="url(#drop-shadow)">
    <!-- Left Hemisphere -->
    <path d="M 64,10 L 19,23 L 19,70 Q 64,117 64,117 Z" fill="url(#shieldLeft)"/>
    <!-- Right Hemisphere -->
    <path d="M 64,10 L 109,23 L 109,70 Q 64,117 64,117 Z" fill="url(#shieldRight)"/>
    <!-- Outer Rim -->
    <path d="M 64,10 L 109,23 L 109,70 Q 64,117 64,117 Q 19,70 19,70 L 19,23 Z" fill="none" stroke="#FFFFFF" stroke-width="3.5" stroke-linejoin="round" opacity="0.9"/>
    <!-- Center Emblem Hub -->
    <circle cx="64" cy="61" r="28" fill="#FFFFFF" opacity="0.96"/>
    <!-- Checkmark Motif -->
    <path d="M 52,60 L 61,70 L 78,50" fill="none" stroke="#047857" stroke-width="5" stroke-linecap="round" stroke-linejoin="round"/>
  </g>
</svg>
"""
    svg_path = target_dir / "chronos-auth.svg"
    svg_path.write_text(svg_content, encoding="utf-8")
    generated["svg"] = svg_path

    return generated


# =============================================================================
# SYSTEM TRAY MANAGER CLASS
# =============================================================================

class ChronosTrayManager:
    """
    Manages the desktop system tray icon, reactive color-changing status shields,
    system menu commands, and notifications.
    """

    def __init__(
        self,
        on_show: Callable[[], None],
        on_toggle_snooze: Callable[[], None],
        on_lock: Callable[[], None],
        on_quit: Callable[[], None],
        get_status: Optional[Callable[[], Dict[str, any]]] = None,
    ):
        self.on_show = on_show
        self.on_toggle_snooze = on_toggle_snooze
        self.on_lock = on_lock
        self.on_quit = on_quit
        self.get_status = get_status or (lambda: {"trust": 100.0, "status": "safe", "snoozed": False})

        self.icon: Optional["pystray.Icon"] = None
        self.is_active = False
        self._thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()
        self._current_status = "safe"
        self._current_trust = 100.0
        self._is_snoozed = False

        # Pre-cache rendered icons for instant swap
        self._cached_icons: Dict[str, "Image.Image"] = {}
        if HAS_PIL:
            for st in ["safe", "warning", "lockout", "snoozed"]:
                rendered = render_shield_icon(status=st, size=64)
                if rendered:
                    self._cached_icons[st] = rendered

    def _is_dock_available(self) -> bool:
        """Checks whether the running X11/desktop session supports system tray docking."""
        if not HAS_PYSTRAY or not HAS_PIL:
            return False
        try:
            # Under Linux Xorg, test whether a system tray window manager atom is registered
            dummy = pystray.Icon("test_probe", Image.new("RGBA", (1, 1)))
            if hasattr(dummy, "_get_systray_manager"):
                mgr = dummy._get_systray_manager()
                return mgr is not None
            return True
        except Exception:
            return False

    def _build_menu(self) -> "pystray.Menu":
        """Constructs the system tray context menu."""
        trust_str = f"Trust: {self._current_trust:.0f}%"
        state_label = "Snoozed" if self._is_snoozed else ("Warning" if self._current_status == "warning" else ("Lockout" if self._current_status in ("lockout", "threat") else "Protected"))
        status_text = f"● Status: {state_label} ({trust_str})"

        snooze_label = "▶️ Resume Continuous Protection" if self._is_snoozed else "⏸️ Snooze Protection (30m)"

        return Menu(
            item("🛡️ Show Chronos Dashboard", lambda _: self.on_show(), default=True),
            item(status_text, lambda _: None, enabled=False),
            Menu.SEPARATOR,
            item(snooze_label, lambda _: self.on_toggle_snooze()),
            item("🔒 Lock Workstation Now", lambda _: self.on_lock()),
            Menu.SEPARATOR,
            item("❌ Quit Chronos-Auth", lambda _: self.on_quit()),
        )

    def start(self):
        """Launches the system tray icon in a dedicated daemon thread."""
        if not HAS_PYSTRAY or not HAS_PIL:
            logger.info("Pystray or Pillow not available; running in direct window mode.")
            self.is_active = False
            return

        if not self._is_dock_available():
            logger.info("No system tray manager detected on current display; tray icon disabled.")
            self.is_active = False
            return

        try:
            initial_img = self._cached_icons.get("safe") or render_shield_icon("safe", 64)
            if not initial_img:
                self.is_active = False
                return

            self.icon = pystray.Icon(
                "chronos_auth",
                initial_img,
                "Chronos-Auth Continuous Security",
                menu=self._build_menu(),
            )

            def _run_tray():
                try:
                    self.is_active = True
                    self.icon.run()
                except Exception as e:
                    logger.warning(f"System tray exited or failed to run: {e}")
                finally:
                    self.is_active = False

            self._thread = threading.Thread(target=_run_tray, daemon=True)
            self._thread.start()
            logger.info("System tray icon started successfully.")
        except Exception as e:
            logger.warning(f"Could not initialize system tray: {e}")
            self.is_active = False

    def update_status(self, trust_score: float, status_label: str, is_snoozed: bool):
        """
        Dynamically updates the tray icon image, hover title, and menu text.
        Called on every biometric scoring pulse.
        """
        with self._lock:
            self._current_trust = trust_score
            self._is_snoozed = is_snoozed

            if is_snoozed:
                target_state = "snoozed"
            elif status_label.lower() in ("threat", "lockout", "critical"):
                target_state = "lockout"
            elif status_label.lower() in ("warning", "suspect"):
                target_state = "warning"
            else:
                target_state = "safe"

            state_changed = (target_state != self._current_status)
            self._current_status = target_state

        if not self.icon or not self.is_active:
            return

        try:
            # Update icon image if state changed
            if state_changed:
                new_img = self._cached_icons.get(target_state) or render_shield_icon(target_state, 64)
                if new_img:
                    self.icon.icon = new_img

            # Update tooltip title
            s_text = "Snoozed" if is_snoozed else ("Protected" if target_state == "safe" else target_state.upper())
            self.icon.title = f"Chronos-Auth: {s_text} ({trust_score:.0f}%)"

            # Rebuild dynamic context menu
            self.icon.menu = self._build_menu()
        except Exception as e:
            logger.debug(f"Tray update ignored: {e}")

    def notify(self, title: str, message: str):
        """Dispatches a desktop notification via tray balloon or native notify-send."""
        if self.icon and self.is_active:
            try:
                self.icon.notify(message, title)
                return
            except Exception:
                pass

        # Fallback to standard desktop notify-send if available
        if shutil.which("notify-send"):
            try:
                subprocess.Popen(
                    ["notify-send", "-a", "Chronos-Auth", "-u", "normal", title, message],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
            except OSError:
                pass

    def stop(self):
        """Terminates the tray icon cleanly."""
        if self.icon and self.is_active:
            try:
                self.icon.stop()
            except Exception:
                pass
        self.is_active = False
