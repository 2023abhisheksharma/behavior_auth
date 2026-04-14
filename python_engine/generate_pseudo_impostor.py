import sqlite3

import numpy as np
import pandas as pd

import database  # Ensures schema migration is applied.
from settings import DB_PATH, FEATURE_COLUMNS


def main(multiplier=1.0):
    conn = sqlite3.connect(DB_PATH)
    df = pd.read_sql("SELECT * FROM features WHERE label='owner'", conn)

    if df.empty:
        conn.close()
        raise RuntimeError("No owner data found to generate pseudo impostor rows")

    df = df.reindex(columns=FEATURE_COLUMNS, fill_value=0)

    # Create synthetic impostor patterns by shifting speed/timing relationships.
    synth = df.copy()
    rng = np.random.default_rng(42)

    synth["typing_speed"] = synth["typing_speed"] * rng.uniform(0.4, 0.8, len(synth))
    synth["mean_dwell"] = synth["mean_dwell"] * rng.uniform(1.2, 1.8, len(synth))
    synth["mean_flight"] = synth["mean_flight"] * rng.uniform(1.1, 1.7, len(synth))
    synth["mean_velocity"] = synth["mean_velocity"] * rng.uniform(0.5, 1.8, len(synth))
    synth["std_velocity"] = synth["std_velocity"] * rng.uniform(0.7, 2.0, len(synth))
    synth["direction_rate"] = np.clip(
        synth["direction_rate"] * rng.uniform(0.8, 1.8, len(synth)),
        0,
        1,
    )

    # Optionally amplify mismatch severity.
    if multiplier != 1.0:
        synth["mean_dwell"] *= multiplier
        synth["mean_flight"] *= multiplier
        synth["typing_speed"] /= max(multiplier, 1e-6)

    cols = ",".join(FEATURE_COLUMNS)
    placeholders = ",".join(["?"] * (len(FEATURE_COLUMNS) + 1))

    rows = [tuple(r) + ("impostor_synth",) for r in synth[FEATURE_COLUMNS].to_numpy(dtype=float)]
    conn.executemany(
        f"INSERT INTO features ({cols}, label) VALUES ({placeholders})",
        rows,
    )
    conn.commit()

    print(f"Inserted {len(rows)} pseudo impostor rows")
    conn.close()


if __name__ == "__main__":
    main()
