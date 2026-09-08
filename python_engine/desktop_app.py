"""
Chronos-Auth: Simplified, Modern Continuous Behavioral Authentication Suite.

Features:
- Streamlined 4-tab interface: Dashboard, Devices, Alerts, Settings
- Zero calibration wizard clutter — authenticates directly using trained ML models
- Real-time ML feature attribution with plain-language explainability
- Live telemetry: Dwell time, Flight latency, Typing velocity, Active context
- Bluetooth phone walk-away proximity with real RSSI signal meter
- Telegram & Email intrusion alerts with snapshot support
"""

from __future__ import annotations

import json
import os
import shutil
import sqlite3
import subprocess
import sys
import threading
import time
from collections import deque
from pathlib import Path
from typing import Any, Dict, List, Optional

import tkinter as tk
from tkinter import messagebox, ttk

BASE_DIR = Path(__file__).resolve().parent
ROOT_DIR = BASE_DIR.parent
DB_PATH = BASE_DIR / "behavior_data.db"
sys.path.insert(0, str(BASE_DIR))

from chronos_auth.bluetooth_proximity import BluetoothProximityMonitor
from chronos_auth.feature_attribution import normalize_impacts
from chronos_auth.remote_service import EmailClient, TelegramClient
from chronos_auth.runtime_config import (
    CredentialsStore,
    LEGACY_LIVE_STATE_PATH,
    LEGACY_RESET_TRIGGER_PATH,
    LIVE_STATE_PATH,
    LOCK_MODE_PATH,
    RESET_TRIGGER_PATH,
    SecurityPolicyStore,
    get_lock_mode,
    read_json,
    set_lock_mode,
)
from chronos_auth.system_actions import lock_workstation
from chronos_auth.tray_manager import ChronosTrayManager, render_shield_icon

try:
    from PIL import ImageTk
    HAS_IMAGE_TK = True
except ImportError:
    HAS_IMAGE_TK = False


# =============================================================================
# CLEAN MODERN THEME
# =============================================================================
class CleanTheme:
    BG_APP = "#F8FAFC"             # Slate-50: Crisp, clean light background
    BG_CARD = "#FFFFFF"            # Pure white card surface
    BG_SIDEBAR = "#FFFFFF"         # Pure white sidebar
    BG_PILL_ACTIVE = "#EFF6FF"     # Active tab pill background

    BORDER_CARD = "#E2E8F0"        # Subtle 1px slate-200 border
    BORDER_SUBTLE = "#F1F5F9"

    TEXT_PRIMARY = "#0F172A"       # Deep slate-900 (sharp readability)
    TEXT_SECONDARY = "#475569"     # Slate-600
    TEXT_MUTED = "#94A3B8"         # Slate-400

    ACCENT_BLUE = "#2563EB"        # Vibrant royal blue
    ACCENT_HOVER = "#1D4ED8"
    ACCENT_BG = "#EFF6FF"

    SUCCESS = "#10B981"            # Emerald green
    SUCCESS_BG = "#ECFDF5"
    SUCCESS_BORDER = "#A7F3D0"

    WARNING = "#F59E0B"            # Amber
    WARNING_BG = "#FFFBEB"
    WARNING_BORDER = "#FDE68A"

    DANGER = "#EF4444"             # Rose red
    DANGER_BG = "#FEF2F2"
    DANGER_BORDER = "#FECACA"

    FONT_FAMILY = "Segoe UI" if sys.platform == "win32" else "DejaVu Sans"
    FONT_MONO = "Cascadia Code" if sys.platform == "win32" else "Monospace"


# =============================================================================
# SMOOTH REAL-TIME SPARKLINE
# =============================================================================
class SmoothSparkline(tk.Canvas):
    """High-performance canvas sparkline showing real-time trends."""

    def __init__(
        self, parent, width: int = 240, height: int = 60, min_val: float = 0.0, max_val: float = 100.0,
        line_color: str = CleanTheme.ACCENT_BLUE, fill_color: str = CleanTheme.ACCENT_BG,
        **kwargs: Any
    ):
        super().__init__(
            parent, width=width, height=height, bg=CleanTheme.BG_CARD,
            highlightthickness=0, **kwargs
        )
        self.w = width
        self.h = height
        self.min_val = min_val
        self.max_val = max_val
        self.line_color = line_color
        self.fill_color = fill_color
        self.history = deque([100.0] * 35, maxlen=35)
        self.draw()

    def append_value(self, val: float):
        self.history.append(float(val))
        self.draw()

    def draw(self):
        self.delete("all")
        pad_x = 4
        pad_y = 6
        draw_w = self.w - (pad_x * 2)
        draw_h = self.h - (pad_y * 2)
        v_range = max(self.max_val - self.min_val, 1e-5)

        def to_y(v: float) -> float:
            clamped = max(self.min_val, min(self.max_val, v))
            return (self.h - pad_y) - ((clamped - self.min_val) / v_range * draw_h)

        # Baseline guideline
        y_mid = to_y((self.min_val + self.max_val) * 0.5)
        self.create_line(pad_x, y_mid, self.w - pad_x, y_mid, fill="#F1F5F9", dash=(3, 3))

        pts = []
        n = len(self.history)
        dx = draw_w / max(n - 1, 1)

        for i, val in enumerate(self.history):
            pts.append((pad_x + (i * dx), to_y(val)))

        if len(pts) >= 2:
            poly = [pad_x, self.h - pad_y]
            for x, y in pts:
                poly.extend([x, y])
            poly.extend([pts[-1][0], self.h - pad_y])
            self.create_polygon(poly, fill=self.fill_color, outline="")

            for i in range(len(pts) - 1):
                self.create_line(pts[i][0], pts[i][1], pts[i + 1][0], pts[i + 1][1], fill=self.line_color, width=2)

            lx, ly = pts[-1]
            self.create_oval(lx - 3, ly - 3, lx + 3, ly + 3, fill=self.line_color, outline=CleanTheme.BG_CARD, width=1)


# =============================================================================
# TRUST PROGRESS GAUGE BAR
# =============================================================================
class TrustProgressBar(tk.Canvas):
    """Clean visual horizontal progress bar with colored fill."""

    def __init__(self, parent, width: int = 180, height: int = 10, **kwargs: Any):
        super().__init__(
            parent, width=width, height=height, bg=CleanTheme.BG_CARD,
            highlightthickness=0, **kwargs
        )
        self.w = width
        self.h = height
        self.pct = 100.0
        self.draw()

    def set_pct(self, val: float):
        self.pct = max(0.0, min(100.0, float(val)))
        self.draw()

    def draw(self):
        self.delete("all")
        # Background track
        self.create_rectangle(0, 0, self.w, self.h, fill="#E2E8F0", outline="")

        # Fill bar
        fill_w = (self.pct / 100.0) * self.w
        if fill_w > 0:
            if self.pct >= 80.0:
                color = CleanTheme.SUCCESS
            elif self.pct >= 50.0:
                color = CleanTheme.WARNING
            else:
                color = CleanTheme.DANGER
            self.create_rectangle(0, 0, fill_w, self.h, fill=color, outline="")


# =============================================================================
# SIGNAL STRENGTH METER
# =============================================================================
class SignalBarMeter(tk.Canvas):
    """5-bar visual Bluetooth / proximity strength meter."""

    def __init__(self, parent, width: int = 100, height: int = 24, **kwargs: Any):
        super().__init__(
            parent, width=width, height=height, bg=CleanTheme.BG_CARD,
            highlightthickness=0, **kwargs
        )
        self.w = width
        self.h = height
        self.strength = 0
        self.draw()

    def set_strength(self, level: int):
        self.strength = max(0, min(5, int(level)))
        self.draw()

    def draw(self):
        self.delete("all")
        bars = 5
        bar_w = 8
        spacing = 4
        start_x = (self.w - (bars * bar_w + (bars - 1) * spacing)) // 2

        for i in range(bars):
            x0 = start_x + i * (bar_w + spacing)
            x1 = x0 + bar_w
            bar_h = 5 + (i * 3.5)
            y0 = self.h - bar_h
            y1 = self.h

            if i < self.strength:
                color = CleanTheme.SUCCESS if self.strength >= 3 else CleanTheme.WARNING
            else:
                color = "#E2E8F0"

            self.create_rectangle(x0, y0, x1, y1, fill=color, outline="")


