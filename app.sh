#!/usr/bin/env bash
set -e

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHON="${DIR}/python_engine/venv/bin/python"

if [ ! -x "${PYTHON}" ]; then
  PYTHON="python3"
fi

echo "================================================================"
echo " 🛡️  Launching Chronos-Auth Dedicated Desktop Application"
echo "================================================================"

if [ -x "${DIR}/start.sh" ] && ! pgrep -f "receiver.py" >/dev/null 2>&1; then
  bash "${DIR}/start.sh" >/tmp/chronos_app_start.log 2>&1 &
fi

export DISPLAY="${DISPLAY:-:0}"
if [ -n "$WAYLAND_DISPLAY" ]; then
  export WAYLAND_DISPLAY="$WAYLAND_DISPLAY"
fi

exec "${PYTHON}" "${DIR}/python_engine/desktop_app.py" "$@"
