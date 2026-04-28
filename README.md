# Behavior Authentication System

Behavior-based authentication using keyboard + mouse telemetry.

- C++ event publisher captures Linux input events and publishes over ZeroMQ.
- Python receiver extracts features and stores them in SQLite.
- Global and context-aware anomaly models are trained for realtime trust decisions.

## Repository Layout

- `event_engine/`: Linux C++ input capture and ZeroMQ publisher.
- `python_engine/`: feature extraction, database, training, realtime inference.
- `requirements.txt`: all Python dependencies for this project.
- `run_pipeline.sh`: one-command pipeline runner (Linux/macOS shell).
- `run_pipeline.ps1`: one-command pipeline runner (Windows PowerShell).

## First-Time Clone Setup

## Linux

```bash
git clone https://github.com/2023abhisheksharma/behavior_auth.git
cd behavior_auth

sudo apt update
sudo apt install -y build-essential cmake pkg-config libevdev-dev libzmq3-dev cppzmq-dev python3 python3-venv

python3 -m venv python_engine/venv
source python_engine/venv/bin/activate
pip install -r requirements.txt

cmake -S event_engine -B event_engine/build
cmake --build event_engine/build
```

## Windows (training/analysis)

```powershell
git clone https://github.com/2023abhisheksharma/behavior_auth.git
cd behavior_auth

python -m venv python_engine\venv
python_engine\venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

Then run:

```powershell
.\run_pipeline.ps1
```

## Daily Run Sequence

## Linux live capture + scoring

1. Terminal A (publisher):

```bash
cd /path/to/behavior_auth/event_engine/build
sudo ./event_engine
```

2. Terminal B (receiver):

```bash
cd /path/to/behavior_auth
source python_engine/venv/bin/activate
python python_engine/receiver.py
```

3. After session, retrain models:

```bash
./run_pipeline.sh
```

## Windows daily training/analysis

```powershell
cd C:\path\to\behavior_auth
python_engine\venv\Scripts\Activate.ps1
.\run_pipeline.ps1
```

## Data Collection Checklist (Owner vs Impostor)

## Owner session checklist

- Use default label (`owner`).
- Collect at least 20 windows before first training.
- Collect mixed behavior: typing-heavy, mouse-heavy, normal browsing.
- Keep session lengths varied (short and long sessions).
- Rerun `./run_pipeline.sh` and confirm context model coverage improves.

## Impostor session checklist

- Set label explicitly before receiver start.

Linux:

```bash
BEHAVIOR_COLLECTION_LABEL=impostor python python_engine/receiver.py
```

Windows PowerShell:

```powershell
$env:BEHAVIOR_COLLECTION_LABEL = "impostor"
python python_engine\receiver.py
```

- Record behaviors that differ from owner style:
	- slower/faster typing rhythm
	- trackpad-only or very different mouse movement
	- different pause patterns
- Keep impostor data in separate labeled sessions.
- Retrain with `./run_pipeline.sh` and validate score separation using `python_engine/analyze_scores.py`.

If real impostor users are unavailable, generate synthetic negatives for testing only:

```bash
python python_engine/generate_pseudo_impostor.py
```

## Quick Setup

## Linux (full capture + training)

1. Install system dependencies:

```bash
sudo apt update
sudo apt install -y build-essential cmake pkg-config libevdev-dev libzmq3-dev cppzmq-dev python3 python3-venv
```

2. Create and activate virtual environment:

```bash
cd /path/to/behavior_auth
python3 -m venv python_engine/venv
source python_engine/venv/bin/activate
```

3. Install Python dependencies once from root:

```bash
pip install -r requirements.txt
```

4. Build event engine:

```bash
cd event_engine
cmake -S . -B build
cmake --build build
cd ..
```

## Windows (training/analysis only)

Note: direct Linux input capture (`/dev/input/*` + `libevdev`) is Linux-specific. On native Windows, use Python training/analysis with existing collected data.

1. Install Python 3.10+.
2. Create and activate virtual environment:

```powershell
cd C:\path\to\behavior_auth
python -m venv python_engine\venv
python_engine\venv\Scripts\Activate.ps1
```

3. Install dependencies:

```powershell
pip install -r requirements.txt
```

4. Run full training pipeline:

```powershell
.\run_pipeline.ps1
```

## Running the System (Linux)

Open 2 terminals.

Terminal 1: start event publisher

```bash
cd /path/to/behavior_auth/event_engine/build
sudo ./event_engine
```

Terminal 2: start Python receiver

```bash
cd /path/to/behavior_auth
source python_engine/venv/bin/activate
python python_engine/receiver.py
```

## Running as a Background Service (No Terminal)

If you want the system to run seamlessly in the background without keeping terminals open, follow these steps.

### Linux (systemd Service)

You can configure the system to run locally without terminals using a systemd daemon.

1. Ensure the background script `start_background.sh` is executable:
```bash
chmod +x /path/to/behavior_auth/start_background.sh
```

2. Create a service file:
```bash
sudo nano /etc/systemd/system/behavior_auth.service
```

3. Paste the following configuration (update `/path/to/behavior_auth` to your actual absolute path):
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

4. Enable and start the service:
```bash
sudo systemctl daemon-reload
sudo systemctl enable behavior_auth.service
sudo systemctl start behavior_auth.service
```

The system will now automatically launch globally in the background every time your Linux machine boots up. You can track ongoing AI logs at `/tmp/behavior_python_receiver.log`.

### Windows (Task Scheduler)

*Note: Since the C++ `event_engine` tracking low-level kernel strokes is Linux-only, this configures only the Python receiver engine to run silently in the background.*

1. Open **Task Scheduler** from the Windows Start Menu.
2. Click **Create Task...** on the right-hand panel.
3. In the **General** tab:
   - Name: `Behavior Auth Service`
   - Select **Run whether user is logged on or not**.
   - Check **Run with highest privileges**.
4. In the **Triggers** tab:
   - Click **New...** and select **At log on** (or **At startup**).
5. In the **Actions** tab:
   - Click **New...** and select **Start a program**.
   - Program/script: `powershell.exe`
   - Add arguments: `-WindowStyle Hidden -ExecutionPolicy Bypass -Command "cd C:\path\to\behavior_auth\python_engine; .\venv\Scripts\Activate.ps1; python receiver.py"`
6. Save the task. The authentication listener will now run completely invisibly in the Windows background.

## Owner Data Collection

Default label is `owner`.

Start receiver as above and use system normally (typing + mouse) for multiple sessions.

Check current dataset stats:

```bash
./run_pipeline.sh
```

## Impostor Data Collection

If you have a second user/device style, collect with a non-owner label:

Linux:

```bash
cd /path/to/behavior_auth
source python_engine/venv/bin/activate
BEHAVIOR_COLLECTION_LABEL=impostor python python_engine/receiver.py
```

Windows PowerShell (for data import/testing workflows):

```powershell
$env:BEHAVIOR_COLLECTION_LABEL = "impostor"
python python_engine\receiver.py
```

If real impostor data is unavailable, generate synthetic negative samples for testing only:

```bash
cd /path/to/behavior_auth
source python_engine/venv/bin/activate
python python_engine/generate_pseudo_impostor.py
```

## Train Models

## One command (recommended)

Linux:

```bash
./run_pipeline.sh
```

Windows:

```powershell
.\run_pipeline.ps1
```

This runs:

- DB migration/sanity
- dataset summary (label + activity counts)
- global + context instant model training
- global + context sequence model training
- model file verification

## Manual commands

```bash
cd /path/to/behavior_auth
source python_engine/venv/bin/activate
python python_engine/train_iforest.py
python python_engine/train_sequence_iforest.py
```

## Context-Aware Models

Activity IDs:

- `0`: typing
- `1`: mouse-driven
- `2`: idle
- `3`: mixed

Context models are trained only when enough samples exist for that activity. Missing context models automatically fall back to global models during realtime inference.

## Git Setup for This Repo

Initialize and link remote:

```bash
cd /path/to/behavior_auth
git init
git branch -M main
git remote add origin https://github.com/2023abhisheksharma/behavior_auth.git
```

Commit and push:

```bash
git add .
git commit -m "Initial behavior_auth setup"
git push -u origin main
```

If remote already exists, update URL:

```bash
git remote set-url origin https://github.com/2023abhisheksharma/behavior_auth.git
```

## Troubleshooting

- If mouse data stops: keep receiver and publisher running; check receiver warnings for sequence gaps.
- If DB resets: it should not reset anymore. Verify `python_engine/behavior_data.db` is being used.
- If context models are missing: collect more samples for those activities and rerun pipeline.
- If scores look unstable: increase owner samples and retrain.

## Release Tags

Use semantic version tags for stable checkpoints.

```bash
git tag -a v0.2.0 -m "Behavior auth stable docs + pipeline + context routing"
git push origin v0.2.0
```
