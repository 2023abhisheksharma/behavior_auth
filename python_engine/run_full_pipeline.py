import sqlite3
import subprocess
import sys
from pathlib import Path

import database  # Ensures DB migration runs before everything else.

from settings import ACTIVITY_LABELS, DB_PATH

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
    print("Chronos-Auth Next-Gen models:")
    chronos_dir = BASE_DIR / "models" / "chronos"
    for fname in ["chronos_classifier.pkl", "chronos_meta.json"]:
        p = chronos_dir / fname
        print(f"  - {'OK' if p.exists() else 'MISSING'}: {fname} -> {p}")
    mouse_model = chronos_dir / "chronos_mouse_model.pkl"
    print(f"  - {'OK' if mouse_model.exists() else 'NOT AVAILABLE (no measured mouse profile)'}: chronos_mouse_model.pkl -> {mouse_model}")


def main():
    print("Behavior Auth Full Training Pipeline")
    print(f"Python: {sys.executable}")
    print(f"DB: {DB_PATH}")

    print_dataset_summary()
    run_step("Train Chronos-Auth Contrastive & SPRT Models", "train_chronos.py")
    verify_models()

    print("\nPipeline completed successfully.")


if __name__ == "__main__":
    main()
