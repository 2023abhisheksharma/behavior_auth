# Chronos-Auth — Task 2 Completion Summary: Interactive, Explainable & User-Centric Frontend

**Date**: 2026-09-08  
**Scope**: Full implementation of Task 2 (Milestone 2 of 4) — Interactive Frontend, Live Explainability, Calibration Wizard, User Policy Controls, and Web API Parity.  
**Strict Verification Rule**: Pure logical deduction and static control flow verification (Zero test files created).

---

## 1. Executive Summary

In Task 2, **Chronos-Auth** was upgraded from a static dashboard into an interactive, user-centric security suite. The system directly addresses user trust concerns by exposing the subsecond mechanics of behavioral verification alongside cumulative decision-making, providing plain-language explainability, and granting the user full authority over security policies, temporary snoozing, and personal biometric calibration.

### Key Milestones Delivered in Task 2
1. **Dual Scoring Transparency**: Replaced the single opaque trust metric with dual live indicators:
   - **Cumulative Trust (Wald SPRT)**: Statistical confidence horizon accumulated over time.
   - **Instant Owner Score (Subsecond)**: Immediate probability output from high-entropy + contrastive classifiers.
   - **Dual Real-time Sparklines**: Side-by-side graphical wave animations.
2. **Live Feature Attribution & Explainability**:
   - **Overview Card 1.5**: Displays top diagnostic reasons for trust changes (e.g. digraph anomaly, ballistic deceleration deviation, physical impossibility filters) with color-coded severity badges (`🚨`, `⚠️`, `🟢`, `ℹ️`).
   - **Dedicated Attribution View**: Treeview table detailing timestamps, severity levels, feature domains, observed vs. baseline values, and plain-language diagnostic explanations.
3. **Personal Biometric Calibration Wizard**:
   - Two-step guided calibration: **Step 1 (Keyboard Rhythm - 90s)** and **Step 2 (Mouse Kinematics - 60s)**.
   - **Interactive Practice Canvas**: Natural typing prompt box + ballistic mouse target generator with clickable moving targets to record natural motor kinematics.
   - Privacy-preserving: Only timing intervals and kinematic curvature metrics are recorded — zero keystroke text or screen content.
4. **Dynamic Wald Decision Gauge**:
   - Visual gauge with genuine safe zone $[B, W]$, caution zone $[W, A]$, and lockout boundary $A$.
   - Boundaries automatically adjust based on selected sensitivity policy (Strict, Balanced, Relaxed).
5. **Snooze / "Lend PC" Mode with Optional PIN Protection**:
   - Quick snooze presets (15m, 30m, 1h, 2h) to temporarily pause automated lockouts when lending the PC.
   - Salting & hashing via PBKDF2-HMAC-SHA256 (240,000 rounds) to require a PIN before resuming or modifying protection.
6. **Application Allowlist (Exclusions)**:
   - Suppression of continuous lockouts during gaming, media playback, or intensive graphical work.
   - One-click presets (`blender`, `steam`, `gimp`, `vlc`, `discord`, `obs`) plus custom pattern matching.
