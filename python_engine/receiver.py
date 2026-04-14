import zmq
from collections import deque
from event_processor import process_event

context = zmq.Context()
socket = context.socket(zmq.SUB)
socket.setsockopt(zmq.RCVHWM, 10000)
socket.connect("tcp://localhost:5555")
socket.setsockopt_string(zmq.SUBSCRIBE, "")

print("Listening...")

buffer = deque()
last_sequence = None
sequence_gaps = 0

while True:
    msg = socket.recv_string()

    parts = msg.split(",")
    if len(parts) > 2 and parts[1].isdigit():
        seq = int(parts[1])
        if last_sequence is not None and seq != (last_sequence + 1):
            sequence_gaps += 1
            print(f"[WARN] sequence gap: expected {last_sequence + 1}, got {seq} (gaps={sequence_gaps})")
        last_sequence = seq

    process_event(msg, buffer)
    