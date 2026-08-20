"""
backfill_rest_meters.py — One-time migration script
=====================================================
Adds the rest_distance_meters column (light rowing between intervals,
tracked separately by Concept2 as "rest_distance" and never included in
the top-level "distance" field the sync previously read) and backfills it
from raw_json for every workout that has it.

distance_meters / avg_pace_seconds / PBs are untouched — they stay
work-interval-only. rest_distance_meters only feeds Workout.total_distance_meters,
which lifetime/volume totals (badges, journeys, challenges) now use instead.

Because five volume badges and the Holland journey were already earned/completed
under the old work-only totals, this also retroactively corrects their
earned_date/completed_date to the date the (now higher) cumulative total
actually crossed the threshold — otherwise they'd sit dated later than they
should now that the true total is known.

Run once inside the container:
    docker compose exec row-tracker python3 backfill_rest_meters.py

Safe to run multiple times — the ALTER TABLE is skipped if the column
already exists, and rows are only updated where the value actually changes.
"""

import logging
from sqlalchemy import text

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)

# Badges that were already earned under the old work-only cumulative totals
# and need their earned_date/workout_id recomputed against the corrected total.
_VOLUME_MILESTONE_BADGES = {
    "first_100k":      100_000,
    "quarter_million":  250_000,
    "half_million":     500_000,
    "one_million":     1_000_000,
}


def _add_column_if_missing(db):
    cols = [row[1] for row in db.session.execute(text("PRAGMA table_info(workouts)")).fetchall()]
    if "rest_distance_meters" in cols:
        logger.info("rest_distance_meters column already exists — skipping ALTER TABLE.")
        return
    db.session.execute(text("ALTER TABLE workouts ADD COLUMN rest_distance_meters INTEGER"))
    db.session.commit()
    logger.info("Added rest_distance_meters column.")


def _backfill_values(db, Workout):
    workouts = Workout.query.filter(Workout.raw_json.isnot(None)).all()
    logger.info(f"Found {len(workouts)} workouts with raw_json to backfill.")

    updated = skipped = errors = 0
    for w in workouts:
        try:
            raw = w.raw_json
            if not isinstance(raw, dict):
                skipped += 1
                continue
            rest = int(raw.get("rest_distance", 0) or 0)
            if w.rest_distance_meters != rest:
                w.rest_distance_meters = rest
                updated += 1
            else:
                skipped += 1
        except Exception as e:
            logger.error(f"Error processing workout {w.id}: {e}")
            errors += 1

    db.session.commit()
    logger.info(f"Values backfilled. Updated: {updated}  Skipped: {skipped}  Errors: {errors}")
    return updated


def _correct_volume_badge_dates(db, Badge):
    import badge_engine

    for badge_key, target in _VOLUME_MILESTONE_BADGES.items():
        badge = Badge.query.filter_by(badge_key=badge_key).first()
        if not badge or badge.earned_date is None:
            continue
        w = badge_engine._find_milestone_workout(target)
        if w and (w.workout_date != badge.earned_date or w.id != badge.workout_id):
            logger.info(
                f"Correcting {badge_key}: earned_date {badge.earned_date} -> {w.workout_date} "
                f"(workout {badge.workout_id} -> {w.id})"
            )
            badge.earned_date = w.workout_date
            badge.workout_id = w.id

    # century_month: re-derive from the corrected totals the same way the
    # live check does, and only overwrite if it actually moved.
    century = Badge.query.filter_by(badge_key="century_month").first()
    if century and century.earned_date is not None:
        earned, workout_id, achieved_date = badge_engine._check_century_month()
        if earned and achieved_date and achieved_date != century.earned_date:
            logger.info(f"Correcting century_month: earned_date {century.earned_date} -> {achieved_date}")
            century.earned_date = achieved_date
            century.workout_id = workout_id

    db.session.commit()


def _correct_journey_dates(db, Journey, Workout):
    from blueprints.gamification import RHINE_TOTAL_M, HOLLAND_TOTAL_M, ROUTE66_TOTAL_M, TRANSCAN_TOTAL_M

    totals = {
        "rhine":    RHINE_TOTAL_M,
        "holland":  HOLLAND_TOTAL_M,
        "route66":  ROUTE66_TOTAL_M,
        "transcan": TRANSCAN_TOTAL_M,
    }

    for journey in Journey.query.filter_by(completed=True).all():
        target = totals.get(journey.route_key)
        if not target:
            continue
        workouts = (
            Workout.query
            .filter(Workout.workout_date >= journey.start_date, Workout.workout_type == "rower")
            .order_by(Workout.workout_date.asc())
            .all()
        )
        cumulative = 0
        crossed_date = None
        for w in workouts:
            cumulative += w.total_distance_meters
            if cumulative >= target:
                crossed_date = w.workout_date
                break
        if crossed_date and crossed_date != journey.completed_date:
            logger.info(
                f"Correcting journey {journey.route_key}: completed_date "
                f"{journey.completed_date} -> {crossed_date}"
            )
            journey.completed_date = crossed_date

    db.session.commit()


def run_backfill():
    from app import create_app
    from models import db, Workout, Badge, Journey

    app = create_app()
    with app.app_context():
        _add_column_if_missing(db)
        updated = _backfill_values(db, Workout)

        if updated:
            logger.info("Recomputing pace/PBs is unaffected (work-only fields untouched).")

        _correct_volume_badge_dates(db, Badge)
        _correct_journey_dates(db, Journey, Workout)

        logger.info("Running badge evaluation for anything newly qualifying under corrected totals...")
        import badge_engine
        newly_awarded = badge_engine.evaluate_badges()
        if newly_awarded:
            logger.info(f"Newly awarded: {newly_awarded}")
        else:
            logger.info("No new badges newly qualified.")

        logger.info("Backfill complete.")


if __name__ == "__main__":
    run_backfill()
