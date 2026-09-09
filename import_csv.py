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

def classify_row(row: dict) -> tuple[Workout | None, str | None]:
    """
    Parse one CSV row, returning (workout_or_none, skip_reason).

    skip_reason is None on success, else:
      "non_rowing" — expected: not a RowErg session (bike, ski, etc.), filtered by design
      "invalid"    — unexpected: missing/malformed Log ID or Date, a real parse
                     failure that a plain "skipped: N" count would otherwise
                     hide inside ordinary non-RowErg filtering
    """
    # Filter: RowErg only. A blank Type isn't a deliberate other-erg entry —
    # it's a malformed/blank row (e.g. a trailing blank line), so it counts
    # as invalid rather than expected non-RowErg filtering.
    workout_type_raw = row.get("Type", "").strip()
    if not workout_type_raw:
        return None, "invalid"
    if workout_type_raw != "RowErg":
        return None, "non_rowing"

    # Log ID — required
    log_id_raw = row.get("Log ID", "").strip()
    if not log_id_raw:
        return None, "invalid"
    try:
        log_id = int(log_id_raw)
    except ValueError:
        return None, "invalid"

    # Date — required
    date_raw = row.get("Date", "").strip()
    if not date_raw:
        return None, "invalid"
    try:
        workout_date = datetime.strptime(date_raw, "%Y-%m-%d %H:%M:%S").date()
    except ValueError:
        return None, "invalid"

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
    ), None


def parse_row(row: dict) -> Workout | None:
    """
    Map one CSV row to a Workout instance.
    Returns None if the row should be skipped (non-RowErg, missing ID, etc.).
    See classify_row() for *why* a row was skipped.
    """
    return classify_row(row)[0]


# --------------------------------------------------------------------------- #
#  Main import logic                                                            #
# --------------------------------------------------------------------------- #

def import_rows(csv_file) -> dict:
    """
    Import RowErg rows from an open, text-mode, csv.DictReader-compatible
    file object (a local file handle or a decoded upload stream). Requires
    an active Flask app context. Shared by the CLI script (import_files,
    below) and the web upload route in blueprints/tracker.py.

    Returns {"inserted": int, "skipped": int, "skipped_non_rowing": int,
    "skipped_invalid": int, "skipped_duplicate": int}. "skipped" is the
    total of the three breakdown counts, kept for existing callers that
    only care about the aggregate; "skipped_invalid" is the one worth
    watching — a malformed Log ID or Date, not an expected filter/dupe.
    """
    reader = csv.DictReader(csv_file)
    inserted = 0
    skipped_non_rowing = 0
    skipped_invalid    = 0
    skipped_duplicate  = 0

    for row in reader:
        workout, reason = classify_row(row)

        if workout is None:
            if reason == "non_rowing":
                skipped_non_rowing += 1
            else:
                skipped_invalid += 1
            continue

        # Use merge (INSERT OR IGNORE equivalent via SQLAlchemy)
        existing = db.session.get(Workout, workout.id)
        if existing is not None:
            skipped_duplicate += 1
            continue

        db.session.add(workout)
        inserted += 1

        # Commit in batches to avoid large memory usage
        if inserted % 100 == 0:
            db.session.commit()

    db.session.commit()
    return {
        "inserted":           inserted,
        "skipped":            skipped_non_rowing + skipped_invalid + skipped_duplicate,
        "skipped_non_rowing": skipped_non_rowing,
        "skipped_invalid":    skipped_invalid,
        "skipped_duplicate":  skipped_duplicate,
    }


def import_files(file_paths: list[str]) -> None:
    app = create_app()

    with app.app_context():
        total_inserted = 0
        total_skipped  = 0
        total_invalid  = 0

        for file_path in sorted(file_paths):
            print(f"\n→ {os.path.basename(file_path)}")

            with open(file_path, newline="", encoding="utf-8-sig") as f:
                stats = import_rows(f)

            print(
                f"   inserted: {stats['inserted']}   "
                f"non-RowErg: {stats['skipped_non_rowing']}   "
                f"duplicate: {stats['skipped_duplicate']}   "
                f"invalid: {stats['skipped_invalid']}"
            )
            if stats["skipped_invalid"]:
                print(f"   ⚠ {stats['skipped_invalid']} row(s) had a malformed or missing Log ID/Date — check this file")
            total_inserted += stats["inserted"]
            total_skipped  += stats["skipped"]
            total_invalid  += stats["skipped_invalid"]

        print(f"\n{'='*50}")
        print(f"Import complete.")
        print(f"  Total inserted : {total_inserted}")
        print(f"  Total skipped  : {total_skipped}")
        if total_invalid:
            print(f"  Total invalid  : {total_invalid}  ⚠ these were malformed rows, not expected filtering — worth a look")

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
