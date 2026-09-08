from collections import deque
import os
from chronos_auth.realtime_pipeline import ChronosRealtimePipeline
from chronos_auth.ngram_analyzer import normalize_windows_key_code

# Sub-second dual-horizon continuous authentication engine
chronos_engine = ChronosRealtimePipeline()


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
            if os.name == "nt":
                event["key_code"] = normalize_windows_key_code(event["key_code"])
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
        elif event_type in ("MOUSE_DOWN", "MOUSE_UP"):
            event["device"] = int(parts[payload_index + 1])
            event["key_code"] = int(parts[payload_index + 2])
        elif event_type == "MOUSE_SCROLL":
            event["device"] = int(parts[payload_index + 1])
            event["value"] = int(parts[payload_index + 2])
        else:
            return
    except (ValueError, IndexError):
        return

    buffer.append(event)
    chronos_engine.process_event(event)
