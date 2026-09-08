# 🛡️ Chronos-Auth: Continuous Behavioral Biometrics Suite

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](https://opensource.org/licenses/MIT)
[![Python: 3.10+](https://img.shields.io/badge/Python-3.10+-brightgreen.svg)](https://www.python.org/)
[![C++: 17](https://img.shields.io/badge/C++-17-blue.svg)](https://isocpp.org/)
[![Status: Research Grade](https://img.shields.io/badge/Status-Research%20Grade%20(2026)-gold.svg)]()

**Chronos-Auth** is a research-grade continuous authentication suite for workstations. It scores measured keyboard dynamics and, when available, measured mouse kinematics. Shortcut and Bluetooth telemetry are displayed separately and are not treated as biometric proof unless a trained model explicitly supports them.

The system uses a calibrated owner/impostor classifier followed by a Wald Sequential Probability Ratio Test (SPRT). Deployment error rates are not claimed until measured on representative real data.

---

## 🌟 Key Breakthrough Capabilities

### 1. ⚡ Dual-Horizon Biometric Inference
* **Sub-Second Fast-Path**: Analyzes ballistic mouse movement strokes and key digraph intervals every **1.5 seconds**, instantly flagging anomalies.
* **Macro Slow-Path (Wald's SPRT)**: Accumulates evidence across live samples; lockout latency and error rates require empirical validation for the target workstation and user.

### 2. 🖱️ Ballistic Mouse Kinematics & Bézier Profiling
* **Jerk Minimization**: Measures root-mean-square jerk ($\text{m/s}^3$) representing human motor control fluidity.
* **Trajectory Tortuosity**: Computes the ratio of actual cursor path length to Euclidean distance ($\text{Length} / \text{Distance}$).
* **Hand-Transition Latency (HTL)**: Profiles the subconscious neuromuscular delay between releasing the keyboard and moving the mouse.

### 3. ⌨️ Dynamic Open-Vocabulary Shortcut Profiler
* **No Hardcoded Keys**: Automatically learns **any** keyboard shortcut or custom hotkey the user presses (e.g. `Ctrl+C`, `Alt+Tab`, custom IDE/editor commands, Blender/Vim key sequences).
* **Muscle Memory Lead-Time**: Measures the precise microsecond interval between pressing modifier keys and character keys.
* **Persistent Habit Profile**: Saves your personal shortcut dictionary to `shortcuts_profile.json` for telemetry and inspection; shortcut heuristics are not added to the authentication LLR.

### 4. 📱 Bluetooth Phone Proximity (The Walk-Away Lock)
* Passively monitors the Bluetooth RSSI signal strength of your paired smartphone or smartwatch in the background.
* **Walk-Away Auto Lock**: Locks the workstation within 1 second if you walk away with your phone (RSSI $< -85\text{ dBm}$ or disconnected).
* **Fatigue Baseline Cushion**: When your phone is present, baseline trust is bolstered to eliminate false rejections during relaxed typing.

### 5. 🚨 Hardware Anti-Bot & BadUSB / Rubber Ducky Interceptor
* Automatically detects automated keystroke injectors (USB Rubber Ducky, Flipper Zero BadUSB, software macro scripts).
* Flags mathematically zero-jitter key dwell times ($\sigma < 2.5\text{ms}$ vs. human $\sigma \ge 15\text{ms}$), superhuman typing speeds ($> 25\text{ chars/s}$), and robotic straight-line cursor movement ($\text{tortuosity} = 1.0000$).

### 6. 🗔 Dedicated Native Desktop Application (Zero-Code / No-Browser)
* Comes with a native desktop application window (CustomTkinter, dark mode, responsive layout).
* **100% Offline**: No browser tabs, no web URLs, no cloud dependencies.
* Includes a **3-Step First-Run Onboarding Wizard** that guides non-technical users from passive learning to full AI arming.

---

## 🚀 Quick Start & Installation

### Option A: One-Click Automated Setup (Recommended)

#### On Linux:
```bash
git clone https://github.com/2023abhisheksharma/behavior_auth.git
cd behavior_auth
./setup.sh
```
* Automatically installs required system libraries (`libevdev-dev`, `cmake`, `libzmq3-dev`).
* Builds the C++ hardware engine and sets up the Python virtual environment.
* Generates a native **Chronos Auth** desktop icon on your Desktop and Applications Menu.
* Launches the dedicated desktop app window immediately!

#### On Windows:
1. Double-click `setup_windows.bat`.
2. It sets up the environment and creates a **Chronos-Auth** desktop shortcut.
3. Launches the dedicated desktop window automatically.

---

### Option B: Standalone Portable Binary (No Python Needed)
You can run the pre-compiled standalone native binary directly without installing Python, pip, or any packages:
```bash
./dist/chronos-auth/chronos-auth
```

---

## 🖥️ Using the Dedicated Desktop Application

Launch the desktop suite at any time by running:
```bash
./app.sh
```
*(Or by double-clicking the **Chronos Auth** icon on your Desktop).*

```text
┌────────────────────────────────────────────────────────────────────────────────────────┐
│  Chronos-Auth 🛡️ Continuous Biometrics Hub                                    —  □  ✕  │
├───────────────────┬────────────────────────────────────────────────────────────────────┤
│  CHRONOS-AUTH     │  Live Security Dashboard                                           │
│  Zero-Trust       │  ┌───────────────────────────────┐ ┌─────────────────────────────┐ │
│                   │  │ CONTINUOUS TRUST SCORE        │ │ ACTIVE TASK & STATE         │ │
│  [🛡️  Live State]  │  │                               │ │ Context: Coding / IDE       │ │
│  [📱  Phone Pair]  │  │              100%             │ │ Wald SPRT LLR: -4.60 (Safe) │ │
│  [⌨️  Shortcuts]   │  │                               │ │ Rate: Sub-second (1.5s)     │ │
│  [📊  Telemetry]  │  │  🟢 [CONTINUE] AUTHENTICATED   │ │                             │ │
│  [⚙️  Settings]   │  └───────────────────────────────┘ └─────────────────────────────┘ │
│                   │                                                                    │
│  ───────────────  │  SYSTEM PROTECTION LOG                                             │
│  ● Status: ACTIVE │  ┌───────────────────────────────────────────────────────────────┐ │
│  [⏹ Stop Guard]  │  │ [Chronos-Auth] Hardware event engine and AI scoring active.   │ │
│                   │  │ [Chronos-Auth] Wald SPRT: Owner verified.                     │ │
│                   │  └───────────────────────────────────────────────────────────────┘ │
└───────────────────┴────────────────────────────────────────────────────────────────────┘
```

* **🛡️ Live Security**: Real-time 0–100% trust gauge, active task context, and live decision streaming.
* **📱 Phone Pairing**: 1-Click "Scan Nearby Phones & Watches", pair device for Walk-Away auto-lock.
* **⌨️ Dynamic Shortcuts**: View discovered keyboard shortcuts and individual muscle-memory intervals.
* **📊 Telemetry & AI Model**: View total collected samples and trigger **1-Click AI Retraining**.
* **⚙️ Settings**: Toggle Simulation Mode vs Real Lock Mode, adjust sensitivity (Relaxed / Balanced / Strict).

---

## 🤖 Headless / Background Service Management

For headless servers or users who prefer invisible background execution:

```bash
# Start background hardware capture and AI inference
./start.sh

# Watch live AI decision stream
tail -f /tmp/behavior_python_receiver.log

# Gracefully stop all background services
./stop.sh
```

---

## 🧠 Model Training & Architecture

### Architectural Pipeline
```text
Hardware Event Stream (Linux /dev/input or Windows RawInput)
        ↓
High-Performance C++ Event Engine (Poll loop, microsecond timestamps)
        ↓
IPC Bus (ZeroMQ IPC / TCP Socket)
        ↓
Python Chronos-Auth Engine:
  ├── ContextDetector (Classifies active window: IDE, Terminal, Browser, Documents, Chat)
  ├── StrokeAnalyzer (Ballistic mouse paths, Bézier tortuosity, jerk RMS, HTL)
  ├── NgramAnalyzer (Neuromuscular key dwell, cross-hand flight, legato overlap)
  ├── ChordAnalyzer (Dynamic shortcut telemetry, not model evidence)
  ├── AntiBotDetector (Zero-jitter Rubber Ducky & BadUSB injection interceptor)
  └── BluetoothProximityMonitor (Phone RSSI walk-away auto-lock)
        ↓
Measured behavioral feature vector
        ↓
Calibrated owner/impostor keyboard classifier
        ↓
Measured mouse one-class profile when enough real mouse samples exist
        ↓
Wald's Sequential Probability Ratio Test (SPRT)
        ↓
Decision Enforcement: High Trust ──► Step-Up MFA Challenge ──► Workstation Lock
```

### Manual Retraining Pipeline
To retrain the Chronos-Auth model:
```bash
# Import the real CMU benchmark as labeled external impostor data first.
python_engine/venv/bin/python python_engine/import_public_keystroke.py /path/to/DSL-StrongPasswordData.csv

python_engine/venv/bin/python python_engine/run_full_pipeline.py
```
The importer records public dataset provenance and never synthesizes or perturbs impostor rows. Missing telemetry remains missing. Live observations are stored as `unverified_live` and are not used for training until explicitly reviewed. Mouse scoring stays disabled until real measured mouse samples are available.

---

## 📁 Repository Structure

```text
behavior_auth/
├── app.sh                         # Native desktop application launcher
├── app_windows.bat                # Windows native desktop launcher
├── setup.sh                       # One-click Linux automated installer
├── setup_windows.bat              # One-click Windows automated installer
├── package_app.sh                 # PyInstaller standalone bundler
├── start.sh                       # Background service starter
├── stop.sh                        # Background service stopper
├── requirements.txt               # Machine learning & GUI dependencies
├── dist/
│   └── chronos-auth/              # Portable standalone binary (runs with zero dependencies)
├── event_engine/                  # C++ hardware event capture engine
│   ├── CMakeLists.txt
│   └── src/
│       ├── EventEngine.cpp        # Linux libevdev capture (keys, mouse, clicks, wheel)
│       └── EventEngine_Windows.cpp# Windows RawInput capture
└── python_engine/                 # Machine learning & inference suite
    ├── desktop_app.py             # Dedicated Tk desktop application
    ├── app_server.py              # Live HTTP dashboard server
    ├── receiver.py                # ZeroMQ telemetry receiver
    ├── event_processor.py         # Hardware event dispatcher
    ├── behavior_data.db           # Master SQLite biometric telemetry store
    ├── shortcuts_profile.json     # Dynamically learned personal shortcut memory
    ├── bluetooth_config.json      # Paired phone device configuration
    └── chronos_auth/              # Next-generation multi-modal biometric package
        ├── bluetooth_proximity.py # Bluetooth RSSI phone walk-away monitor
        ├── chord_analyzer.py      # Open-vocabulary shortcut muscle memory engine
        ├── antibot_detector.py    # Hardware BadUSB / Rubber Ducky interceptor
        ├── stroke_analyzer.py     # Ballistic mouse kinematics & Bézier tortuosity
        ├── ngram_analyzer.py      # Neuromuscular key timing & hand-transition
        ├── context_detector.py    # Active desktop application classification
        ├── chronos_features.py    # 26-dimensional multi-modal vector assembler
        ├── contrastive_model.py   # Calibrated classifier + measured mouse profile
        ├── sprt_trust_engine.py   # Wald's Sequential Probability Ratio Test
        └── realtime_pipeline.py   # Live sub-second inference engine
```

---

## 📜 Validation Status

| Metric | Current status |
| :--- | :--- |
| **Held-out AUC** | Reported only for imported labeled rows; not a deployment guarantee |
| **Mouse model** | Disabled until real measured mouse samples are collected |
| **Impostor lockout latency / EER / FRR** | Not established empirically |
| **Bluetooth proximity** | Disabled unless a real configured device reports connected |

---

## 📄 License
MIT License. Open-source for academic research and personal security.
