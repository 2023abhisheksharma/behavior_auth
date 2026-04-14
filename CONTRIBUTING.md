# Contributing

## Development Setup

## Linux

```bash
git clone https://github.com/2023abhisheksharma/behavior_auth.git
cd behavior_auth

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

## Daily Contributor Flow

1. Pull latest changes:

```bash
git pull --rebase origin main
```

2. Run quick validation:

```bash
./run_pipeline.sh
```

On Windows:

```powershell
.\run_pipeline.ps1
```

3. If changing Python code, run at least:

```bash
python -m compileall python_engine
```

4. Commit and push:

```bash
git add .
git commit -m "Describe your change"
git push origin main
```

## Data Collection Rules

- Use `owner` label for genuine owner sessions.
- Use `impostor` (or another explicit non-owner label) for non-owner sessions.
- Never mix owner and impostor behavior in one labeled run.
- Capture enough diversity across typing and mouse behavior before retraining.

Linux impostor example:

```bash
BEHAVIOR_COLLECTION_LABEL=impostor python python_engine/receiver.py
```

## Pull Request Notes

- Include summary of changed files and why.
- Include commands used for local validation.
- Mention any schema, model, or pipeline behavior changes.
