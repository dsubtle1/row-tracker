"""
backfill_pace_calories.py — One-time migration script
======================================================
Recalculates avg_pace_seconds, total_calories, and avg_stroke_rate
for all existing workouts that have raw_json from the C2 API.

Run once inside the container:
    docker compose exec row-tracker python3 backfill_pace_calories.py

Safe to run multiple times — only updates rows where raw_json is present.
"""

import os
import sys
import logging

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)


def run_backfill():
    from app import create_app
    from models import db, Workout

    app = create_app()

    with app.app_context():
        # Only rows that were synced via API (have raw_json)
        workouts = Workout.query.filter(Workout.raw_json.isnot(None)).all()
        logger.info(f"Found {len(workouts)} workouts with raw_json to backfill.")

        updated   = 0
        skipped   = 0
        errors    = 0

        for w in workouts:
            try:
                raw = w.raw_json
                if not isinstance(raw, dict):
                    skipped += 1
                    continue

                changed = False

                # ── Pace: calculate from time and distance ─────────────
                time_raw   = raw.get("time", 0) or 0
                distance_m = raw.get("distance", 0) or 0
                time_s     = round(time_raw / 10) if time_raw else None

                if time_s and distance_m:
                    new_pace = round((time_s / distance_m) * 500)
                    if w.avg_pace_seconds != new_pace:
                        w.avg_pace_seconds = new_pace
                        changed = True

                # ── Calories: read calories_total ──────────────────────
                calories = raw.get("calories_total") or None
                if calories:
                    calories = int(calories)
                    if w.total_calories != calories:
                        w.total_calories = calories
                        changed = True

                # ── Stroke rate: read stroke_rate ──────────────────────
                stroke_rate = raw.get("stroke_rate") or None
                if stroke_rate:
                    stroke_rate = int(stroke_rate)
                    if w.avg_stroke_rate != stroke_rate:
                        w.avg_stroke_rate = stroke_rate
                        changed = True

                if changed:
                    updated += 1
                else:
                    skipped += 1

            except Exception as e:
                logger.error(f"Error processing workout {w.id}: {e}")
                errors += 1

        db.session.commit()

        logger.info(f"Backfill complete.")
        logger.info(f"  Updated : {updated}")
        logger.info(f"  Skipped : {skipped} (already correct or no raw_json)")
        logger.info(f"  Errors  : {errors}")

        if updated > 0:
            logger.info("Running PB recalculation on updated data...")
            try:
                from pb_engine import recalculate_all_pbs
                recalculate_all_pbs()
                logger.info("PBs recalculated.")
            except Exception as e:
                logger.error(f"PB recalc failed: {e}")


if __name__ == "__main__":
    run_backfill()