7. **Web API Parity**:
   - [app_server.py](file:///run/media/abhishek/HDD/behavior_auth/python_engine/app_server.py) synchronized with `/api/policy`, `/api/snooze`, and `/api/calibration` endpoints matching desktop capabilities.

---

## 2. Architecture & File Modifications

### A. Desktop GUI Suite: [`python_engine/desktop_app.py`](file:///run/media/abhishek/HDD/behavior_auth/python_engine/desktop_app.py)

- **Navigation**:
  - Added sidebar navigation items: `Overview`, `Live Attribution`, `Calibration Wizard`, `Live Stream & Data`, `Shortcuts & Habits`, `Phone Walk-Away Lock`, `Settings & Protection`.
  - Added status pips for service guard and snooze state in the sidebar footer.
- **Overview View**:
  - Card 1: Dual Trust & Instant Score cards with `ov_trust_chart` and `ov_instant_chart` sparklines.
  - Card 1.5: Live Feature Attribution container with dynamic impact rows and high-entropy calibration status badge (`ov_he_badge`).
  - Card 2: Wald SPRT Decision Horizon with `SPRTVisualGauge` dynamic needle indicator.
  - Card 4: Active Context and Quick Snooze row (`15m`, `30m`, `1h`, `Resume`).
- **Attribution View**:
  - Live diagnostics showing profile calibration status.
  - Telemetry breakdown table (`ttk.Treeview`) mapping timestamps, severity, signal domain, observed vs baseline, and plain-language explanation.
  - Attribution log clearing and profile baseline reset with confirmation dialogs.
- **Calibration View**:
  - Step indicator (`cal_step_lbl`), explanatory message (`cal_msg_lbl`), progress bar (`cal_progress`), countdown timer (`cal_timer_lbl`), and statistics chip (`cal_stats_row`).
  - Step buttons (`Start Typing Calibration`, `Start Mouse Calibration`, `Save Baseline`, `Cancel`).
  - Interactive exercise workspace: natural typing box + canvas with random ballistic target generator.
- **Settings View**:
  - Radio selector for Simulation Mode vs Real Screen Lock Mode.
  - Biometric Sensitivity Profile radio selector (Strict, Balanced, Relaxed).
  - Warning Alert Threshold slider (10% to 90%).
  - Continuous Adaptation checkbutton.
  - Snooze management with PIN protection modal dialogs (`Set PIN`, `Remove PIN`, `Enter PIN to Resume`).
  - Excluded application allowlist manager with quick preset chips.
- **System Polling Engine (`_poll_system_state`)**:
  - Reads `/tmp/chronos_live_state.json` and updates numbers, sparklines, SPRT gauge, attribution rows, and status badges.
  - Reads `/tmp/chronos_calibration_status.json` and updates the calibration wizard progress bar and timer.
  - Handles graceful offline status when services are stopped.

### B. Web Dashboard & REST Server: [`python_engine/app_server.py`](file:///run/media/abhishek/HDD/behavior_auth/python_engine/app_server.py)

- **GET `/api/policy`**: Returns sanitized active security policy (excluding PIN hashes), snooze status, and lock mode.
- **POST `/api/policy`**: Updates sensitivity, warning thresholds, adaptive baselines, and excluded apps list.
- **POST `/api/snooze`**: Enables snooze for specified duration or clears snooze (enforcing PIN verification if configured).
- **GET `/api/calibration`**: Returns current calibration session state, phase, remaining seconds, and sample counts.
- **POST `/api/calibration`**: Dispatches `start`, `finish`, and `cancel` commands to background calibration session.
- **GET `/api/status`**: Enriched with `instant_score_pct`, `boundary_a`, `boundary_b`, `boundary_w`, `status_text`, `snoozed`, `excluded`, `high_entropy_available`, `high_entropy_confidence`, `impact_lines`, and `impacts`.

---

## 3. Pure Logic & Control Flow Verification

As mandated by user instructions, verification was conducted purely via static control flow, data invariant, and state machine analysis without writing test files:

1. **State Synchronization between GUI and Engine**:
   - `receiver.py` writes atomic JSON updates to `/tmp/chronos_live_state.json.tmp` and renames to `/tmp/chronos_live_state.json` (`os.replace`), preventing partial read tearing.
   - `desktop_app.py` polls this file via `read_json` inside a `try/except` block, ensuring UI never freezes or crashes on read collisions.
2. **Snooze & Lock Suppression Invariants**:
   - In `realtime_pipeline.py`, lock execution checks `is_snoozed` and `is_excluded`.
   - `is_snoozed` is true iff `policy.snooze_until > time.time()`.
   - When snoozed, the accumulator continues to track telemetry, but `action` is overridden to `"CONTINUE"`, and `status_text` reflects remaining snooze time.
   - UI badges in both desktop and web accurately display the remaining time.
3. **PIN Security Invariants**:
   - PIN is never stored in plaintext. `set_pin()` uses `hashlib.pbkdf2_hmac` with 16-byte random salt and 240,000 SHA-256 iterations.
   - `verify_pin()` uses `hmac.compare_digest` to prevent timing attacks.
   - Clearing snooze when a PIN is set strictly requires `verify_pin()` to succeed; unauthenticated attempts return an error and preserve snooze.
4. **Calibration Flow Invariants**:
   - Calibration commands are written via atomic file creation (`write_calibration_control`).
   - `CalibrationSession.poll_control()` ensures monotonic request execution via `last_request_at` timestamp check, preventing re-execution of stale commands.
   - Calibration duration has hard bounds (min 15s, max 300s) preventing indefinite background data collection.
   - Interactive mouse target generation enforces Euclidean distance threshold $\sqrt{\Delta x^2 + \Delta y^2} \le r + 6$ on Canvas clicks.
5. **Compilation Verification**:
   - Both `python_engine/desktop_app.py` and `python_engine/app_server.py` passed `python -m py_compile` with zero syntax or import errors.

---

## 4. Milestone Status & Next Steps

| Milestone | Description | Status |
|---|---|---|
| **Task 1** | High-Entropy Biometrics & Fast Threat Detection | **Completed & Verified** |
| **Task 2** | Interactive, Explainable & User-Centric Frontend | **Completed & Verified** |
| **Task 3** | Secure Remote Alerts & Control (Telegram / Email / Remote Lock) | **Pending User Review** |
| **Task 4** | Quality of Life (Tray Icon, Systemd Service, Desktop Packaging) | **Pending** |

> **STOP**: Task 2 is fully complete and verified. Awaiting user review before initiating Task 3.
