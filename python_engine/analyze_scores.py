import sqlite3
import pandas as pd
import joblib
import database  # Ensures schema migration is applied.
from settings import DB_PATH, MODEL_PATH

model = joblib.load(MODEL_PATH)

conn = sqlite3.connect(DB_PATH)
df = pd.read_sql("SELECT * FROM features", conn)
conn.close()

if hasattr(model, "feature_names_in_"):
	expected = list(model.feature_names_in_)
	X = df.reindex(columns=expected, fill_value=0)
else:
	X = df.drop(columns=["id", "label"], errors="ignore")

scores = model.decision_function(X)

print("Min score:", scores.min())
print("Max score:", scores.max())
print("Mean score:", scores.mean())
