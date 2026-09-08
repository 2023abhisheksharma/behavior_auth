#!/usr/bin/env bash
set -e

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHON="${DIR}/python_engine/venv/bin/python"

echo "================================================================"
echo " 📦 Packaging Standalone Portable Executable (No Python Required)"
echo "================================================================"

"${DIR}/python_engine/venv/bin/pyinstaller" \
  --noconfirm \
  --onedir \
  --name "chronos-auth" \
  --paths "${DIR}/python_engine" \
  --collect-all chronos_auth \
  --collect-all customtkinter \
  "${DIR}/python_engine/desktop_app.py"

echo ""
echo "✅ Standalone bundle generated in: ${DIR}/dist/chronos-auth/"
echo "Users can now double-click 'dist/chronos-auth/chronos-auth' to run without installing Python!"
