"""
backfill_strokes_hr.py — One-time migration script
=====================================================
Adds the stroke_count and heart_rate_max columns and backfills both by
re-fetching every rower result from the live Concept2 API and matching by
workout ID — same approach as backfill_rest_meters.py, and for the same
reason: most historical workouts here were CSV-imported and never had a
local raw_json to read this from.

Both are plain per-session values (no work/rest split like distance/time —
C2 doesn't report rest-period strokes or a separate rest heart rate), so
there's no equivalent of total_distance_meters/total_time_seconds here and
no pace/PB impact to worry about.

Unlike badges and journeys, Insights milestones aren't "earned once and
locked" — they're computed fresh from the database on every page load, so
there's nothing to retroactively correct here once the columns are filled.

Run once inside the container:
    docker compose exec row-tracker python3 backfill_strokes_hr.py

Safe to run multiple times — the ALTER TABLE is skipped if a column already
exists, and rows are only updated where a value actually changes.
"""

import logging
from sqlalchemy import text

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)


def _add_column_if_missing(db, column, ddl_type="INTEGER"):
    cols = [row[1] for row in db.session.execute(text("PRAGMA table_info(workouts)")).fetchall()]
    if column in cols:
        logger.info(f"{column} column already exists — skipping ALTER TABLE.")
        return
    db.session.execute(text(f"ALTER TABLE workouts ADD COLUMN {column} {ddl_type}"))
    db.session.commit()
    logger.info(f"Added {column} column.")


def _fetch_all_values(app):
    """Re-fetch every rower result from the live C2 API. Returns {c2_id: (stroke_count, heart_rate_max)}."""
    from c2_api import C2ApiClient

    client = C2ApiClient(
        client_id     = app.config.get("C2_CLIENT_ID", ""),
        client_secret = app.config.get("C2_CLIENT_SECRET", ""),
        refresh_token = app.config.get("C2_REFRESH_TOKEN", ""),
    )
    if not client.is_configured():
        raise RuntimeError("C2 credentials not configured — cannot backfill from the live API.")

    raw_results = client.get_results(since_date=None)
    if client.last_error:
        raise RuntimeError(f"C2 API fetch failed: {client.last_error}")

    values = {}
    for r in raw_results:
        strokes = r.get("stroke_count") or None
        hr_max = (r.get("heart_rate") or {}).get("max") or None
        values[r["id"]] = (int(strokes) if strokes else None, int(hr_max) if hr_max else None)
    return values


def _backfill_values(db, Workout, app):
    values_by_id = _fetch_all_values(app)
    logger.info(f"Fetched {len(values_by_id)} rower results from the live C2 API.")

    workouts = Workout.query.filter_by(workout_type="rower").all()
    logger.info(f"Matching against {len(workouts)} local rower workouts.")

    updated = skipped = not_found = 0
    for w in workouts:
        if w.id not in values_by_id:
            not_found += 1
            continue
        strokes, hr_max = values_by_id[w.id]
        changed = False
        if w.stroke_count != strokes:
            w.stroke_count = strokes
            changed = True
        if w.heart_rate_max != hr_max:
            w.heart_rate_max = hr_max
            changed = True
        if changed:
            updated += 1
        else:
            skipped += 1

    db.session.commit()
    logger.info(f"Values backfilled. Updated: {updated}  Skipped: {skipped}  Not found in live API: {not_found}")
    return updated


def run_backfill():
    from app import create_app
    from models import db, Workout

    app = create_app()
    with app.app_context():
        _add_column_if_missing(db, "stroke_count")
        _add_column_if_missing(db, "heart_rate_max")
        _backfill_values(db, Workout, app)
        logger.info("Backfill complete.")


if __name__ == "__main__":
    run_backfill()
