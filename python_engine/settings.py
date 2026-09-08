import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = os.getenv("BEHAVIOR_DB_PATH", str(BASE_DIR / "behavior_data.db"))

ACTIVITY_LABELS = {
    0: "typing",
    1: "mouse",
    2: "idle",
    3: "mixed",
    5: "general",
}
