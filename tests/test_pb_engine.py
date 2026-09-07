"""
Tests for pb_engine.py — personal best recalculation.

Key business rules under test:
  - Distance categories require an EXACT distance match (not >=).
  - Time categories require an EXACT time match, best = most distance.
  - Non-"rower" workout types are excluded.
  - recalculate_all_pbs() is a full wipe-and-rebuild, not an incremental update.
"""

from datetime import date, timedelta

from models import PersonalBest
from pb_engine import recalculate_all_pbs, progression_for_category


def test_empty_db_produces_no_pbs(app_ctx):
    recalculate_all_pbs()
    assert PersonalBest.query.count() == 0


def test_distance_pb_requires_exact_match(app_ctx, make_workout):
    # 2001m should NOT count toward the 2000m category.
    make_workout(id=1, distance_meters=2001, time_seconds=480)
    recalculate_all_pbs()

    pb = PersonalBest.query.filter_by(category="2000m").first()
    assert pb is None


def test_distance_pb_picks_fastest_of_exact_matches(app_ctx, make_workout):
    make_workout(id=1, distance_meters=2000, time_seconds=480)  # slower
    make_workout(id=2, distance_meters=2000, time_seconds=420)  # faster — should win
    make_workout(id=3, distance_meters=2000, time_seconds=450)
    recalculate_all_pbs()

    pb = PersonalBest.query.filter_by(category="2000m").first()
    assert pb is not None
    assert pb.value_seconds == 420
    assert pb.workout_id == 2
    assert pb.value_meters is None


def test_time_piece_requires_exact_time_match(app_ctx, make_workout):
    # 29:59 is not an exact match for the 30min category.
    make_workout(id=1, time_seconds=30 * 60 - 1, distance_meters=7500)
    recalculate_all_pbs()

    pb = PersonalBest.query.filter_by(category="30min").first()
    assert pb is None


def test_time_piece_picks_greatest_distance_of_exact_matches(app_ctx, make_workout):
    thirty_min = 30 * 60
    make_workout(id=1, time_seconds=thirty_min, distance_meters=7400)
    make_workout(id=2, time_seconds=thirty_min, distance_meters=7600)  # further — should win
    recalculate_all_pbs()

    pb = PersonalBest.query.filter_by(category="30min").first()
    assert pb is not None
    assert pb.value_meters == 7600
    assert pb.workout_id == 2
    assert pb.value_seconds == thirty_min


def test_non_rower_workouts_are_excluded(app_ctx, make_workout):
    make_workout(id=1, distance_meters=2000, time_seconds=420, workout_type="bike")
    recalculate_all_pbs()

    assert PersonalBest.query.filter_by(category="2000m").first() is None


def test_recalculate_is_idempotent(app_ctx, make_workout):
    make_workout(id=1, distance_meters=2000, time_seconds=420)

    recalculate_all_pbs()
    first_value = PersonalBest.query.filter_by(category="2000m").first().value_seconds

    recalculate_all_pbs()
    second = PersonalBest.query.filter_by(category="2000m").first()

    assert PersonalBest.query.count() == 1
    assert second.value_seconds == first_value


def test_recalculate_tracks_previous_value_on_genuine_improvement(app_ctx, make_workout):
    make_workout(id=1, distance_meters=2000, time_seconds=450)
    recalculate_all_pbs()

    make_workout(id=2, distance_meters=2000, time_seconds=420)
    recalculate_all_pbs()

    pb = PersonalBest.query.filter_by(category="2000m").first()
    assert pb.value_seconds == 420
    assert pb.previous_value == 450
    assert pb.delta_seconds == 30


def test_recalculate_does_not_overwrite_a_better_existing_pb(app_ctx, make_workout):
    """A slower additional workout must not clobber the standing best."""
    make_workout(id=1, distance_meters=2000, time_seconds=420)
    recalculate_all_pbs()

    make_workout(id=2, distance_meters=2000, time_seconds=450)
    recalculate_all_pbs()

    pb = PersonalBest.query.filter_by(category="2000m").first()
    assert pb.value_seconds == 420
    assert pb.workout_id == 1
    assert pb.previous_value is None


def test_recalculate_removes_pb_for_category_with_no_remaining_match(app_ctx, make_workout):
    w = make_workout(id=1, distance_meters=2000, time_seconds=420)
    recalculate_all_pbs()
    assert PersonalBest.query.filter_by(category="2000m").first() is not None

    from models import db
    db.session.delete(w)
    db.session.commit()
    recalculate_all_pbs()

    assert PersonalBest.query.filter_by(category="2000m").first() is None


# --------------------------------------------------------------------------- #
#  progression_for_category() — record-progression staircase                  #
# --------------------------------------------------------------------------- #

def test_progression_unknown_category_returns_empty(app_ctx):
    assert progression_for_category("not-a-real-category") == []


def test_progression_empty_history_returns_empty(app_ctx):
    assert progression_for_category("2000m") == []


def test_progression_distance_category_only_includes_genuine_improvements(app_ctx, make_workout):
    today = date.today()
    make_workout(id=1, distance_meters=2000, time_seconds=460, workout_date=today - timedelta(days=30))
    make_workout(id=2, distance_meters=2000, time_seconds=470, workout_date=today - timedelta(days=20))  # slower — not a new PB
    make_workout(id=3, distance_meters=2000, time_seconds=440, workout_date=today - timedelta(days=10))  # improvement

    points = progression_for_category("2000m")
    assert [p["value_seconds"] for p in points] == [460, 440]
    assert points[0]["date"] == (today - timedelta(days=30)).isoformat()
    assert points[1]["date"] == (today - timedelta(days=10)).isoformat()
    assert "value_formatted" in points[0]


def test_progression_ignores_non_exact_distance_matches(app_ctx, make_workout):
    make_workout(id=1, distance_meters=2001, time_seconds=440)
    assert progression_for_category("2000m") == []


def test_progression_time_category_only_includes_genuine_improvements(app_ctx, make_workout):
    today = date.today()
    make_workout(id=1, time_seconds=30 * 60, distance_meters=7400, workout_date=today - timedelta(days=20))
    make_workout(id=2, time_seconds=30 * 60, distance_meters=7300, workout_date=today - timedelta(days=10))  # shorter — not an improvement
    make_workout(id=3, time_seconds=30 * 60, distance_meters=7500, workout_date=today - timedelta(days=5))   # improvement

    points = progression_for_category("30min")
    assert [p["value_meters"] for p in points] == [7400, 7500]


def test_progression_is_chronological_regardless_of_id_order(app_ctx, make_workout):
    today = date.today()
    make_workout(id=2, distance_meters=2000, time_seconds=450, workout_date=today - timedelta(days=5))
    make_workout(id=1, distance_meters=2000, time_seconds=460, workout_date=today - timedelta(days=15))

    points = progression_for_category("2000m")
    assert [p["date"] for p in points] == [
        (today - timedelta(days=15)).isoformat(),
        (today - timedelta(days=5)).isoformat(),
    ]
