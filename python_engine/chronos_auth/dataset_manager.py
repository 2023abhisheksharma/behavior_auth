import sqlite3
import numpy as np
import pandas as pd
from pathlib import Path
from typing import Tuple, Optional
from chronos_auth.chronos_features import CHRONOS_FEATURE_COLUMNS, CHRONOS_FEATURE_DIM

class ChronosDatasetManager:
    """
    Manages real labeled training rows for Chronos-Auth.
    It never creates, perturbs, or fills synthetic impostor samples.
    """

    def __init__(self, db_path: Optional[str] = None):
        if db_path is None:
            self.db_path = Path(__file__).resolve().parent.parent / "behavior_data.db"
        else:
            self.db_path = Path(db_path)

        self._ensure_schema()

    def _ensure_schema(self):
        """Ensures that all 26 feature columns exist in the SQLite database without losing old data."""
        conn = sqlite3.connect(str(self.db_path))
        cur = conn.cursor()

        cur.execute("PRAGMA table_info(features)")
        existing_cols = {row[1] for row in cur.fetchall()}

        for col in CHRONOS_FEATURE_COLUMNS:
            if col not in existing_cols:
                cur.execute(f"ALTER TABLE features ADD COLUMN {col} REAL")

        conn.commit()
        conn.close()

    def load_training_data(
        self,
        feature_columns: Optional[list] = None,
    ) -> Tuple[np.ndarray, np.ndarray, pd.DataFrame]:
        """
        Loads genuine owner samples and impostor samples from SQLite.
        Returns:
            (X, y, full_dataframe)
            where y = 0 for Owner, y = 1 for Impostor
        """
        conn = sqlite3.connect(str(self.db_path))
        df = pd.read_sql("SELECT * FROM features", conn)
        conn.close()

        if df.empty:
            raise RuntimeError(f"Database {self.db_path} has no records!")

        target_cols = feature_columns or [
            "mean_dwell",
            "std_dwell",
            "mean_flight",
            "std_flight",
            "typing_speed",
        ]

        df = df.dropna(subset=target_cols)

        owner_df = df[
            (df["label"] == "owner")
            & (~df["data_source"].isin(["local_chronos", "local_legacy_window"]))
        ].copy()
        impostor_df = df[df["label"].isin(["external_impostor", "impostor"])].copy()

        print(f"[Dataset] Loaded {len(owner_df)} owner records, {len(impostor_df)} existing non-owner records.")

        if owner_df.empty:
            raise RuntimeError("No labeled owner rows found in database.")

        if impostor_df.empty:
            raise RuntimeError(
                "No real impostor rows found. Import a labeled public dataset or a labeled impostor DB before training."
            )

        owner_df["target"] = 0
        impostor_df["target"] = 1

        combined = pd.concat([owner_df, impostor_df], ignore_index=True)
        # Shuffle
        combined = combined.sample(frac=1.0, random_state=42).reset_index(drop=True)

        X = combined[target_cols].to_numpy(dtype=np.float32)
        y = combined["target"].to_numpy(dtype=np.int32)

        return X, y, combined
