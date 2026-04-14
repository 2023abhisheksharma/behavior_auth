import sqlite3
import subprocess
import sys
from pathlib import Path

import database  # Ensures DB migration runs before everything else.

from settings import (
    DB_PATH,
    MODEL_PATH,
    SEQUENCE_MODEL_PATH,
    CONTEXT_MODEL_DIR,
    CONTEXT_SEQUENCE_MODEL_DIR,
    ACTIVITY_LABELS,
)

BASE_DIR = Path(__file__).resolve().parent


def run_step(title, script_name):
    script_path = BASE_DIR / script_name
    print(f"\n=== {title} ===")
    print(f"Running: {script_path}")

    proc = subprocess.run(
        [sys.executable, str(script_path)],
        cwd=str(BASE_DIR),
        text=True,
        capture_output=True,
    )

    if proc.stdout:
        print(proc.stdout.strip())
    if proc.stderr:
        print(proc.stderr.strip())

    if proc.returncode != 0:
        raise RuntimeError(f"Step failed: {title} (exit={proc.returncode})")


def print_dataset_summary():
    print("\n=== Dataset Summary ===")
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    cur.execute("SELECT COUNT(*) FROM features")
    total = cur.fetchone()[0]
    print(f"Total rows: {total}")

    cur.execute(
        """
        SELECT COALESCE(label, 'NULL') AS label, COUNT(*)
        FROM features
        GROUP BY COALESCE(label, 'NULL')
        ORDER BY COUNT(*) DESC
        """
    )
    print("Rows by label:")
    for label, cnt in cur.fetchall():
        print(f"  - {label}: {cnt}")

    cur.execute(
        """
        SELECT CAST(activity AS INTEGER) AS activity_id, COUNT(*)
        FROM features
        GROUP BY CAST(activity AS INTEGER)
        ORDER BY activity_id
        """
    )
    print("Rows by activity:")
    rows = cur.fetchall()
    if not rows:
        print("  - none")
    else:
        for activity_id, cnt in rows:
            name = ACTIVITY_LABELS.get(activity_id, f"unknown_{activity_id}")
            print(f"  - {activity_id} ({name}): {cnt}")

    conn.close()


def verify_models():
    print("\n=== Model Check ===")
    expected = [Path(MODEL_PATH), Path(SEQUENCE_MODEL_PATH)]

    for p in expected:
        print(f"  - {'OK' if p.exists() else 'MISSING'}: {p}")

    context_dir = Path(CONTEXT_MODEL_DIR)
    seq_context_dir = Path(CONTEXT_SEQUENCE_MODEL_DIR)

    print("Instant context models:")
    for activity_id, name in ACTIVITY_LABELS.items():
        p = context_dir / f"iforest_activity_{activity_id}.pkl"
        print(f"  - {'OK' if p.exists() else 'MISSING'}: {name} -> {p}")

    print("Sequence context models:")
    for activity_id, name in ACTIVITY_LABELS.items():
        p = seq_context_dir / f"sequence_iforest_activity_{activity_id}.pkl"
        print(f"  - {'OK' if p.exists() else 'MISSING'}: {name} -> {p}")


def main():
    print("Behavior Auth Full Training Pipeline")
    print(f"Python: {sys.executable}")
    print(f"DB: {DB_PATH}")

    print_dataset_summary()
    run_step("Train Instant Models (Global + Context)", "train_iforest.py")
    run_step("Train Sequence Models (Global + Context)", "train_sequence_iforest.py")
    verify_models()

    print("\nPipeline completed successfully.")


if __name__ == "__main__":
    main()
