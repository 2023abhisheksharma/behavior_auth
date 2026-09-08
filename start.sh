#!/bin/bash
# A script to start both C++ and Python engines in the background

cd "$(dirname "$0")"

echo "Starting Behavior Auth Background Services..."



# Gracefully stop any existing instances before starting fresh
pkill -f '[.]\/event_engine' >/dev/null 2>&1 || true
pkill -f '[r]eceiver.py' >/dev/null 2>&1 || true
rm -f /tmp/chronos_live_state.json
rm -f /tmp/chronos_lock_mode
rm -f "${HOME}/.config/chronos-auth/live_state.json"
rm -f "${HOME}/.config/chronos-auth/lock_mode"
sleep 0.5

# 1. Start the C++ Event Engine
cd event_engine/build
if [ ! -f "event_engine" ]; then
    echo "event_engine binary not found! Did you build it?"
    exit 1
fi
echo "Starting C++ Event Engine..."
if command -v setsid >/dev/null 2>&1; then
    setsid -f ./event_engine > /tmp/behavior_event_engine.log 2>&1 < /dev/null
else
    nohup ./event_engine > /tmp/behavior_event_engine.log 2>&1 &
    disown $!
fi
echo "C++ Event Engine started."

# 2. Start the Python Receiver
cd ../../python_engine
echo "Starting Python Receiver..."

# Make sure we use the EXACT venv context by explicitly feeding it the fully qualified python binary
VENV_PYTHON=""
if [ -d "venv/bin" ]; then
    VENV_PYTHON="$(pwd)/venv/bin/python"
elif [ -d ".venv/bin" ]; then
    VENV_PYTHON="$(pwd)/.venv/bin/python"
else
    VENV_PYTHON="python3" # Fallback
fi

if command -v setsid >/dev/null 2>&1; then
    setsid -f "$VENV_PYTHON" -u receiver.py > /tmp/behavior_python_receiver.log 2>&1 < /dev/null
else
    nohup "$VENV_PYTHON" -u receiver.py > /tmp/behavior_python_receiver.log 2>&1 &
    disown $!
fi
echo "Python Receiver started using $VENV_PYTHON."

echo "All services running in the background!"
echo "To stop them later, run: ./stop.sh"
