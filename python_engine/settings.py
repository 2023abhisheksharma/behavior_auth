import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent

DB_PATH = os.getenv("BEHAVIOR_DB_PATH", str(BASE_DIR / "behavior_data.db"))
MODEL_PATH = os.getenv("BEHAVIOR_MODEL_PATH", str(BASE_DIR / "iforest_model.pkl"))
MODEL_BACKUP_PATH = os.getenv("BEHAVIOR_MODEL_BACKUP_PATH", str(BASE_DIR / "iforest_model_backup.pkl"))

WINDOW_TIME_US = int(os.getenv("BEHAVIOR_WINDOW_TIME_US", "20000000"))
MIN_KEY_EVENTS = int(os.getenv("BEHAVIOR_MIN_KEY_EVENTS", "5"))
MIN_MOUSE_EVENTS = int(os.getenv("BEHAVIOR_MIN_MOUSE_EVENTS", "10"))

LOCK_THRESHOLD = float(os.getenv("BEHAVIOR_LOCK_THRESHOLD", "0.30"))
ALERT_THRESHOLD = float(os.getenv("BEHAVIOR_ALERT_THRESHOLD", "0.50"))
TRUST_ALPHA = float(os.getenv("BEHAVIOR_TRUST_ALPHA", "0.2"))
CALIBRATION_WINDOWS = int(os.getenv("BEHAVIOR_CALIBRATION_WINDOWS", "30"))

ENABLE_ADAPTIVE_RETRAIN = os.getenv("BEHAVIOR_ENABLE_ADAPTIVE_RETRAIN", "0") == "1"
RETRAIN_MIN_SAMPLES = int(os.getenv("BEHAVIOR_RETRAIN_MIN_SAMPLES", "200"))
COLLECTION_LABEL = os.getenv("BEHAVIOR_COLLECTION_LABEL", "owner")

SEQUENCE_MODEL_PATH = os.getenv(
	"BEHAVIOR_SEQUENCE_MODEL_PATH",
	str(BASE_DIR / "sequence_iforest_model.pkl"),
)
SEQUENCE_LENGTH = int(os.getenv("BEHAVIOR_SEQUENCE_LENGTH", "5"))
SEQUENCE_BLEND_WEIGHT = float(os.getenv("BEHAVIOR_SEQUENCE_BLEND_WEIGHT", "0.5"))

CONTEXT_MODEL_DIR = os.getenv(
	"BEHAVIOR_CONTEXT_MODEL_DIR",
	str(BASE_DIR / "models" / "activity"),
)
CONTEXT_SEQUENCE_MODEL_DIR = os.getenv(
	"BEHAVIOR_CONTEXT_SEQUENCE_MODEL_DIR",
	str(BASE_DIR / "models" / "sequence_activity"),
)
CONTEXT_MIN_SAMPLES = int(os.getenv("BEHAVIOR_CONTEXT_MIN_SAMPLES", "12"))

ACTIVITY_LABELS = {
	0: "typing",
	1: "mouse",
	2: "idle",
	3: "mixed",
}

FEATURE_COLUMNS = [
	"mean_dwell",
	"std_dwell",
	"mean_flight",
	"std_flight",
	"typing_speed",
	"mean_velocity",
	"std_velocity",
	"mean_acc",
	"direction_rate",
	"mean_space_d",
	"mean_enter_d",
	"space_freq",
	"enter_freq",
	"activity",
]
