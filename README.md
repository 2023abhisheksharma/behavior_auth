# 🛡️ Behavior Authentication System

A continuous, behavior-based authentication system using keystroke dynamics and mouse telemetry. 

The system uses a highly optimized C++ engine to capture hardware inputs and publishes them over ZeroMQ to a Python machine-learning receiver. The Python engine extracts behavioral features, stores them in SQLite, and scores them in real-time against user-trained Anomaly Detection models (Isolation Forest).

---

## 🧩 WINDOWS SETUP (FULL STEPS FROM ZERO)

### 1. Install Required Software

**1.1 Install Python**
* Download: [Python](https://www.python.org/downloads/)
* During install:
  * ✔ Add to PATH
  * ✔ Install pip
* Verify: `python --version`

**1.2 Install Visual Studio (for C++)**
* Download: [Visual Studio](https://visualstudio.microsoft.com/)
* Select workload: **Desktop development with C++**

**1.3 Install ZeroMQ (C++ + Python)**
*C++ side:*
Use `vcpkg`:
```cmd
git clone https://github.com/microsoft/vcpkg
cd vcpkg
bootstrap-vcpkg.bat
vcpkg install zeromq:x64-windows
vcpkg install cppzmq:x64-windows
vcpkg integrate install
```

*Python side:*
```cmd
pip install pyzmq
```

**1.4 Install Python Libraries**
```cmd
pip install numpy scikit-learn joblib matplotlib
```

**1.5 Install SQLite Tools**
* Download: [DB Browser for SQLite](https://sqlitebrowser.org/)
* Used for: Viewing collected data and verifying features.

---

## ⚙️ 2. BUILD C++ EVENT ENGINE (WINDOWS)

**Steps:**
1. Open Visual Studio.
2. Create a Console Application.
3. Add your `.cpp` and `.hpp` files (including `EventEngine_Windows.cpp`).
4. Link ZeroMQ (via vcpkg auto-integration).
5. Build: `Build → Build Solution`.
**Output:** `event_engine.exe`

---

## ▶️ 3. RUN SYSTEM (ORDER IS IMPORTANT)

### Step 1: Start C++ Event Engine
```cmd
event_engine.exe
```
*Expected Output:*
```
Windows Event Engine (Raw Input) Starting...
Listening for global Windows input...
```

### Step 2: Start Python Receiver
```cmd
cd python_engine
python receiver.py
```
*Expected Output:*
```
Listening...
```

---

## 🧠 4. DATA COLLECTION

**What you do:** Type normally, move the mouse, use the system normally.
**System will:** → capture events → extract features → store in SQLite

---

## 🗄️ 5. VERIFY DATA (IMPORTANT STEP)

1. Open **DB Browser for SQLite**.
2. Open file: `behavior_data.db`.
3. Check the `features` table.
4. You should see: `mean_dwell`, `typing_speed`, `velocity`, etc.

---

## 🧠 6. TRAIN & EVALUATE MODELS

**Train Model:**
```cmd
python train_iforest.py
```

**Test Model:**
```cmd
python test_iforest.py
```

**Analyze Scores:**
```cmd
python analyze_scores.py
```

**Evaluate Model (FAR, FRR, EER):**
```cmd
python evaluate_model.py
```

---

## 🔁 FULL PIPELINE ARCHITECTURE

```text
C++ Raw Input (Windows) / libevdev (Linux)
        ↓
      ZeroMQ
        ↓
  Python Receiver
        ↓
  Event Processor
        ↓
  Feature Engine
        ↓
    SQLite DB
        ↓
IsolationForest Model
        ↓
    Trust System
        ↓
  Decision Output
```

---

## 🐧 LINUX SETUP (QUICK START)

If you are running this natively on Linux (like Arch/Ubuntu):

**1. Install Dependencies:**
```bash
sudo apt update
sudo apt install -y build-essential cmake pkg-config libevdev-dev libzmq3-dev cppzmq-dev python3 python3-venv
```

**2. Build C++ Engine:**
```bash
mkdir -p event_engine/build && cd event_engine/build
cmake ..
make
```

**3. Setup Python Engine & Run Background Service:**
```bash
cd ../../python_engine
python -m venv venv
source venv/bin/activate
pip install -r ../requirements.txt
cd ..
./start_background.sh
```

---

## ⚠️ COMMON ISSUES

❌ **Mouse data = 0**
* **Cause:** Raw Input not capturing / Wrong device usage.
* **Fix:** Ensure `WM_INPUT` correctly handled, verify `dx/dy` values.

❌ **Database resets**
* **Cause:** Path mismatch.
* **Fix:** Use absolute DB paths everywhere.

❌ **Model mismatch**
* **Cause:** Feature count mismatch.
* **Fix:** Train again after feature changes.

