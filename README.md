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
