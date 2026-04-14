from collections import deque
from feature_engine import add_event_and_check_window


def process_event(msg, buffer):
    parts = msg.split(",")
    if len(parts) < 3:
        return

    try:
        timestamp = int(parts[0])
    except ValueError:
        return

    # Backward compatible format handling:
    # old: ts,TYPE,...
    # new: ts,seq,TYPE,...
    payload_index = 1
    sequence = None
    if parts[1].isdigit() and len(parts) >= 4:
        sequence = int(parts[1])
        payload_index = 2

    event_type = parts[payload_index]
    event = {
        "timestamp": timestamp,
        "type": event_type,
        "sequence": sequence,
    }

    try:
        if event_type in ("KEY_DOWN", "KEY_UP"):
            event["key_code"] = int(parts[payload_index + 1])
        elif event_type == "MOUSE_MOVE":
            # new: ts,seq,MOUSE_MOVE,device,dx,dy
            # old: ts,MOUSE_MOVE,dx,dy
            if len(parts) >= payload_index + 4:
                event["device"] = int(parts[payload_index + 1])
                event["dx"] = int(parts[payload_index + 2])
                event["dy"] = int(parts[payload_index + 3])
            else:
                event["device"] = 0
                event["dx"] = int(parts[payload_index + 1])
                event["dy"] = int(parts[payload_index + 2])
        else:
            return
    except (ValueError, IndexError):
        return

    buffer.append(event)
    add_event_and_check_window(event)