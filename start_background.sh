#!/bin/bash
# A script to start both C++ and Python engines in the background

cd "$(dirname "$0")"

echo "Starting Behavior Auth Background Services..."

# Prompt for sudo password upfront in the foreground so backgrounding doesn't break
echo "We need administrator permissions to read mouse/keyboard devices."
sudo -v

# 1. Start the C++ Event Engine with sudo
cd event_engine/build
if [ ! -f "event_engine" ]; then
    echo "event_engine binary not found! Did you build it?"
    exit 1
fi
echo "Starting C++ Event Engine (requires sudo)..."
sudo nohup ./event_engine > /tmp/behavior_event_engine.log 2>&1 &
echo "C++ Event Engine started."

# 2. Start the Python Receiver
cd ../../python_engine
echo "Starting Python Receiver..."
source .venv/bin/activate
nohup python receiver.py > /tmp/behavior_python_receiver.log 2>&1 &
echo "Python Receiver started."

echo "All services running in the background!"
echo "Check /tmp/behavior_event_engine.log and /tmp/behavior_python_receiver.log for output."
echo "To stop them later, run: sudo pkill -f event_engine && pkill -f 'python receiver.py'"
