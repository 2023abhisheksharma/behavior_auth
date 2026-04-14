#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHON="${ROOT_DIR}/python_engine/venv/bin/python"

if [[ ! -x "${PYTHON}" ]]; then
  echo "Python venv executable not found: ${PYTHON}"
  echo "Create/activate your venv first."
  exit 1
fi

cd "${ROOT_DIR}/python_engine"
"${PYTHON}" run_full_pipeline.py
