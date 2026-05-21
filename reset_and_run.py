"""
Reset script — wipes the database and re-runs the pipeline from scratch.
Run this when you want a clean slate: python reset_and_run.py
"""
import os
from pathlib import Path

db_path = Path("data/carbon_tracker.db")
if db_path.exists():
    os.remove(db_path)
    print(f"Deleted {db_path}")
else:
    print("No existing DB found.")

# Re-run pipeline
from pipeline.database import init_db
from pipeline.runner import run_pipeline

init_db()
run_pipeline()
