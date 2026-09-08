#!/usr/bin/env bash
set -e

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "================================================================"
echo " 🛡️  CHRONOS-AUTH: ONE-CLICK AUTOMATED SYSTEM INSTALLER"
echo "================================================================"
echo "Setting up continuous biometric authentication on your machine..."
echo ""

# 1. Detect Package Manager & Install System Prerequisites if missing
MISSING_PKGS=()
if ! command -v cmake &> /dev/null; then MISSING_PKGS+=("cmake"); fi
if ! command -v g++ &> /dev/null; then MISSING_PKGS+=("build-essential"); fi
if ! pkg-config --exists libevdev 2>/dev/null; then MISSING_PKGS+=("libevdev-dev"); fi
if ! pkg-config --exists libzmq 2>/dev/null; then MISSING_PKGS+=("libzmq3-dev"); fi
if ! command -v python3 &> /dev/null; then MISSING_PKGS+=("python3"); fi

if [ ${#MISSING_PKGS[@]} -gt 0 ]; then
  echo "📦 Installing required system libraries: ${MISSING_PKGS[*]}..."
  if command -v apt-get &> /dev/null; then
    sudo apt-get update -qq
    sudo apt-get install -y -qq build-essential cmake pkg-config libevdev-dev libzmq3-dev cppzmq-dev python3 python3-venv
  elif command -v dnf &> /dev/null; then
    sudo dnf install -y -q gcc-c++ cmake pkgconfig libevdev-devel zeromq-devel python3
  elif command -v pacman &> /dev/null; then
    sudo pacman -Sy --noconfirm base-devel cmake libevdev zeromq cppzmq python
  else
    echo "⚠️ Warning: Unknown package manager. Please ensure cmake, libevdev, and zeromq are installed."
  fi
fi

# 2. Build C++ Event Engine
echo "⚙️ Building C++ Hardware Event Engine..."
mkdir -p "${DIR}/event_engine/build"
cmake -S "${DIR}/event_engine" -B "${DIR}/event_engine/build" > /dev/null
cmake --build "${DIR}/event_engine/build" -- -j"$(nproc 2>/dev/null || echo 2)" > /dev/null
echo "✅ Event Engine built successfully."

# 3. Setup Python Machine Learning Environment
echo "🧠 Setting up Python Biometric Environment..."
VENV_DIR="${DIR}/python_engine/venv"
if [ ! -d "${VENV_DIR}" ]; then
  python3 -m venv "${VENV_DIR}"
fi

VENV_PIP="${VENV_DIR}/bin/pip"
VENV_PYTHON="${VENV_DIR}/bin/python"

"${VENV_PIP}" install --upgrade pip -q
"${VENV_PIP}" install -r "${DIR}/requirements.txt" -q
# 4. Train the calibrated model if needed
if [ ! -f "${DIR}/python_engine/models/chronos/chronos_classifier.pkl" ]; then
  echo "⚡ Calibrating initial AI biometric weights..."
  "${VENV_PYTHON}" "${DIR}/python_engine/train_chronos.py" > /dev/null 2>&1 || true
fi

# 5. Create One-Click Desktop Application Shortcut (.desktop)
bash "${DIR}/install_desktop.sh"

echo ""
echo "================================================================"
echo " 🎉 INSTALLATION COMPLETE!"
echo "================================================================"
echo "• Desktop Icon: 'Chronos Auth' created on your Desktop."
echo "• Launching application hub now..."
echo "================================================================"

exec "${DIR}/app.sh"