# =============================================================================
# MAIN APPLICATION WINDOW
# =============================================================================
class ChronosAuthApp(tk.Tk):
    """Clean, simplified continuous behavioral authentication desktop dashboard."""

    def __init__(self):
        super().__init__()
        self.title("Chronos-Auth — Continuous Identity Protection")
        self.geometry("1060x720")
        self.minsize(980, 640)
        self.configure(bg=CleanTheme.BG_APP)

        # Core State
        self.is_running_app = True
        self.is_service_running = False
        self.simulate_lock = (get_lock_mode() != "enforce")
        self.policy_store = SecurityPolicyStore()
        self.cred_store = CredentialsStore()
        self.bluetooth_monitor = BluetoothProximityMonitor()

        # Cached Telemetry
        self.last_trust = 100.0
        self.last_action = "CONTINUE"

        # System Tray Support
        self.tray_manager = ChronosTrayManager(
            on_show=self.show_window_from_tray,
            on_toggle_snooze=lambda: self.quick_snooze(30),
            on_lock=self.trigger_manual_lock,
            on_quit=self.quit_app,
        )

        self.protocol("WM_DELETE_WINDOW", self.on_close)

        # Build Clean UI Layout
        self._build_sidebar()
        self._build_content_area()

        # Start Polling Loop
        self.after(300, self._start_polling_loop)

        # Start System Tray
        self.tray_manager.start()

    # =========================================================================
    # CARD HELPER
    # =========================================================================
    def _create_card(self, parent: tk.Widget, **kwargs: Any) -> tk.Frame:
        """Creates a modern card frame with clean 1px border and white background."""
        return tk.Frame(
            parent, bg=CleanTheme.BG_CARD, highlightthickness=1,
            highlightbackground=CleanTheme.BORDER_CARD, **kwargs
        )

    # =========================================================================
    # SIDEBAR NAVIGATION
    # =========================================================================
    def _build_sidebar(self):
        self.sidebar = tk.Frame(
            self, bg=CleanTheme.BG_SIDEBAR, width=220,
            highlightthickness=1, highlightbackground=CleanTheme.BORDER_CARD
        )
        self.sidebar.pack(side="left", fill="y")
        self.sidebar.pack_propagate(False)

        # Brand Header
        brand_f = tk.Frame(self.sidebar, bg=CleanTheme.BG_SIDEBAR)
        brand_f.pack(fill="x", padx=18, pady=(20, 24))

        tk.Label(
            brand_f, text="🛡️ Chronos", font=(CleanTheme.FONT_FAMILY, 15, "bold"),
            fg=CleanTheme.TEXT_PRIMARY, bg=CleanTheme.BG_SIDEBAR
        ).pack(side="left")

        tk.Label(
            brand_f, text="AUTH", font=(CleanTheme.FONT_FAMILY, 10, "bold"),
            fg=CleanTheme.ACCENT_BLUE, bg=CleanTheme.ACCENT_BG, padx=6, pady=2
        ).pack(side="left", padx=6)

        # Navigation Items (Simplified to 4 Clear Tabs)
        self.nav_items: Dict[str, tuple] = {}
        tabs = [
            ("dashboard", "🛡️  Dashboard"),
            ("devices",   "📱  Devices"),
            ("alerts",    "🔔  Alerts & Remote"),
            ("settings",  "⚙️  Settings"),
        ]

        for tab_id, label in tabs:
            f = tk.Frame(self.sidebar, bg=CleanTheme.BG_SIDEBAR, cursor="hand2")
            f.pack(fill="x", padx=12, pady=4)

            ind = tk.Frame(f, bg=CleanTheme.BG_SIDEBAR, width=3, height=38)
            ind.pack(side="left", fill="y")

            lbl = tk.Label(
                f, text=label, font=(CleanTheme.FONT_FAMILY, 10),
                fg=CleanTheme.TEXT_PRIMARY, bg=CleanTheme.BG_SIDEBAR,
                padx=12, pady=8, anchor="w"
            )
            lbl.pack(side="left", fill="both", expand=True)

            def make_click(t=tab_id):
                return lambda e: self.switch_view(t)

            f.bind("<Button-1>", make_click(tab_id))
            lbl.bind("<Button-1>", make_click(tab_id))
            self.nav_items[tab_id] = (f, ind, lbl)

        # Sidebar Power / Service Status Card
        pwr = tk.Frame(self.sidebar, bg=CleanTheme.BG_APP, highlightthickness=1, highlightbackground=CleanTheme.BORDER_CARD)
        pwr.pack(side="bottom", fill="x", padx=12, pady=18)

        self.sb_guard_status = tk.Label(
            pwr, text="● Protection Active", font=(CleanTheme.FONT_FAMILY, 9, "bold"),
            fg=CleanTheme.SUCCESS, bg=CleanTheme.BG_APP
        )
        self.sb_guard_status.pack(padx=12, pady=(12, 2), anchor="w")

        self.sb_sim_status = tk.Label(
            pwr, text="Mode: Safe Simulation", font=(CleanTheme.FONT_FAMILY, 8),
            fg=CleanTheme.TEXT_MUTED, bg=CleanTheme.BG_APP
        )
        self.sb_sim_status.pack(padx=12, pady=(0, 8), anchor="w")

        self.sb_toggle_btn = tk.Button(
            pwr, text="Pause Guard", font=(CleanTheme.FONT_FAMILY, 9, "bold"),
            bg="#FFFFFF", fg=CleanTheme.TEXT_PRIMARY, relief="solid", borderwidth=1,
            padx=8, pady=4, cursor="hand2", command=self.toggle_guard_service
        )
        self.sb_toggle_btn.pack(padx=12, pady=(0, 12), fill="x")

    # =========================================================================
    # CONTENT CONTAINER & TAB SWITCHER
    # =========================================================================
    def _build_content_area(self):
        self.content_container = tk.Frame(self, bg=CleanTheme.BG_APP)
        self.content_container.pack(side="right", fill="both", expand=True)

        self.views: Dict[str, tk.Frame] = {}
        self._build_dashboard_tab()
        self._build_devices_tab()
        self._build_alerts_tab()
        self._build_settings_tab()

        self.switch_view("dashboard")

    def switch_view(self, target_id: str):
        for tab_id, frame in self.views.items():
            f, ind, lbl = self.nav_items[tab_id]
            if tab_id == target_id:
                frame.pack(fill="both", expand=True, padx=24, pady=20)
                f.configure(bg=CleanTheme.BG_PILL_ACTIVE)
                ind.configure(bg=CleanTheme.ACCENT_BLUE)
                lbl.configure(bg=CleanTheme.BG_PILL_ACTIVE, fg=CleanTheme.ACCENT_BLUE, font=(CleanTheme.FONT_FAMILY, 10, "bold"))
            else:
                frame.pack_forget()
                f.configure(bg=CleanTheme.BG_SIDEBAR)
                ind.configure(bg=CleanTheme.BG_SIDEBAR)
                lbl.configure(bg=CleanTheme.BG_SIDEBAR, fg=CleanTheme.TEXT_PRIMARY, font=(CleanTheme.FONT_FAMILY, 10))

    # =========================================================================
    # TAB 1: DASHBOARD (SIMPLE, INTUITIVE, UNCLUTTERED)
    # =========================================================================
    def _build_dashboard_tab(self):
        v = tk.Frame(self.content_container, bg=CleanTheme.BG_APP)
        self.views["dashboard"] = v

        # Top Header Strip
        hdr = tk.Frame(v, bg=CleanTheme.BG_APP)
        hdr.pack(fill="x", pady=(0, 14))

        hdr_left = tk.Frame(hdr, bg=CleanTheme.BG_APP)
        hdr_left.pack(side="left")

        tk.Label(
            hdr_left, text="Security Dashboard", font=(CleanTheme.FONT_FAMILY, 16, "bold"),
            fg=CleanTheme.TEXT_PRIMARY, bg=CleanTheme.BG_APP
        ).pack(anchor="w")

        tk.Label(
            hdr_left, text="Continuous Neuromuscular & Kinematic Biometrics",
            font=(CleanTheme.FONT_FAMILY, 9), fg=CleanTheme.TEXT_MUTED, bg=CleanTheme.BG_APP
        ).pack(anchor="w")

        # Top Right Controls & Badges
        hdr_right = tk.Frame(hdr, bg=CleanTheme.BG_APP)
        hdr_right.pack(side="right")

        self.db_mode_badge = tk.Label(
            hdr_right, text="Simulation Mode", font=(CleanTheme.FONT_FAMILY, 8, "bold"),
            fg=CleanTheme.WARNING, bg=CleanTheme.WARNING_BG, padx=8, pady=3,
            highlightthickness=1, highlightbackground=CleanTheme.WARNING_BORDER
        )
        self.db_mode_badge.pack(side="left", padx=4)

        self.db_status_pill = tk.Label(
            hdr_right, text="● Owner Verified", font=(CleanTheme.FONT_FAMILY, 8, "bold"),
            fg=CleanTheme.SUCCESS, bg=CleanTheme.SUCCESS_BG, padx=10, pady=3,
            highlightthickness=1, highlightbackground=CleanTheme.SUCCESS_BORDER
        )
        self.db_status_pill.pack(side="left", padx=4)

        tk.Button(
            hdr_right, text="🔒 Lock PC", font=(CleanTheme.FONT_FAMILY, 8, "bold"),
            bg=CleanTheme.DANGER_BG, fg=CleanTheme.DANGER, relief="solid", borderwidth=1,
            padx=10, pady=2, cursor="hand2", command=self.trigger_manual_lock
        ).pack(side="left", padx=4)

        # ---------------------------------------------------------------------
        # Card 1: Primary Trust Score & ML Confidence Card
        # ---------------------------------------------------------------------
        c_hero = self._create_card(v)
        c_hero.pack(fill="x", pady=(0, 12))

        hero_in = tk.Frame(c_hero, bg=CleanTheme.BG_CARD)
        hero_in.pack(fill="both", expand=True, padx=20, pady=16)

        # Left Column: Cumulative Trust
        h_left = tk.Frame(hero_in, bg=CleanTheme.BG_CARD)
        h_left.pack(side="left", fill="both", expand=True, padx=(0, 16))

        tk.Label(
            h_left, text="CUMULATIVE TRUST", font=(CleanTheme.FONT_FAMILY, 8, "bold"),
            fg=CleanTheme.TEXT_MUTED, bg=CleanTheme.BG_CARD
        ).pack(anchor="w")

        self.db_trust_val = tk.Label(
            h_left, text="100.0%", font=(CleanTheme.FONT_FAMILY, 30, "bold"),
            fg=CleanTheme.SUCCESS, bg=CleanTheme.BG_CARD
        )
        self.db_trust_val.pack(anchor="w", pady=(1, 2))

        self.db_trust_bar = TrustProgressBar(h_left, width=160, height=8)
        self.db_trust_bar.pack(anchor="w", pady=(0, 4))

        self.db_trust_sub = tk.Label(
            h_left, text="SPRT Decision: Owner Authenticated", font=(CleanTheme.FONT_FAMILY, 8),
            fg=CleanTheme.TEXT_SECONDARY, bg=CleanTheme.BG_CARD
        )
        self.db_trust_sub.pack(anchor="w")

        # Middle Column: Instant ML Score
        h_mid = tk.Frame(hero_in, bg=CleanTheme.BG_CARD)
        h_mid.pack(side="left", fill="both", expand=True, padx=16)

        tk.Label(
            h_mid, text="INSTANT ML MATCH", font=(CleanTheme.FONT_FAMILY, 8, "bold"),
            fg=CleanTheme.TEXT_MUTED, bg=CleanTheme.BG_CARD
        ).pack(anchor="w")

        self.db_instant_val = tk.Label(
            h_mid, text="99.9%", font=(CleanTheme.FONT_FAMILY, 30, "bold"),
            fg=CleanTheme.SUCCESS, bg=CleanTheme.BG_CARD
        )
        self.db_instant_val.pack(anchor="w", pady=(1, 2))

        self.db_model_source_lbl = tk.Label(
            h_mid, text="Model: Calibrated Keystroke Classifier", font=(CleanTheme.FONT_FAMILY, 8),
            fg=CleanTheme.TEXT_SECONDARY, bg=CleanTheme.BG_CARD
        )
        self.db_model_source_lbl.pack(anchor="w")

        # Right Column: Trend Sparkline
        h_right = tk.Frame(hero_in, bg=CleanTheme.BG_CARD)
        h_right.pack(side="right", padx=(16, 0))

        tk.Label(
            h_right, text="Trust Score Trend", font=(CleanTheme.FONT_FAMILY, 8),
            fg=CleanTheme.TEXT_MUTED, bg=CleanTheme.BG_CARD
        ).pack(anchor="e", pady=(0, 4))

        self.db_sparkline = SmoothSparkline(h_right, width=220, height=52)
        self.db_sparkline.pack(anchor="e")

        # ---------------------------------------------------------------------
        # Card 2: 4 Real Biometric Metric Tiles
        # ---------------------------------------------------------------------
        c_tiles = tk.Frame(v, bg=CleanTheme.BG_APP)
        c_tiles.pack(fill="x", pady=(0, 12))

        # Tile 1: Dwell
        t1 = self._create_card(c_tiles)
        t1.pack(side="left", fill="both", expand=True, padx=(0, 6))
        t1_in = tk.Frame(t1, bg=CleanTheme.BG_CARD, padx=14, pady=10)
        t1_in.pack(fill="both", expand=True)
        tk.Label(t1_in, text="KEY DWELL TIME", font=(CleanTheme.FONT_FAMILY, 7, "bold"), fg=CleanTheme.TEXT_MUTED, bg=CleanTheme.BG_CARD).pack(anchor="w")
        self.db_dwell_val = tk.Label(t1_in, text="— ms", font=(CleanTheme.FONT_MONO, 16, "bold"), fg=CleanTheme.TEXT_PRIMARY, bg=CleanTheme.BG_CARD)
        self.db_dwell_val.pack(anchor="w", pady=(2, 0))
        tk.Label(t1_in, text="Baseline: 93 ± 32 ms", font=(CleanTheme.FONT_FAMILY, 7), fg=CleanTheme.TEXT_MUTED, bg=CleanTheme.BG_CARD).pack(anchor="w")

        # Tile 2: Flight
        t2 = self._create_card(c_tiles)
        t2.pack(side="left", fill="both", expand=True, padx=6)
        t2_in = tk.Frame(t2, bg=CleanTheme.BG_CARD, padx=14, pady=10)
        t2_in.pack(fill="both", expand=True)
        tk.Label(t2_in, text="FLIGHT LATENCY", font=(CleanTheme.FONT_FAMILY, 7, "bold"), fg=CleanTheme.TEXT_MUTED, bg=CleanTheme.BG_CARD).pack(anchor="w")
        self.db_flight_val = tk.Label(t2_in, text="— ms", font=(CleanTheme.FONT_MONO, 16, "bold"), fg=CleanTheme.TEXT_PRIMARY, bg=CleanTheme.BG_CARD)
        self.db_flight_val.pack(anchor="w", pady=(2, 0))
        tk.Label(t2_in, text="Baseline: 184 ± 223 ms", font=(CleanTheme.FONT_FAMILY, 7), fg=CleanTheme.TEXT_MUTED, bg=CleanTheme.BG_CARD).pack(anchor="w")

        # Tile 3: Typing Speed
        t3 = self._create_card(c_tiles)
        t3.pack(side="left", fill="both", expand=True, padx=6)
        t3_in = tk.Frame(t3, bg=CleanTheme.BG_CARD, padx=14, pady=10)
        t3_in.pack(fill="both", expand=True)
        tk.Label(t3_in, text="TYPING CADENCE", font=(CleanTheme.FONT_FAMILY, 7, "bold"), fg=CleanTheme.TEXT_MUTED, bg=CleanTheme.BG_CARD).pack(anchor="w")
        self.db_speed_val = tk.Label(t3_in, text="— keys/s", font=(CleanTheme.FONT_MONO, 16, "bold"), fg=CleanTheme.TEXT_PRIMARY, bg=CleanTheme.BG_CARD)
        self.db_speed_val.pack(anchor="w", pady=(2, 0))
        tk.Label(t3_in, text="Baseline: 4.7 ± 1.6 keys/s", font=(CleanTheme.FONT_FAMILY, 7), fg=CleanTheme.TEXT_MUTED, bg=CleanTheme.BG_CARD).pack(anchor="w")

        # Tile 4: Active Context
        t4 = self._create_card(c_tiles)
        t4.pack(side="left", fill="both", expand=True, padx=(6, 0))
        t4_in = tk.Frame(t4, bg=CleanTheme.BG_CARD, padx=14, pady=10)
        t4_in.pack(fill="both", expand=True)
        tk.Label(t4_in, text="ACTIVE CONTEXT", font=(CleanTheme.FONT_FAMILY, 7, "bold"), fg=CleanTheme.TEXT_MUTED, bg=CleanTheme.BG_CARD).pack(anchor="w")
        self.db_context_val = tk.Label(t4_in, text="General", font=(CleanTheme.FONT_FAMILY, 15, "bold"), fg=CleanTheme.TEXT_PRIMARY, bg=CleanTheme.BG_CARD)
        self.db_context_val.pack(anchor="w", pady=(2, 0))
        self.db_app_val = tk.Label(t4_in, text="Window: Desktop", font=(CleanTheme.FONT_FAMILY, 7), fg=CleanTheme.TEXT_MUTED, bg=CleanTheme.BG_CARD)
        self.db_app_val.pack(anchor="w")

        # ---------------------------------------------------------------------
        # Card 3: Live AI Feature Attribution & Explainability
        # ---------------------------------------------------------------------
        c_attr = self._create_card(v)
        c_attr.pack(fill="both", expand=True, pady=(0, 12))

        attr_in = tk.Frame(c_attr, bg=CleanTheme.BG_CARD)
        attr_in.pack(fill="both", expand=True, padx=20, pady=14)

        attr_hdr = tk.Frame(attr_in, bg=CleanTheme.BG_CARD)
        attr_hdr.pack(fill="x", pady=(0, 8))

        tk.Label(
            attr_hdr, text="LIVE AI FEATURE ATTRIBUTION & EXPLAINABILITY",
            font=(CleanTheme.FONT_FAMILY, 9, "bold"), fg=CleanTheme.TEXT_MUTED, bg=CleanTheme.BG_CARD
        ).pack(side="left")

        self.db_attr_status = tk.Label(
            attr_hdr, text="● Real-Time ML Active", font=(CleanTheme.FONT_FAMILY, 8, "bold"),
            fg=CleanTheme.SUCCESS, bg=CleanTheme.SUCCESS_BG, padx=8, pady=2,
            highlightthickness=1, highlightbackground=CleanTheme.SUCCESS_BORDER
        )
        self.db_attr_status.pack(side="right")

        # 4 Dynamic Attribution Display Rows
        self.db_attr_rows: List[tk.Label] = []
        for _ in range(4):
            row = tk.Label(
                attr_in, text="ℹ️ Monitoring live interaction — start typing or moving cursor to view real-time evidence.",
                font=(CleanTheme.FONT_FAMILY, 9), fg=CleanTheme.TEXT_SECONDARY, bg=CleanTheme.BG_CARD,
                anchor="w", justify="left"
            )
            row.pack(fill="x", pady=2)
            self.db_attr_rows.append(row)

        # ---------------------------------------------------------------------
        # Card 4: Quick Controls & Snooze Bar
        # ---------------------------------------------------------------------
        c_ctrl = self._create_card(v)
        c_ctrl.pack(fill="x")

        ctrl_in = tk.Frame(c_ctrl, bg=CleanTheme.BG_CARD)
        ctrl_in.pack(fill="both", expand=True, padx=18, pady=10)

        # Snooze presets
        snooze_f = tk.Frame(ctrl_in, bg=CleanTheme.BG_CARD)
        snooze_f.pack(side="left")

        tk.Label(
            snooze_f, text="Lend PC / Snooze:", font=(CleanTheme.FONT_FAMILY, 8, "bold"),
            fg=CleanTheme.TEXT_MUTED, bg=CleanTheme.BG_CARD
        ).pack(side="left", padx=(0, 8))

        for mins, label in [(15, "15m"), (30, "30m"), (60, "1h")]:
            tk.Button(
                snooze_f, text=label, font=(CleanTheme.FONT_FAMILY, 8),
                bg=CleanTheme.BG_APP, fg=CleanTheme.TEXT_PRIMARY, relief="solid", borderwidth=1,
                padx=8, pady=1, cursor="hand2", command=lambda m=mins: self.quick_snooze(m)
            ).pack(side="left", padx=2)

        tk.Button(
            snooze_f, text="Resume Protection", font=(CleanTheme.FONT_FAMILY, 8, "bold"),
            bg=CleanTheme.SUCCESS_BG, fg=CleanTheme.SUCCESS, relief="solid", borderwidth=1,
            padx=8, pady=1, cursor="hand2", command=self.cancel_snooze
        ).pack(side="left", padx=(6, 0))

        # Reset trust score
        reset_f = tk.Frame(ctrl_in, bg=CleanTheme.BG_CARD)
        reset_f.pack(side="right")

        tk.Button(
            reset_f, text="⚡ Reset Trust to 100%", font=(CleanTheme.FONT_FAMILY, 8, "bold"),
            bg=CleanTheme.ACCENT_BG, fg=CleanTheme.ACCENT_BLUE, relief="flat",
            padx=10, pady=2, cursor="hand2", command=self.reset_trust_score
        ).pack(side="right")

    # =========================================================================
    # TAB 2: DEVICES (BLUETOOTH PROXIMITY)
    # =========================================================================
    def _build_devices_tab(self):
        v = tk.Frame(self.content_container, bg=CleanTheme.BG_APP)
        self.views["devices"] = v

        tk.Label(
            v, text="Bluetooth Proximity & Devices", font=(CleanTheme.FONT_FAMILY, 16, "bold"),
            fg=CleanTheme.TEXT_PRIMARY, bg=CleanTheme.BG_APP
        ).pack(anchor="w", pady=(0, 14))

        # Card 1: Active Target Device
        c1 = self._create_card(v)
        c1.pack(fill="x", pady=(0, 14))

        c1_in = tk.Frame(c1, bg=CleanTheme.BG_CARD)
        c1_in.pack(fill="both", expand=True, padx=20, pady=16)

        c1_top = tk.Frame(c1_in, bg=CleanTheme.BG_CARD)
        c1_top.pack(fill="x", pady=(0, 8))

        tk.Label(
            c1_top, text="PAIRED PROXIMITY DEVICE", font=(CleanTheme.FONT_FAMILY, 9, "bold"),
            fg=CleanTheme.TEXT_MUTED, bg=CleanTheme.BG_CARD
        ).pack(side="left")

        self.dev_meter = SignalBarMeter(c1_top, width=90, height=20)
        self.dev_meter.pack(side="right")

        self.dev_target_name = tk.Label(
            c1_in, text="No device paired", font=(CleanTheme.FONT_FAMILY, 14, "bold"),
            fg=CleanTheme.TEXT_PRIMARY, bg=CleanTheme.BG_CARD
        )
        self.dev_target_name.pack(anchor="w")

        self.dev_target_mac = tk.Label(
            c1_in, text="Scan nearby devices below to pair your phone or smartwatch",
            font=(CleanTheme.FONT_FAMILY, 9), fg=CleanTheme.TEXT_MUTED, bg=CleanTheme.BG_CARD
        )
        self.dev_target_mac.pack(anchor="w", pady=(2, 6))

        self.dev_conn_status = tk.Label(
            c1_in, text="Status: Disconnected", font=(CleanTheme.FONT_FAMILY, 9, "bold"),
            fg=CleanTheme.DANGER, bg=CleanTheme.BG_CARD
        )
        self.dev_conn_status.pack(anchor="w")

        # Card 2: Nearby Scanned Devices
        c2 = self._create_card(v)
        c2.pack(fill="both", expand=True)

        c2_in = tk.Frame(c2, bg=CleanTheme.BG_CARD)
        c2_in.pack(fill="both", expand=True, padx=20, pady=16)

        c2_top = tk.Frame(c2_in, bg=CleanTheme.BG_CARD)
        c2_top.pack(fill="x", pady=(0, 10))

        tk.Label(
            c2_top, text="DISCOVERED BLUETOOTH DEVICES", font=(CleanTheme.FONT_FAMILY, 9, "bold"),
            fg=CleanTheme.TEXT_MUTED, bg=CleanTheme.BG_CARD
        ).pack(side="left")

        tk.Button(
            c2_top, text="🔍 Scan Devices", font=(CleanTheme.FONT_FAMILY, 8, "bold"),
            bg=CleanTheme.ACCENT_BLUE, fg="#FFFFFF", relief="flat", padx=10, pady=3,
            cursor="hand2", command=self.scan_bluetooth
        ).pack(side="right")

        # Table of scanned devices
        cols = ("Name", "MAC Address", "Status")
        self.dev_table = ttk.Treeview(c2_in, columns=cols, show="headings", height=8)
        self.dev_table.heading("Name", text="Device Name")
        self.dev_table.heading("MAC Address", text="Bluetooth MAC Address")
        self.dev_table.heading("Status", text="Connection State")
        self.dev_table.column("Name", width=220)
        self.dev_table.column("MAC Address", width=180)
        self.dev_table.column("Status", width=140)
        self.dev_table.pack(fill="both", expand=True, pady=(0, 10))

        btn_row = tk.Frame(c2_in, bg=CleanTheme.BG_CARD)
        btn_row.pack(fill="x")

        tk.Button(
            btn_row, text="Pair Selected Device", font=(CleanTheme.FONT_FAMILY, 9, "bold"),
            bg=CleanTheme.SUCCESS, fg="#FFFFFF", relief="flat", padx=12, pady=5,
            cursor="hand2", command=self.pair_selected_device
        ).pack(side="left")

        tk.Button(
            btn_row, text="Unpair Device", font=(CleanTheme.FONT_FAMILY, 9),
            bg=CleanTheme.BG_APP, fg=CleanTheme.DANGER, relief="solid", borderwidth=1, padx=12, pady=5,
            cursor="hand2", command=self.unpair_device
        ).pack(side="left", padx=8)

    # =========================================================================
    # TAB 3: ALERTS & REMOTE
    # =========================================================================
    def _build_alerts_tab(self):
        v = tk.Frame(self.content_container, bg=CleanTheme.BG_APP)
        self.views["alerts"] = v

        tk.Label(
            v, text="Remote Alerts & Notifications", font=(CleanTheme.FONT_FAMILY, 16, "bold"),
            fg=CleanTheme.TEXT_PRIMARY, bg=CleanTheme.BG_APP
        ).pack(anchor="w", pady=(0, 14))

        creds = self.cred_store.load()
        tg_cfg = creds.get("telegram", {})
        smtp_cfg = creds.get("smtp", {})

        # Card 1: Telegram Alerts
        c_tg = self._create_card(v)
        c_tg.pack(fill="x", pady=(0, 14))

        tg_in = tk.Frame(c_tg, bg=CleanTheme.BG_CARD)
        tg_in.pack(fill="both", expand=True, padx=20, pady=16)

        tk.Label(
            tg_in, text="TELEGRAM BOT NOTIFICATIONS", font=(CleanTheme.FONT_FAMILY, 9, "bold"),
            fg=CleanTheme.TEXT_MUTED, bg=CleanTheme.BG_CARD
        ).pack(anchor="w", pady=(0, 6))

        tg_grid = tk.Frame(tg_in, bg=CleanTheme.BG_CARD)
        tg_grid.pack(fill="x", pady=(0, 8))

        tk.Label(tg_grid, text="Bot Token:", font=(CleanTheme.FONT_FAMILY, 9), bg=CleanTheme.BG_CARD).grid(row=0, column=0, sticky="w", pady=4)
        self.tg_token_entry = tk.Entry(tg_grid, font=(CleanTheme.FONT_FAMILY, 9), width=36)
        self.tg_token_entry.insert(0, str(tg_cfg.get("token", "")))
        self.tg_token_entry.grid(row=0, column=1, padx=8, pady=4, sticky="w")

        tk.Label(tg_grid, text="Chat ID:", font=(CleanTheme.FONT_FAMILY, 9), bg=CleanTheme.BG_CARD).grid(row=1, column=0, sticky="w", pady=4)
        self.tg_chat_entry = tk.Entry(tg_grid, font=(CleanTheme.FONT_FAMILY, 9), width=24)
        self.tg_chat_entry.insert(0, str(tg_cfg.get("chat_id", "")))
        self.tg_chat_entry.grid(row=1, column=1, padx=8, pady=4, sticky="w")

        tk.Button(
            tg_grid, text="🔍 Auto-Detect", font=(CleanTheme.FONT_FAMILY, 8),
            bg=CleanTheme.BG_APP, fg=CleanTheme.TEXT_PRIMARY, relief="solid", borderwidth=1, padx=8, pady=2,
            cursor="hand2", command=self.detect_telegram_chat_id
        ).grid(row=1, column=2, padx=4, pady=4, sticky="w")

        self.tg_enabled_var = tk.BooleanVar(value=bool(tg_cfg.get("enabled", True)))
        tk.Checkbutton(
            tg_in, text="Enable Telegram alerts on security warnings and lockouts",
            variable=self.tg_enabled_var, font=(CleanTheme.FONT_FAMILY, 9), bg=CleanTheme.BG_CARD
        ).pack(anchor="w", pady=(0, 8))

        tg_btns = tk.Frame(tg_in, bg=CleanTheme.BG_CARD)
        tg_btns.pack(fill="x")

        tk.Button(
            tg_btns, text="Save Telegram Settings", font=(CleanTheme.FONT_FAMILY, 8, "bold"),
            bg=CleanTheme.ACCENT_BLUE, fg="#FFFFFF", relief="flat", padx=10, pady=4,
            cursor="hand2", command=self.save_telegram_settings
        ).pack(side="left")

        tk.Button(
            tg_btns, text="Send Test Alert", font=(CleanTheme.FONT_FAMILY, 8),
            bg=CleanTheme.BG_APP, fg=CleanTheme.TEXT_PRIMARY, relief="solid", borderwidth=1, padx=10, pady=4,
            cursor="hand2", command=self.test_telegram_alert
        ).pack(side="left", padx=8)

        # Card 2: Email Alerts
        c_em = self._create_card(v)
        c_em.pack(fill="x")

        em_in = tk.Frame(c_em, bg=CleanTheme.BG_CARD)
        em_in.pack(fill="both", expand=True, padx=20, pady=16)

        tk.Label(
            em_in, text="EMAIL / SMTP ALERTS", font=(CleanTheme.FONT_FAMILY, 9, "bold"),
            fg=CleanTheme.TEXT_MUTED, bg=CleanTheme.BG_CARD
        ).pack(anchor="w", pady=(0, 6))

        em_grid = tk.Frame(em_in, bg=CleanTheme.BG_CARD)
        em_grid.pack(fill="x", pady=(0, 8))

        tk.Label(em_grid, text="SMTP Server:", font=(CleanTheme.FONT_FAMILY, 9), bg=CleanTheme.BG_CARD).grid(row=0, column=0, sticky="w", pady=4)
        self.em_host_entry = tk.Entry(em_grid, font=(CleanTheme.FONT_FAMILY, 9), width=24)
        self.em_host_entry.insert(0, str(smtp_cfg.get("host", "smtp.gmail.com")))
        self.em_host_entry.grid(row=0, column=1, padx=8, pady=4, sticky="w")

        tk.Label(em_grid, text="Port:", font=(CleanTheme.FONT_FAMILY, 9), bg=CleanTheme.BG_CARD).grid(row=0, column=2, sticky="w", pady=4)
        self.em_port_entry = tk.Entry(em_grid, font=(CleanTheme.FONT_FAMILY, 9), width=8)
        self.em_port_entry.insert(0, str(smtp_cfg.get("port", 587)))
        self.em_port_entry.grid(row=0, column=3, padx=8, pady=4, sticky="w")

        tk.Label(em_grid, text="Username:", font=(CleanTheme.FONT_FAMILY, 9), bg=CleanTheme.BG_CARD).grid(row=1, column=0, sticky="w", pady=4)
        self.em_user_entry = tk.Entry(em_grid, font=(CleanTheme.FONT_FAMILY, 9), width=24)
        self.em_user_entry.insert(0, str(smtp_cfg.get("user", "")))
        self.em_user_entry.grid(row=1, column=1, padx=8, pady=4, sticky="w")

        tk.Label(em_grid, text="Recipient:", font=(CleanTheme.FONT_FAMILY, 9), bg=CleanTheme.BG_CARD).grid(row=1, column=2, sticky="w", pady=4)
        self.em_rcpt_entry = tk.Entry(em_grid, font=(CleanTheme.FONT_FAMILY, 9), width=24)
        self.em_rcpt_entry.insert(0, str(smtp_cfg.get("recipient", "")))
        self.em_rcpt_entry.grid(row=1, column=3, padx=8, pady=4, sticky="w")

        self.em_enabled_var = tk.BooleanVar(value=bool(smtp_cfg.get("enabled", True)))
        tk.Checkbutton(
            em_in, text="Enable Email alerts on lockouts",
            variable=self.em_enabled_var, font=(CleanTheme.FONT_FAMILY, 9), bg=CleanTheme.BG_CARD
        ).pack(anchor="w", pady=(0, 8))

        em_btns = tk.Frame(em_in, bg=CleanTheme.BG_CARD)
        em_btns.pack(fill="x")

        tk.Button(
            em_btns, text="Save Email Settings", font=(CleanTheme.FONT_FAMILY, 8, "bold"),
            bg=CleanTheme.ACCENT_BLUE, fg="#FFFFFF", relief="flat", padx=10, pady=4,
            cursor="hand2", command=self.save_email_settings
        ).pack(side="left")

        tk.Button(
            em_btns, text="Send Test Email", font=(CleanTheme.FONT_FAMILY, 8),
            bg=CleanTheme.BG_APP, fg=CleanTheme.TEXT_PRIMARY, relief="solid", borderwidth=1, padx=10, pady=4,
            cursor="hand2", command=self.test_email_alert
        ).pack(side="left", padx=8)

    # =========================================================================
    # TAB 4: SETTINGS & ENFORCEMENT
    # =========================================================================
    def _build_settings_tab(self):
        v = tk.Frame(self.content_container, bg=CleanTheme.BG_APP)
        self.views["settings"] = v

        tk.Label(
            v, text="Security Settings & Protection Policy", font=(CleanTheme.FONT_FAMILY, 16, "bold"),
            fg=CleanTheme.TEXT_PRIMARY, bg=CleanTheme.BG_APP
        ).pack(anchor="w", pady=(0, 14))

        policy = self.policy_store.load()

        # Card 1: Enforcement Mode
        c1 = self._create_card(v)
        c1.pack(fill="x", pady=(0, 14))

        c1_in = tk.Frame(c1, bg=CleanTheme.BG_CARD)
        c1_in.pack(fill="both", expand=True, padx=20, pady=16)

        tk.Label(
            c1_in, text="LOCK ENFORCEMENT MODE", font=(CleanTheme.FONT_FAMILY, 9, "bold"),
            fg=CleanTheme.TEXT_MUTED, bg=CleanTheme.BG_CARD
        ).pack(anchor="w", pady=(0, 6))

        self.set_sim_var = tk.IntVar(value=1 if self.simulate_lock else 0)

        tk.Radiobutton(
            c1_in, text="Simulation Mode (Safe — alerts and logs suspicious activity without locking your screen)",
            variable=self.set_sim_var, value=1, font=(CleanTheme.FONT_FAMILY, 9),
            bg=CleanTheme.BG_CARD, command=self.on_mode_toggled
        ).pack(anchor="w", pady=2)

        tk.Radiobutton(
            c1_in, text="Active Enforcement (Armed — immediately locks workstation screen when confidence falls below barrier)",
            variable=self.set_sim_var, value=0, font=(CleanTheme.FONT_FAMILY, 9, "bold"),
            fg=CleanTheme.DANGER, bg=CleanTheme.BG_CARD, command=self.on_mode_toggled
        ).pack(anchor="w", pady=2)

        # Card 2: Sensitivity & Alert Threshold
        c2 = self._create_card(v)
        c2.pack(fill="x", pady=(0, 14))

        c2_in = tk.Frame(c2, bg=CleanTheme.BG_CARD)
        c2_in.pack(fill="both", expand=True, padx=20, pady=16)

        tk.Label(
            c2_in, text="SECURITY SENSITIVITY PROFILE", font=(CleanTheme.FONT_FAMILY, 9, "bold"),
            fg=CleanTheme.TEXT_MUTED, bg=CleanTheme.BG_CARD
        ).pack(anchor="w", pady=(0, 6))

        self.set_sens_var = tk.StringVar(value=policy.get("sensitivity", "Balanced"))

        sens_f = tk.Frame(c2_in, bg=CleanTheme.BG_CARD)
        sens_f.pack(fill="x", pady=(0, 10))

        for opt in ["Relaxed", "Balanced", "Strict"]:
            tk.Radiobutton(
                sens_f, text=opt, variable=self.set_sens_var, value=opt,
                font=(CleanTheme.FONT_FAMILY, 9), bg=CleanTheme.BG_CARD
            ).pack(side="left", padx=(0, 16))

        tk.Label(
            c2_in, text="Warning Alert Threshold (%):", font=(CleanTheme.FONT_FAMILY, 9),
            bg=CleanTheme.BG_CARD
        ).pack(anchor="w", pady=(6, 2))

        self.set_thresh_var = tk.IntVar(value=int(policy.get("warning_threshold", 50)))
        thresh_scale = tk.Scale(
            c2_in, from_=20, to=80, orient="horizontal", variable=self.set_thresh_var,
            bg=CleanTheme.BG_CARD, highlightthickness=0, length=280
        )
        thresh_scale.pack(anchor="w", pady=(0, 10))

        tk.Button(
            c2_in, text="Save Policy Settings", font=(CleanTheme.FONT_FAMILY, 8, "bold"),
            bg=CleanTheme.ACCENT_BLUE, fg="#FFFFFF", relief="flat", padx=12, pady=4,
            cursor="hand2", command=self.save_policy_settings
        ).pack(anchor="w")

        # Card 3: Excluded Applications
        c3 = self._create_card(v)
        c3.pack(fill="both", expand=True)

        c3_in = tk.Frame(c3, bg=CleanTheme.BG_CARD)
        c3_in.pack(fill="both", expand=True, padx=20, pady=16)

        tk.Label(
            c3_in, text="EXCLUDED APPLICATIONS (MONITORING PAUSED)",
            font=(CleanTheme.FONT_FAMILY, 9, "bold"), fg=CleanTheme.TEXT_MUTED, bg=CleanTheme.BG_CARD
        ).pack(anchor="w", pady=(0, 4))

        tk.Label(
            c3_in, text="Applications in this list bypass continuous lockout (e.g. video games, full-screen media).",
            font=(CleanTheme.FONT_FAMILY, 8), fg=CleanTheme.TEXT_MUTED, bg=CleanTheme.BG_CARD
        ).pack(anchor="w", pady=(0, 8))

        self.excl_listbox = tk.Listbox(c3_in, font=(CleanTheme.FONT_FAMILY, 9), height=4)
        for app_n in policy.get("excluded_apps", []):
            self.excl_listbox.insert("end", app_n)
        self.excl_listbox.pack(fill="x", pady=(0, 8))

        excl_btns = tk.Frame(c3_in, bg=CleanTheme.BG_CARD)
        excl_btns.pack(fill="x")

        self.excl_entry = tk.Entry(excl_btns, font=(CleanTheme.FONT_FAMILY, 9), width=20)
        self.excl_entry.pack(side="left", padx=(0, 6))

        tk.Button(
            excl_btns, text="Add Application", font=(CleanTheme.FONT_FAMILY, 8),
            bg=CleanTheme.BG_APP, fg=CleanTheme.TEXT_PRIMARY, relief="solid", borderwidth=1,
            padx=8, pady=2, cursor="hand2", command=self.add_excluded_app
        ).pack(side="left", padx=4)

        tk.Button(
            excl_btns, text="Remove Selected", font=(CleanTheme.FONT_FAMILY, 8),
            bg=CleanTheme.BG_APP, fg=CleanTheme.DANGER, relief="solid", borderwidth=1,
            padx=8, pady=2, cursor="hand2", command=self.remove_excluded_app
        ).pack(side="left", padx=4)

    # =========================================================================
    # SYSTEM POLLING & REAL-TIME DASHBOARD UPDATE LOOP
    # =========================================================================
    def _start_polling_loop(self):
        self._poll_system_state()
        if self.is_running_app:
            self.after(1000, self._start_polling_loop)

    def _poll_system_state(self):
        if not self.is_running_app:
            return

        # 1. Check if receiver.py process is active
        try:
            res = subprocess.run(["pgrep", "-f", "receiver.py"], capture_output=True)
            self.is_service_running = (res.returncode == 0)
        except Exception:
            self.is_service_running = False

        if self.is_service_running:
            self.sb_guard_status.configure(text="● Protection Active", fg=CleanTheme.SUCCESS)
            self.sb_toggle_btn.configure(text="Pause Guard")
        else:
            self.sb_guard_status.configure(text="○ Protection Off", fg=CleanTheme.DANGER)
            self.sb_toggle_btn.configure(text="Start Guard")

        # Sync lock mode
        self.simulate_lock = (get_lock_mode() != "enforce")
        sim_txt = "Simulation Mode (Safe)" if self.simulate_lock else "Enforcement Active (Armed)"
        sim_fg = CleanTheme.WARNING if self.simulate_lock else CleanTheme.DANGER
        sim_bg = CleanTheme.WARNING_BG if self.simulate_lock else CleanTheme.DANGER_BG
        sim_border = CleanTheme.WARNING_BORDER if self.simulate_lock else CleanTheme.DANGER_BORDER
        self.db_mode_badge.configure(text=sim_txt, fg=sim_fg, bg=sim_bg, highlightbackground=sim_border)
        self.sb_sim_status.configure(text=f"Mode: {'Safe Simulation' if self.simulate_lock else 'Enforced Lock'}")

        # 2. Read live JSON state file
        target_state = LIVE_STATE_PATH if LIVE_STATE_PATH.exists() else LEGACY_LIVE_STATE_PATH
        state_data: Optional[Dict[str, Any]] = None

        if target_state.exists():
            try:
                with open(target_state, "r", encoding="utf-8") as f:
                    state_data = json.load(f)
            except Exception:
                pass

        if state_data and self.is_service_running:
            trust = float(state_data.get("trust_pct", 100.0))
            instant = float(state_data.get("instant_score_pct", 100.0))
            action = state_data.get("action", "CONTINUE")
            self.last_trust = trust
            self.last_action = action

            # Update Trust Numbers & Bar
            self.db_trust_val.configure(text=f"{trust:.1f}%")
            self.db_trust_bar.set_pct(trust)
            self.db_sparkline.append_value(trust)

            # Color styling based on trust score
            col = CleanTheme.SUCCESS if trust >= 80 else (CleanTheme.WARNING if trust >= 50 else CleanTheme.DANGER)
            bg_col = CleanTheme.SUCCESS_BG if trust >= 80 else (CleanTheme.WARNING_BG if trust >= 50 else CleanTheme.DANGER_BG)
            border_col = CleanTheme.SUCCESS_BORDER if trust >= 80 else (CleanTheme.WARNING_BORDER if trust >= 50 else CleanTheme.DANGER_BORDER)

            self.db_trust_val.configure(fg=col)
            self.db_status_pill.configure(
                text=f"● {action} (Owner Verified)" if action == "CONTINUE" else f"● {action}",
                fg=col, bg=bg_col, highlightbackground=border_col
            )

            # Update Instant Match & Model Info
            self.db_instant_val.configure(text=f"{instant:.1f}%", fg=col)
            model_src = state_data.get("model_source", "CalibratedKeyboard")
            kb_cnt = state_data.get("keyboard_events", 0)
            self.db_model_source_lbl.configure(text=f"Source: {model_src} • {kb_cnt} events recorded")

            # Update 4 Biometric Metric Tiles
            dwell = state_data.get("dwell_mean_ms")
            flight = state_data.get("flight_mean_ms")
            speed = state_data.get("typing_speed")
            context = state_data.get("context", "General")
            app_n = state_data.get("app_name", "Desktop")

            self.db_dwell_val.configure(text=f"{dwell:.1f} ms" if dwell is not None else "— ms")
            self.db_flight_val.configure(text=f"{flight:.1f} ms" if flight is not None else "— ms")
            self.db_speed_val.configure(text=f"{speed:.1f} keys/s" if speed is not None else "— keys/s")
            self.db_context_val.configure(text=str(context))
            self.db_app_val.configure(text=f"Window: {app_n}")

            # Update Live AI Feature Attribution
            impact_lines = state_data.get("impact_lines", [])
            for idx, row_lbl in enumerate(self.db_attr_rows):
                if idx < len(impact_lines):
                    line_txt = impact_lines[idx]
                    if "🚨" in line_txt:
                        fg_c = CleanTheme.DANGER
                    elif "⚠️" in line_txt:
                        fg_c = CleanTheme.WARNING
                    elif "🟢" in line_txt:
                        fg_c = CleanTheme.SUCCESS
                    else:
                        fg_c = CleanTheme.TEXT_SECONDARY
                    row_lbl.configure(text=line_txt, fg=fg_c)
                else:
                    row_lbl.configure(text="", fg=CleanTheme.TEXT_MUTED)

            # Update System Tray Icon
            self.tray_manager.update_status(trust, action, is_snoozed=bool(state_data.get("snoozed", False)))

        elif not self.is_service_running:
            # Service paused / offline
            self.db_trust_val.configure(text="Paused", fg=CleanTheme.TEXT_MUTED)
            self.db_instant_val.configure(text="—", fg=CleanTheme.TEXT_MUTED)
            self.db_status_pill.configure(
                text="○ Protection Paused", fg=CleanTheme.DANGER,
                bg=CleanTheme.DANGER_BG, highlightbackground=CleanTheme.DANGER_BORDER
            )
            self.db_dwell_val.configure(text="— ms")
            self.db_flight_val.configure(text="— ms")
            self.db_speed_val.configure(text="— keys/s")
            self.db_attr_rows[0].configure(
                text="ℹ️ Protection service is paused. Click 'Start Guard' to resume continuous authentication.",
                fg=CleanTheme.TEXT_MUTED
            )
            for r in self.db_attr_rows[1:]:
                r.configure(text="")
            self.tray_manager.update_status(0.0, "PAUSED", is_snoozed=False)
        else:
            # Service running, awaiting first keystrokes
            self.db_status_pill.configure(
                text="● Monitoring Ready", fg=CleanTheme.SUCCESS,
                bg=CleanTheme.SUCCESS_BG, highlightbackground=CleanTheme.SUCCESS_BORDER
            )
            self.db_attr_rows[0].configure(
                text="ℹ️ Continuous protection active — type or move pointer to verify identity.",
                fg=CleanTheme.TEXT_SECONDARY
            )

        # 3. Bluetooth Status Update
        try:
            score, conn, walk_away = self.bluetooth_monitor.get_status()
            if self.bluetooth_monitor.target_mac:
                self.dev_target_mac.configure(text=f"MAC: {self.bluetooth_monitor.target_mac}")
                if conn or prox > 0.0:
                    if self.bluetooth_monitor.last_rssi is not None:
                        rssi_val = self.bluetooth_monitor.last_rssi
                        bars = 5 if rssi_val >= -65 else (4 if rssi_val >= -75 else (3 if rssi_val >= -85 else 2))
                        status_str = f"Nearby • Signal: {rssi_val} dBm (Passive Proximity)"
                    else:
                        bars = 4 if prox >= 0.7 else (3 if prox >= 0.4 else 2)
                        status_str = f"Nearby • Proximity: {int(prox * 100)}% (Radio Presence)"
                    self.dev_meter.set_strength(bars)
                    self.dev_conn_status.configure(text=status_str, fg=CleanTheme.SUCCESS)
                else:
                    self.dev_meter.set_strength(0)
                    self.dev_conn_status.configure(text="Out of Range / Asleep", fg=CleanTheme.DANGER)
        except Exception:
            pass

    # =========================================================================
    # ACTIONS & CONTROLS
    # =========================================================================
    def toggle_guard_service(self):
        """Starts or stops background C++ and Python receiver services."""
        if self.is_service_running:
            subprocess.run(["bash", str(ROOT_DIR / "stop.sh")], cwd=str(ROOT_DIR))
        else:
            subprocess.run(["bash", str(ROOT_DIR / "start.sh")], cwd=str(ROOT_DIR))
        self.after(600, self._poll_system_state)

    def trigger_manual_lock(self):
        """Immediately locks workstation screen."""
        if self.simulate_lock:
            messagebox.showinfo(
                "Simulation Mode",
                "Lock workstation requested, but system is currently in Simulation Mode.\n\n"
                "To enable actual screen locking, switch mode to 'Active Enforcement' in Settings."
            )
        else:
            ok, reason = lock_workstation()
            if not ok:
                messagebox.showwarning("Lock Failed", f"Could not lock screen: {reason}")

    def quick_snooze(self, minutes: int):
        """Snoozes automated lockouts for lending PC."""
        self.policy_store.enable_snooze(minutes)
        messagebox.showinfo("Protection Snoozed", f"Automated lockouts snoozed for {minutes} minutes.")
        self._poll_system_state()

    def cancel_snooze(self):
        """Resumes active monitoring immediately."""
        self.policy_store.clear_snooze()
        messagebox.showinfo("Protection Resumed", "Snooze cleared. Active monitoring is now enforcing protection.")
        self._poll_system_state()

    def reset_trust_score(self):
        """Resets the Wald SPRT hypothesis accumulator back to 100% genuine owner state."""
        for path in (RESET_TRIGGER_PATH, LEGACY_RESET_TRIGGER_PATH):
            try:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(str(time.time()), encoding="utf-8")
            except OSError:
                pass
        self.last_trust = 100.0
        self.db_trust_val.configure(text="100.0%", fg=CleanTheme.SUCCESS)
        self.db_trust_bar.set_pct(100.0)
        messagebox.showinfo("Trust Reset", "Evidence accumulator reset to 100% genuine owner baseline.")

    def on_mode_toggled(self):
        """Switches between simulation and enforcement modes."""
        sim = (self.set_sim_var.get() == 1)
        self.simulate_lock = sim
        set_lock_mode("simulate" if sim else "enforce")
        self._poll_system_state()

    def save_policy_settings(self):
        """Persists sensitivity and threshold to policy.json."""
        sens = self.set_sens_var.get()
        thresh = self.set_thresh_var.get()
        self.policy_store.update(sensitivity=sens, warning_threshold=thresh)
        messagebox.showinfo("Settings Saved", f"Policy updated: Sensitivity={sens}, Alert Threshold={thresh}%")

    def add_excluded_app(self):
        val = self.excl_entry.get().strip().lower()
        if val:
            pol = self.policy_store.load()
            excl = pol.get("excluded_apps", [])
            if val not in excl:
                excl.append(val)
                self.policy_store.update(excluded_apps=excl)
                self.excl_listbox.insert("end", val)
                self.excl_entry.delete(0, "end")

    def remove_excluded_app(self):
        sel = self.excl_listbox.curselection()
        if sel:
            val = self.excl_listbox.get(sel[0])
            pol = self.policy_store.load()
            excl = [x for x in pol.get("excluded_apps", []) if x != val]
            self.policy_store.update(excluded_apps=excl)
            self.excl_listbox.delete(sel[0])

    # Bluetooth Operations
    def scan_bluetooth(self):
        for item in self.dev_table.get_children():
            self.dev_table.delete(item)

        def _do():
            devs = BluetoothProximityMonitor.scan_nearby_devices()
            def _apply():
                for d in devs:
                    status_text = "Connected" if d.get("connected") else "Available"
                    self.dev_table.insert("", "end", values=(d["name"], d["mac"], status_text))
            self.after(0, _apply)

        threading.Thread(target=_do, daemon=True).start()

    def pair_selected_device(self):
        sel = self.dev_table.selection()
        if not sel:
            messagebox.showwarning("Select Device", "Please select a device from the table to pair.")
            return
        vals = self.dev_table.item(sel[0], "values")
        name, mac = vals[0], vals[1]
        self.bluetooth_monitor.save_target_device(mac, name)
        self.dev_target_name.configure(text=name)
        self.dev_target_mac.configure(text=f"MAC: {mac}")
        messagebox.showinfo("Device Paired", f"Successfully paired {name} ({mac}) for walk-away lock.")

    def unpair_device(self):
        self.bluetooth_monitor.save_target_device("", "")
        self.dev_target_name.configure(text="No device paired")
        self.dev_target_mac.configure(text="Scan nearby devices below to pair your phone or smartwatch")
        self.dev_meter.set_strength(0)
        self.dev_conn_status.configure(text="Status: Unpaired", fg=CleanTheme.TEXT_MUTED)
        messagebox.showinfo("Unpaired", "Bluetooth target device cleared.")

    # Alert Settings Operations
    def detect_telegram_chat_id(self):
        """Auto-discovers the user's Chat ID by polling updates from their bot."""
        tok = self.tg_token_entry.get().strip()
        if not tok:
            messagebox.showwarning("Missing Token", "Please enter your Telegram Bot Token first.")
            return

        ok, updates = TelegramClient.get_updates(tok, offset=0, timeout=3)
        if not ok or not updates:
            messagebox.showinfo(
                "No Messages Found",
                "To detect your Chat ID:\n\n"
                "1. Open Telegram on your phone or computer.\n"
                "2. Search for your bot username and tap START (or send 'hi').\n"
                "3. Click this 'Auto-Detect' button again!"
            )
            return

        chat_id = None
        user_name = ""
        for u in reversed(updates):
            msg = u.get("message") or u.get("channel_post")
            if msg and "chat" in msg:
                chat_id = str(msg["chat"].get("id", ""))
                first_name = msg["chat"].get("first_name", "")
                user_name = msg["chat"].get("username", first_name)
                break
            cb = u.get("callback_query")
            if cb and "from" in cb:
                chat_id = str(cb["from"].get("id", ""))
                user_name = cb["from"].get("username", "")
                break

        if chat_id:
            self.tg_chat_entry.delete(0, tk.END)
            self.tg_chat_entry.insert(0, chat_id)
            account_display = f"@{user_name}" if user_name else "User"
            messagebox.showinfo(
                "Chat ID Detected!",
                f"Successfully detected your Chat ID: {chat_id} ({account_display})\n\n"
                f"Click 'Save Telegram Settings' to apply."
            )
        else:
            messagebox.showinfo(
                "Send Message First",
                "Please send any message (e.g. /start or 'hi') to your bot in Telegram first, then click Auto-Detect."
            )

    def save_telegram_settings(self):
        tok = self.tg_token_entry.get().strip()
        cid = self.tg_chat_entry.get().strip()
        en = self.tg_enabled_var.get()
        self.cred_store.update_telegram(tok, cid, en)
        messagebox.showinfo("Telegram Saved", "Telegram alert credentials updated.")

    def test_telegram_alert(self):
        tok = self.tg_token_entry.get().strip()
        cid = self.tg_chat_entry.get().strip()
        if not tok or not cid:
            messagebox.showwarning("Missing Credentials", "Enter a valid Telegram Bot Token and Chat ID first.")
            return
        ok, msg = TelegramClient.send_message(
            tok, cid, "🛡️ *Chronos-Auth Security Test*\n\nYour continuous behavioral biometric guard is active and operational."
        )
        if ok:
            messagebox.showinfo("Telegram Delivered", "Test alert message delivered successfully!")
        else:
            messagebox.showerror("Telegram Error", f"Delivery failed: {msg}")

    def save_email_settings(self):
        self.cred_store.update_smtp(
            host=self.em_host_entry.get().strip(),
            port=int(self.em_port_entry.get().strip() or 587),
            user=self.em_user_entry.get().strip(),
            recipient=self.em_rcpt_entry.get().strip(),
            enabled=self.em_enabled_var.get(),
            use_tls=True,
        )
        messagebox.showinfo("Email Saved", "SMTP email alert settings updated.")

    def test_email_alert(self):
        creds = self.cred_store.load().get("smtp", {})
        host = self.em_host_entry.get().strip()
        rcpt = self.em_rcpt_entry.get().strip()
        user = self.em_user_entry.get().strip()
        port = int(self.em_port_entry.get().strip() or 587)
        if not host or not rcpt:
            messagebox.showwarning("Missing Fields", "Enter an SMTP server host and recipient address.")
            return
        ok, msg = EmailClient.send_alert(
            host=host, port=port, user=user, password="", recipient=rcpt,
            subject="Chronos-Auth Test Alert",
            body="This is a test notification from your Chronos-Auth security engine.",
            use_tls=True,
        )
        if ok:
            messagebox.showinfo("Email Sent", "Test alert email sent successfully!")
        else:
            messagebox.showerror("Email Error", f"Failed to send email: {msg}")

    # Tray and Window Lifecycle
    def show_window_from_tray(self):
        self.after(0, self._restore_window)

    def _restore_window(self):
        self.deiconify()
        self.lift()
        self.focus_force()

    def on_close(self):
        """Minimizes to tray if supported, otherwise exits cleanly."""
        if getattr(self.tray_manager, "is_active", False):
            self.withdraw()
        else:
            self.quit_app()

    def quit_app(self):
        """Clean application shutdown."""
        self.is_running_app = False
        self.bluetooth_monitor.stop()
        self.tray_manager.stop()
        self.destroy()


def main():
    app = ChronosAuthApp()
    app.mainloop()


if __name__ == "__main__":
    main()
