#!/bin/bash
# A script to gracefully stop both the C++ and Python behavior auth engines

echo "Stopping Behavior Auth Background Services..."

# 1. Stop the C++ Event Engine
pkill -f '[.]\/event_engine'
if [ $? -eq 0 ]; then
    echo "C++ Event Engine stopped."
else
    echo "C++ Event Engine was not running."
fi

# 2. Stop the Python Receiver
pkill -f '[r]eceiver.py'
if [ $? -eq 0 ]; then
    echo "Python Receiver stopped."
else
    echo "Python Receiver was not running."
fi

echo "All background services stopped!"
