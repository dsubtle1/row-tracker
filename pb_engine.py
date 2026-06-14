"""
Personal Bests Engine
======================
Recalculates all PBs from scratch by querying the workouts table.
Called after every CSV import and every C2 API sync.

PB categories (matching C2 standard):
  Fixed distance : 100m, 500m, 1000m, 2000m, 5000m, 10000m
  Time-based     : 30min, 60min
"""

from models import db, Workout, PersonalBest

# --------------------------------------------------------------------------- #
#  Category definitions                                                         #
# --------------------------------------------------------------------------- #

DISTANCE_CATEGORIES = {
    "100m":    100,
    "500m":    500,
    "1000m":   1000,
    "2000m":   2000,
    "5000m":   5000,
    "10000m":  10000,
}

TIME_CATEGORIES = {
    "30min": 30 * 60,   # seconds
    "60min": 60 * 60,
}


# --------------------------------------------------------------------------- #
#  Helpers                                                                      #
# --------------------------------------------------------------------------- #

def _best_for_exact_distance(target_meters: int) -> Workout | None:
    """
    Find the fastest workout with distance_meters exactly equal to target.
    Returns the Workout with the lowest time_seconds.
    """
    return (
        Workout.query
        .filter(
            Workout.workout_type == "rower",
            Workout.distance_meters == target_meters,
            Workout.time_seconds.isnot(None),
        )
        .order_by(Workout.time_seconds.asc())
        .first()
    )


def _best_for_time_piece(target_seconds: int) -> Workout | None:
    """
    Find the workout with time_seconds exactly equal to target and highest distance.
    Returns the Workout with the greatest distance_meters.
    """
    return (
        Workout.query
        .filter(
            Workout.workout_type == "rower",
            Workout.time_seconds == target_seconds,
            Workout.distance_meters.isnot(None),
        )
        .order_by(Workout.distance_meters.desc())
        .first()
    )


def _upsert_pb(category: str, value_seconds: int, value_meters, workout: Workout) -> None:
    """
    Insert or update the PersonalBest row for a given category.
    Stores previous_value for delta display.
    """
    existing = PersonalBest.query.filter_by(category=category).first()

    if existing is None:
        pb = PersonalBest(
            category       = category,
            value_seconds  = value_seconds,
            value_meters   = value_meters,
            workout_id     = workout.id,
            achieved_date  = workout.workout_date,
            previous_value = None,
        )
        db.session.add(pb)
    else:
        # Only update if this is genuinely better
        is_better = False
        if value_meters is not None:
            # Time piece: higher metres = better
            is_better = (existing.value_meters is None or value_meters > existing.value_meters)
        else:
            # Distance piece: lower seconds = better
            is_better = (existing.value_seconds is None or value_seconds < existing.value_seconds)

        if is_better:
            existing.previous_value = existing.value_seconds
            existing.value_seconds  = value_seconds
            existing.value_meters   = value_meters
            existing.workout_id     = workout.id
            existing.achieved_date  = workout.workout_date


# --------------------------------------------------------------------------- #
#  Public API                                                                   #
# --------------------------------------------------------------------------- #

def recalculate_all_pbs() -> None:
    """
    Recalculate all personal bests from scratch.
    Clears existing PB rows and rebuilds from the workouts table.
    Safe to call repeatedly — idempotent.
    """
    # Clear existing PBs
    PersonalBest.query.delete()
    db.session.commit()

    # Fixed-distance PBs
    for category, meters in DISTANCE_CATEGORIES.items():
        best = _best_for_exact_distance(meters)
        if best is not None:
            _upsert_pb(
                category      = category,
                value_seconds = best.time_seconds,
                value_meters  = None,
                workout       = best,
            )

    # Time-piece PBs
    for category, seconds in TIME_CATEGORIES.items():
        best = _best_for_time_piece(seconds)
        if best is not None:
            _upsert_pb(
                category      = category,
                value_seconds = seconds,
                value_meters  = best.distance_meters,
                workout       = best,
            )

    db.session.commit()
