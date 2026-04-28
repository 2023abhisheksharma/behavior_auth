import sqlite3
import shutil
import sys
from pathlib import Path
from database import DB_PATH

def merge_dbs(impostor_db_path):
    impostor_path = Path(impostor_db_path)
    if not impostor_path.exists():
        print(f"Error: {impostor_db_path} not found.")
        sys.exit(1)

    print(f"Importing {impostor_path} into our main DB...")
    
    # Connect to both DBs
    conn_main = sqlite3.connect(DB_PATH)
    conn_imp = sqlite3.connect(impostor_path)

    # Read the features from the friend's DB
    import pandas as pd
    try:
        df_imp = pd.read_sql("SELECT * FROM features", conn_imp)
    except Exception as e:
        print("Failed to read features table from impostor DB:", e)
        sys.exit(1)
        
    if df_imp.empty:
        print("Impostor database has no feature records.")
        sys.exit(0)
        
    print(f"Found {len(df_imp)} rows from friend's machine.")
    
    # 💥 CRITICAL: Relabel everything they did as 'impostor'
    df_imp['label'] = "impostor"
    
    # Drop their local ID to avoid primary key conflicts when appending to our DB
    if 'id' in df_imp.columns:
        df_imp = df_imp.drop(columns=['id'])
        
    # Insert everything into our main DB
    df_imp.to_sql("features", conn_main, if_exists="append", index=False)
    
    print(f"✅ Success! Merged {len(df_imp)} impostor records. You can now run LightGBM training.")

    conn_main.close()
    conn_imp.close()

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python import_impostor_db.py <path_to_friends_behavior_data.db>")
        sys.exit(1)
    merge_dbs(sys.argv[1])
