from realtime_engine import RealtimeEngine
engine = RealtimeEngine()

import numpy as np
from database import save_features
from settings import WINDOW_TIME_US, MIN_KEY_EVENTS, MIN_MOUSE_EVENTS, COLLECTION_LABEL

WINDOW_TIME = WINDOW_TIME_US
window_start_time = None

key_down_times = {}
completed_keys = []
flight_times = []
mouse_movements = []

space_dwell = []
enter_dwell = []

space_count = 0
enter_count = 0

last_key_up_time = None


# ---------------- ACTIVITY ----------------
def detect_activity(typing_speed, mean_velocity):
    # 0 typing, 1 mouse-driven, 2 idle, 3 mixed
    if typing_speed >= 2.0 and mean_velocity < 2.0:
        return 0
    elif mean_velocity >= 3.0 and typing_speed < 0.7:
        return 1
    elif typing_speed < 0.3 and mean_velocity < 0.8:
        return 2
    else:
        return 3


# ---------------- EVENT ----------------
def add_event_and_check_window(event):
    global key_down_times, completed_keys, mouse_movements
    global last_key_up_time, flight_times
    global space_count, enter_count
    global window_start_time

    if window_start_time is None:
        window_start_time = event["timestamp"]

    if event["type"] == "KEY_DOWN":
        key_down_times[event["key_code"]] = event["timestamp"]

        if event["key_code"] == 57:
            space_count += 1
        if event["key_code"] == 28:
            enter_count += 1

        if last_key_up_time is not None:
            flight_times.append(event["timestamp"] - last_key_up_time)

    elif event["type"] == "KEY_UP":
        code = event["key_code"]

        if code in key_down_times:
            dwell = event["timestamp"] - key_down_times[code]
            completed_keys.append(dwell)

            if code == 57:
                space_dwell.append(dwell)
            if code == 28:
                enter_dwell.append(dwell)

            last_key_up_time = event["timestamp"]
            del key_down_times[code]

    elif event["type"] == "MOUSE_MOVE":
        mouse_movements.append((event.get("device", 0), event["dx"], event["dy"], event["timestamp"]))

    # -------- TIME WINDOW --------
    elapsed = event["timestamp"] - window_start_time

    if elapsed >= WINDOW_TIME:
        extract_features()
        reset_window()
        window_start_time = None


# ---------------- RESET ----------------
def reset_window():
    global key_down_times, completed_keys, mouse_movements, flight_times
    global space_dwell, enter_dwell, space_count, enter_count

    key_down_times.clear()
    completed_keys.clear()
    mouse_movements.clear()
    flight_times.clear()

    space_dwell.clear()
    enter_dwell.clear()

    space_count = 0
    enter_count = 0


# ---------------- FEATURE ----------------
def extract_features():

    # Skip idle/weak windows to avoid polluting training data.
    if len(completed_keys) < MIN_KEY_EVENTS and len(mouse_movements) < MIN_MOUSE_EVENTS:
        return

    dwell = np.array(completed_keys)
    flight = np.array(flight_times) if flight_times else np.array([0])

    mean_dwell = np.mean(dwell) if len(dwell) > 0 else 0
    std_dwell = np.std(dwell) if len(dwell) > 0 else 0

    mean_flight = np.mean(flight)
    std_flight = np.std(flight)

    total_time = (dwell.sum() + flight.sum()) / 1_000_000
    typing_speed = len(dwell) / total_time if total_time > 0 else 0

    # ---------- SPACE ----------
    mean_space_d = np.mean(space_dwell) if space_dwell else 0
    mean_enter_d = np.mean(enter_dwell) if enter_dwell else 0

    space_freq = space_count / len(dwell) if len(dwell) > 0 else 0
    enter_freq = enter_count / len(dwell) if len(dwell) > 0 else 0

    # ---------- MOUSE ----------
    velocities = []
    accelerations = []
    direction_changes = 0

    prev_velocity = None
    prev_angle = None
    prev_time = None

    for _device, dx, dy, t in mouse_movements:

        if prev_time is None:
            prev_time = t
            continue

        dt = (t - prev_time) / 1_000_000
        if dt <= 0:
            continue

        distance = np.sqrt(dx**2 + dy**2)

        # ❗ IGNORE NOISE MOVEMENT
        if distance < 1:
            prev_time = t
            continue

        velocity = distance / dt
        velocities.append(velocity)

        if prev_velocity is not None:
            acc = (velocity - prev_velocity) / dt
            accelerations.append(acc)

        angle = np.arctan2(dy, dx)

        if prev_angle is not None:
            if abs(angle - prev_angle) > np.pi / 4:
                direction_changes += 1

        prev_velocity = velocity
        prev_angle = angle
        prev_time = t

    mean_velocity = np.mean(velocities) if velocities else 0
    std_velocity = np.std(velocities) if velocities else 0

    mean_acc = np.mean(accelerations) if accelerations else 0

    direction_rate = (
        direction_changes / len(mouse_movements)
        if len(mouse_movements) > 0 else 0
    )

    activity = detect_activity(typing_speed, mean_velocity)

    feature_vector = [
        float(mean_dwell),
        float(std_dwell),
        float(mean_flight),
        float(std_flight),
        float(typing_speed),
        float(mean_velocity),
        float(std_velocity),
        float(mean_acc),
        float(direction_rate),
        float(mean_space_d),
        float(mean_enter_d),
        float(space_freq),
        float(enter_freq),
        float(activity),
    ]

    save_features(feature_vector, label=COLLECTION_LABEL)
    engine.predict(feature_vector)

    print("Saved:", feature_vector)