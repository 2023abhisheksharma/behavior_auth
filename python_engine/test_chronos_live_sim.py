import sys
import time
from collections import deque
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))

from event_processor import process_event

def run_simulation():
    print("================================================================")
    print(" 🧪 RUNNING END-TO-END CHRONOS-AUTH LIVE SIMULATION TEST")
    print("================================================================")

    buffer = deque()
    base_ts = int(time.time() * 1e6)
    seq = 100

    # 1. Simulate Genuine Owner Typing & Mouse Movement
    print("\n[Phase 1] Simulating Genuine Owner (Natural Rhythm)...")
    keys = [18, 19, 31, 32, 57, 21, 22, 36, 37, 28] # E, R, S, D, Space, Y, U, J, K, Enter
    for k in keys:
        # Key down
        process_event(f"{base_ts},{seq},KEY_DOWN,{k}", buffer)
        base_ts += 85000  # 85ms dwell
        seq += 1
        # Key up
        process_event(f"{base_ts},{seq},KEY_UP,{k}", buffer)
        base_ts += 95000  # 95ms flight
        seq += 1

    # Add smooth mouse stroke
    base_ts += 250000 # 250ms HTL
    for step in range(12):
        process_event(f"{base_ts},{seq},MOUSE_MOVE,0,15,10", buffer)
        base_ts += 15000
        seq += 1
    # Mouse click
    process_event(f"{base_ts},{seq},MOUSE_DOWN,0,272", buffer)
    base_ts += 75000
    seq += 1
    process_event(f"{base_ts},{seq},MOUSE_UP,0,272", buffer)
    seq += 1

    time.sleep(0.5)

    # 2. Simulate Impostor Takeover (Foreign Kinematics & Timing Distortions)
    print("\n[Phase 2] Simulating Impostor Workstation Takeover...")
    impostor_keys = [48, 47, 46, 45, 14, 14, 14, 25, 26, 27] # Unusual key bursts & rapid backspaces
    for k in impostor_keys:
        process_event(f"{base_ts},{seq},KEY_DOWN,{k}", buffer)
        base_ts += 280000  # Sluggish 280ms dwell
        seq += 1
        process_event(f"{base_ts},{seq},KEY_UP,{k}", buffer)
        base_ts += 350000  # Erratic 350ms flight
        seq += 1

    # Add jerky/wobbly mouse movement
    base_ts += 1800000 # 1.8s long hesitation
    for step in range(10):
        dx = 50 if step % 2 == 0 else -40
        dy = -30 if step % 2 == 0 else 45
        process_event(f"{base_ts},{seq},MOUSE_MOVE,0,{dx},{dy}", buffer)
        base_ts += 8000
        seq += 1

    # Second burst of impostor typing
    for k in [30, 44, 16, 17, 28]:
        process_event(f"{base_ts},{seq},KEY_DOWN,{k}", buffer)
        base_ts += 320000
        seq += 1
        process_event(f"{base_ts},{seq},KEY_UP,{k}", buffer)
        base_ts += 400000
        seq += 1

    # Third burst: 10 keys to trigger evaluation and cross lock threshold
    for k in [49, 50, 51, 52, 53, 54, 55, 56, 57, 28]:
        process_event(f"{base_ts},{seq},KEY_DOWN,{k}", buffer)
        base_ts += 310000
        seq += 1
        process_event(f"{base_ts},{seq},KEY_UP,{k}", buffer)
        base_ts += 390000
        seq += 1

    print("\n================================================================")
    print(" ✅ Live Simulation Completed Successfully!")
    print("================================================================")

if __name__ == "__main__":
    run_simulation()
