# 🛡️ Behavior Authentication System

A continuous, behavior-based authentication system using keystroke dynamics and mouse telemetry. 

The system uses a highly optimized C++ engine to capture low-level Linux hardware inputs and publishes them over ZeroMQ to a Python machine-learning receiver. The Python engine extracts behavioral features, stores them in SQLite, and scores them in real-time against user-trained Anomaly Detection models (Isolation Forest).

---

## 🛠️ 1. Installation & Setup (Linux)

### 1.1 Install System Dependencies
```bash
sudo apt update
sudo apt install -y build-essential cmake pkg-config libevdev-dev libzmq3-dev cppzmq-dev python3 python3-venv
```

### 1.2 Build the C++ Event Engine
```bash
git clone https://github.com/2023abhisheksharma/behavior_auth.git
cd behavior_auth

mkdir -p event_engine/build
cd event_engine/build
cmake ..
make
cd ../..
```

### 1.3 Setup Python Machine Learning Environment
```bash
cd python_engine
python3 -m venv venv
source venv/bin/activate
pip install -r ../requirements.txt
cd ..
```

---

## 🚀 2. Running the System

You have two choices for running the data collection and inference pipeline: visually in the foreground, or invisibly in the background.

### Option A: Clean Background Service (Recommended)
We have a fully automated script that launches the C++ tracker and Python ML receiver seamlessly in the background.

1. **Start the service:**
   ```bash
   ./start_background.sh
   ```
2. **Watch the live AI predictions:**
   ```bash
   tail -f /tmp/behavior_python_receiver.log
   ```
3. **Stop the service:**
   ```bash
   sudo pkill -f event_engine && pkill -f "receiver.py"
   ```

### Option B: Manual Foreground Terminals (For Debugging)
Open two separate terminals:
* **Terminal 1 (Publisher):** `cd event_engine/build && sudo ./event_engine`
* **Terminal 2 (Receiver):** `cd python_engine && source venv/bin/activate && python receiver.py`

---

## 🧠 3. Training the AI

The AI starts out completely empty and passively learns your habits. You should retrain the system periodically so it gets smarter at recognizing you.

* **Phase 1 (1 Hour):** After 1-2 hours of usage (around 100-200 frames), run the training pipeline to generate the global models.
* **Phase 2 (End of Day):** After compiling ~500+ frames, retraining will generate Context-Aware Models (specific AIs for when you are typing vs when you are using the mouse).

### How to Train:
Run the automated pipeline to compile your SQLite data, build the Sklearn models, and verify feature weights:

**Linux:**
```bash
./run_pipeline.sh
```

**Windows:**
```powershell
.\run_pipeline.ps1
```

---

## 🕵️ 4. Importing Impostor Data (For Friends/Teammates)

When you are ready to train Deep Learning classifiers (like LightGBM), you need real data from other humans ("impostors"). Rather than lending them your laptop, they can run this system on theirs!

1. Have your friend clone this repo and run `./start_background.sh` on their Linux machine for a few hours.
2. Have them send you their `python_engine/behavior_data.db` file.
3. Save their database file to your machine (e.g., `~/Downloads/friend_db.db`).
4. Run the remote import tool. It will selectively strip their database IDs, forcefully label all their telemetry as `impostor`, and merge it directly into your live master DB.
   
   **Linux:**
   ```bash
   cd python_engine
   source venv/bin/activate
   python import_impostor_db.py ~/Downloads/friend_db.db
   ```

   **Windows:**
   ```powershell
   cd python_engine
   .\venv\Scripts\Activate.ps1
   python import_impostor_db.py C:\Users\Downloads\friend_db.db
   ```

---

## 🪟 Windows Support (Analysis Only)

*Note: The C++ `event_engine` reads low-level `/dev/input/*` events, which is structurally specific to the Linux Kernel. Therefore, live data collection only runs on Linux.*

However, you can clone the repository on a Windows machine to run data analytics, view data, and train models using data compiled from Linux.

1. **Setup:**
   ```powershell
   python -m venv python_engine\venv
   python_engine\venv\Scripts\Activate.ps1
   pip install -r requirements.txt
   ```
2. **Train/Analyze:**
   ```powershell
   .\run_pipeline.ps1
   ```

---

## ⚙️ Systemd Persistent Daemon (Advanced Linux)
To make the system launch globally on boot without needing to open a terminal:
1. `sudo nano /etc/systemd/system/behavior_auth.service`
2. Configure it:
   ```ini
   [Unit]
   Description=Behavior Authentication Security Service
   After=network.target

   [Service]
   Type=simple
   User=root
   WorkingDirectory=/path/to/behavior_auth
   ExecStart=/path/to/behavior_auth/start_background.sh
   Restart=on-failure
   RestartSec=5

   [Install]
   WantedBy=multi-user.target
   ```
3. Enable it: `sudo systemctl daemon-reload && sudo systemctl enable behavior_auth.service && sudo systemctl start behavior_auth.service`

