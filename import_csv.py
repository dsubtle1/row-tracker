"""
CSV Import Script — Concept2 Logbook Season Export
====================================================
Reads all CSV files from ./csv-data/, filters to RowErg workouts only,
parses C2's column format, and inserts into the local SQLite database.

Idempotent: uses INSERT OR IGNORE on the C2 Log ID primary key,
so re-running against the same files will not create duplicates.

Usage (inside the container, or locally):
    python import_csv.py

Optional: target a single file:
    python import_csv.py csv-data/concept2-season-2020.csv
"""

import csv
import glob
import os
import sys
from datetime import datetime

from app import create_app
from models import db, Workout

# --------------------------------------------------------------------------- #
#  Pace parser                                                                 #
# --------------------------------------------------------------------------- #

def parse_pace(pace_str: str) -> int | None:
    """
    Convert C2 pace string to integer seconds per 500m.

    C2 formats: '2:28.7'  '1:57.9'  '2:04.3'
    We truncate the fractional second (floor to int).
    Returns None if the string is empty or unparseable.
    """
    if not pace_str or not pace_str.strip():
        return None
    try:
        pace_str = pace_str.strip()
        minutes_part, seconds_part = pace_str.split(":")
        minutes = int(minutes_part)
        seconds = int(float(seconds_part))   # drop sub-second fraction
        return minutes * 60 + seconds
    except (ValueError, AttributeError):
        return None


# --------------------------------------------------------------------------- #
#  Row parser                                                                  #
# --------------------------------------------------------------------------- #

def parse_row(row: dict) -> Workout | None:
    """
    Map one CSV row to a Workout instance.
    Returns None if the row should be skipped (non-RowErg, missing ID, etc.).
    """
    # Filter: RowErg only
    workout_type_raw = row.get("Type", "").strip()
    if workout_type_raw != "RowErg":
        return None

    # Log ID — required
    log_id_raw = row.get("Log ID", "").strip()
    if not log_id_raw:
        return None
    try:
        log_id = int(log_id_raw)
    except ValueError:
        return None

    # Date — required
    date_raw = row.get("Date", "").strip()
    if not date_raw:
        return None
    try:
        workout_date = datetime.strptime(date_raw, "%Y-%m-%d %H:%M:%S").date()
    except ValueError:
        return None

    # Time in seconds (C2 exports as decimal seconds, e.g. 595.1)
    time_seconds = None
    time_raw = row.get("Work Time (Seconds)", "").strip()
    if time_raw:
        try:
            time_seconds = int(float(time_raw))
        except ValueError:
            pass

    # Distance in metres
    distance_meters = None
    dist_raw = row.get("Work Distance", "").strip()
    if dist_raw:
        try:
            distance_meters = int(dist_raw)
        except ValueError:
            pass

    # Pace
    avg_pace_seconds = parse_pace(row.get("Pace", ""))

    # Stroke rate
    avg_stroke_rate = None
    spm_raw = row.get("Stroke Rate/Cadence", "").strip()
    if spm_raw:
        try:
            avg_stroke_rate = int(spm_raw)
        except ValueError:
            pass

    # Total calories
    total_calories = None
    cal_raw = row.get("Total Cal", "").strip()
    if cal_raw:
        try:
            total_calories = int(cal_raw)
        except ValueError:
            pass

    return Workout(
        id               = log_id,
        workout_date     = workout_date,
        workout_type     = "rower",
        time_seconds     = time_seconds,
        distance_meters  = distance_meters,
        avg_pace_seconds = avg_pace_seconds,
        avg_stroke_rate  = avg_stroke_rate,
        total_calories   = total_calories,
        stroke_data      = None,    # not available from CSV
        raw_json         = None,    # not available from CSV
        synced_at        = datetime.utcnow(),
    )


# --------------------------------------------------------------------------- #
#  Main import logic                                                            #
# --------------------------------------------------------------------------- #

def import_files(file_paths: list[str]) -> None:
    app = create_app()

    with app.app_context():
        total_inserted = 0
        total_skipped  = 0
        total_errors   = 0

        for file_path in sorted(file_paths):
            file_inserted = 0
            file_skipped  = 0

            print(f"\n→ {os.path.basename(file_path)}")

            with open(file_path, newline="", encoding="utf-8-sig") as f:
                reader = csv.DictReader(f)

                for line_num, row in enumerate(reader, start=2):
                    workout = parse_row(row)

                    if workout is None:
                        file_skipped += 1
                        continue

                    # Use merge (INSERT OR IGNORE equivalent via SQLAlchemy)
                    existing = db.session.get(Workout, workout.id)
                    if existing is not None:
                        file_skipped += 1
                        continue

                    db.session.add(workout)
                    file_inserted += 1

                    # Commit in batches to avoid large memory usage
                    if file_inserted % 100 == 0:
                        db.session.commit()

            db.session.commit()
            print(f"   inserted: {file_inserted}   skipped/non-RowErg: {file_skipped}")
            total_inserted += file_inserted
            total_skipped  += file_skipped

        print(f"\n{'='*50}")
        print(f"Import complete.")
        print(f"  Total inserted : {total_inserted}")
        print(f"  Total skipped  : {total_skipped}")
        print(f"  Errors         : {total_errors}")

        # After import, recalculate personal bests
        if total_inserted > 0:
            print("\nRecalculating personal bests...")
            from pb_engine import recalculate_all_pbs
            recalculate_all_pbs()
            print("Personal bests updated.")


if __name__ == "__main__":
    if len(sys.argv) > 1:
        # Specific file(s) passed as arguments
        files = sys.argv[1:]
    else:
        # Auto-discover all CSVs in ./csv-data/
        csv_dir = os.path.join(os.path.dirname(__file__), "csv-data")
        files = glob.glob(os.path.join(csv_dir, "*.csv"))

        if not files:
            print(f"No CSV files found in {csv_dir}")
            print("Usage: python import_csv.py [file1.csv file2.csv ...]")
            sys.exit(1)

    print(f"Found {len(files)} file(s) to import.")
    import_files(files)
