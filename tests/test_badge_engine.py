"""
Tests for badge_engine.py — badge condition checks and the evaluation runner.

Each check function is tested in isolation by writing directly to the
Workout/PersonalBest tables (badge_engine doesn't care how the data got
there), plus a few tests of evaluate_badges()'s orchestration behavior.
"""

from datetime import date, timedelta

import pytest

import badge_engine
from badge_engine import (
    seed_badges,
    evaluate_badges,
    BADGE_DEFINITIONS,
    CHECK_FUNCTIONS,
    _check_sub_2_06_pace,
    _check_pb_crusher,
    _check_first_100k,
    _check_century_month,
    _check_week_warrior,
    _check_iron_month,
    _check_streak_30,
    _check_technique_gain,
    _check_load_master,
)
from models import db, Badge, PersonalBest, WodHistory


# ---------------------------------------------------------------------------
# Pace badges — boundary conditions
# ---------------------------------------------------------------------------

def test_sub_2_06_pace_boundary_not_earned_at_exactly_126(app_ctx, make_workout):
    make_workout(id=1, avg_pace_seconds=126)
    earned, workout_id, achieved_date = _check_sub_2_06_pace()
    assert earned is False


def test_sub_2_06_pace_earned_below_126(app_ctx, make_workout, days_ago):
    w = make_workout(id=1, avg_pace_seconds=125, workout_date=days_ago(10))
    earned, workout_id, achieved_date = _check_sub_2_06_pace()
    assert earned is True
    assert workout_id == 1
    assert achieved_date == w.workout_date


# ---------------------------------------------------------------------------
# pb_crusher — depends on PersonalBest.previous_value, not on pb_engine
# ---------------------------------------------------------------------------

def test_pb_crusher_requires_more_than_five_seconds(app_ctx, make_workout):
    w = make_workout(id=1, distance_meters=2000, time_seconds=420)
    db.session.add(PersonalBest(
        category="2000m", value_seconds=420, previous_value=425,  # only 5s — not enough
        workout_id=w.id, achieved_date=w.workout_date,
    ))
    db.session.commit()

    earned, _, _ = _check_pb_crusher()
    assert earned is False


def test_pb_crusher_earned_over_five_seconds(app_ctx, make_workout, days_ago):
    w = make_workout(id=1, distance_meters=2000, time_seconds=420, workout_date=days_ago(3))
    db.session.add(PersonalBest(
        category="2000m", value_seconds=420, previous_value=426,  # 6s improvement
        workout_id=w.id, achieved_date=w.workout_date,
    ))
    db.session.commit()

    earned, workout_id, achieved_date = _check_pb_crusher()
    assert earned is True
    assert workout_id == w.id
    assert achieved_date == w.workout_date


# ---------------------------------------------------------------------------
# Milestone badges — cumulative walk in date order
# ---------------------------------------------------------------------------

def test_first_100k_not_earned_below_threshold(app_ctx, make_workout):
    make_workout(id=1, distance_meters=50_000, time_seconds=10_000)
    earned, _, _ = _check_first_100k()
    assert earned is False


def test_first_100k_finds_crossing_workout(app_ctx, make_workout, days_ago):
    make_workout(id=1, distance_meters=60_000, time_seconds=10_000, workout_date=days_ago(2))
    crossing = make_workout(id=2, distance_meters=60_000, time_seconds=10_000, workout_date=days_ago(1))
    earned, workout_id, achieved_date = _check_first_100k()
    assert earned is True
    assert workout_id == crossing.id  # cumulative 120k crosses 100k on the 2nd workout
    assert achieved_date == crossing.workout_date


# ---------------------------------------------------------------------------
# century_month / iron_month — per-calendar-month aggregates
# ---------------------------------------------------------------------------

def test_century_month_not_earned_when_split_across_months(app_ctx, make_workout):
    make_workout(id=1, distance_meters=60_000, time_seconds=10_000, workout_date=date(2025, 1, 31))
    make_workout(id=2, distance_meters=60_000, time_seconds=10_000, workout_date=date(2025, 2, 1))
    earned, _, _ = _check_century_month()
    assert earned is False


def test_century_month_earned_within_single_month(app_ctx, make_workout):
    make_workout(id=1, distance_meters=60_000, time_seconds=10_000, workout_date=date(2025, 3, 5))
    crossing = make_workout(id=2, distance_meters=60_000, time_seconds=10_000, workout_date=date(2025, 3, 20))
    earned, _, achieved_date = _check_century_month()
    assert earned is True
    assert achieved_date == crossing.workout_date  # the day the month's total crossed 100k


def test_iron_month_not_earned_below_planned_session_threshold(app_ctx):
    start = date(2025, 4, 1)
    for i in range(19):
        db.session.add(WodHistory(generated_date=start + timedelta(days=i),
                                   wod_type="steady_state", completed=True))
    db.session.commit()
    assert _check_iron_month()[0] is False


def test_iron_month_earned_when_every_planned_day_is_completed(app_ctx):
    start = date(2025, 4, 1)
    for i in range(20):
        db.session.add(WodHistory(generated_date=start + timedelta(days=i),
                                   wod_type="steady_state", completed=True))
    db.session.commit()
    earned, _, achieved_date = _check_iron_month()
    assert earned is True
    assert achieved_date == start + timedelta(days=19)  # last planned day of the month


def test_iron_month_not_earned_with_a_missed_planned_day(app_ctx):
    start = date(2025, 4, 1)
    for i in range(20):
        completed = not (i == 10)  # one missed session in an otherwise full month
        db.session.add(WodHistory(generated_date=start + timedelta(days=i),
                                   wod_type="steady_state", completed=completed))
    db.session.commit()
    assert _check_iron_month()[0] is False


def test_iron_month_only_actual_workouts_no_longer_count_on_their_own(app_ctx, make_workout):
    """
    The old proxy earned this badge from 20 synced Workout rows alone,
    with no notion of a plan or completion. That must no longer be enough.
    """
    for i in range(20):
        make_workout(id=i + 1, distance_meters=2000, time_seconds=420,
                     workout_date=date(2025, 4, i + 1))
    assert _check_iron_month()[0] is False


def test_iron_month_collapses_same_day_rows_to_the_latest(app_ctx):
    start = date(2025, 6, 1)
    for i in range(19):
        db.session.add(WodHistory(generated_date=start + timedelta(days=i),
                                   wod_type="steady_state", completed=True))
    db.session.commit()

    # Day 20: first WOD generated was skipped, then regenerated and completed.
    last_day = start + timedelta(days=19)
    db.session.add(WodHistory(generated_date=last_day, wod_type="steady_state", completed=False))
    db.session.commit()
    db.session.add(WodHistory(generated_date=last_day, wod_type="steady_state", completed=True))
    db.session.commit()

    assert _check_iron_month()[0] is True


def test_iron_month_regenerating_a_completed_day_into_incomplete_breaks_it(app_ctx):
    start = date(2025, 6, 1)
    for i in range(19):
        db.session.add(WodHistory(generated_date=start + timedelta(days=i),
                                   wod_type="steady_state", completed=True))
    db.session.commit()

    last_day = start + timedelta(days=19)
    db.session.add(WodHistory(generated_date=last_day, wod_type="steady_state", completed=True))
    db.session.commit()
    db.session.add(WodHistory(generated_date=last_day, wod_type="steady_state", completed=False))
    db.session.commit()

    assert _check_iron_month()[0] is False


# ---------------------------------------------------------------------------
# week_warrior — rolling 7-day window
# ---------------------------------------------------------------------------

def test_week_warrior_counts_workouts_within_a_7_day_window(app_ctx, make_workout):
    start = date(2025, 5, 1)
    for i in range(5):
        make_workout(id=i + 1, distance_meters=2000, time_seconds=420, workout_date=start + timedelta(days=i))
    earned, _, achieved_date = _check_week_warrior()
    assert earned is True
    assert achieved_date == start + timedelta(days=4)  # date of the 5th qualifying workout


def test_week_warrior_not_earned_when_spread_too_thin(app_ctx, make_workout):
    start = date(2025, 5, 1)
    # 5 workouts, but spread across 10 days — no 7-day window contains all 5.
    for i, offset in enumerate([0, 3, 6, 9, 12]):
        make_workout(id=i + 1, distance_meters=2000, time_seconds=420, workout_date=start + timedelta(days=offset))
    earned, _, _ = _check_week_warrior()
    assert earned is False


# ---------------------------------------------------------------------------
# streak_30 — consecutive unique calendar days
# ---------------------------------------------------------------------------

def test_streak_30_requires_unbroken_consecutive_days(app_ctx, make_workout):
    start = date(2025, 1, 1)
    for i in range(29):
        make_workout(id=i + 1, distance_meters=2000, time_seconds=420, workout_date=start + timedelta(days=i))
    assert _check_streak_30()[0] is False  # only 29 days

    make_workout(id=30, distance_meters=2000, time_seconds=420, workout_date=start + timedelta(days=29))
    earned, _, achieved_date = _check_streak_30()
    assert earned is True
    assert achieved_date == start + timedelta(days=29)  # day the 30th consecutive day landed


def test_streak_30_resets_on_gap(app_ctx, make_workout):
    start = date(2025, 1, 1)
    for i in range(29):
        make_workout(id=i + 1, distance_meters=2000, time_seconds=420, workout_date=start + timedelta(days=i))
    # gap of one day breaks the streak before it reaches 30
    make_workout(id=30, distance_meters=2000, time_seconds=420, workout_date=start + timedelta(days=30))
    assert _check_streak_30()[0] is False


# ---------------------------------------------------------------------------
# technique_gain — same pace, lower stroke rate, ~6 months apart
# ---------------------------------------------------------------------------

def test_technique_gain_earned_when_spm_drops_at_same_pace(app_ctx, make_workout, days_ago):
    for i in range(3):
        make_workout(id=i + 1, distance_meters=2000, time_seconds=480,
                      avg_pace_seconds=120, avg_stroke_rate=26, workout_date=days_ago(5 + i))
    for i in range(3):
        make_workout(id=i + 10, distance_meters=2000, time_seconds=480,
                      avg_pace_seconds=120, avg_stroke_rate=30, workout_date=days_ago(175 + i))
    earned, _, achieved_date = _check_technique_gain()
    assert earned is True
    assert achieved_date == days_ago(5)  # most recent workout in the "recent" comparison window


def test_technique_gain_not_earned_when_no_spm_drop(app_ctx, make_workout, days_ago):
    for i in range(3):
        make_workout(id=i + 1, distance_meters=2000, time_seconds=480,
                      avg_pace_seconds=120, avg_stroke_rate=26, workout_date=days_ago(5 + i))
    for i in range(3):
        make_workout(id=i + 10, distance_meters=2000, time_seconds=480,
                      avg_pace_seconds=120, avg_stroke_rate=26, workout_date=days_ago(175 + i))
    assert _check_technique_gain()[0] is False


def test_technique_gain_missing_historical_window_not_earned(app_ctx, make_workout, days_ago):
    make_workout(id=1, distance_meters=2000, time_seconds=480,
                 avg_pace_seconds=120, avg_stroke_rate=26, workout_date=days_ago(5))
    assert _check_technique_gain()[0] is False


# ---------------------------------------------------------------------------
# load_master — CAWR in 0.8-1.3 for 4 consecutive weeks
# ---------------------------------------------------------------------------

def test_load_master_earned_with_steady_weekly_load(app_ctx, make_workout):
    start = date(2024, 3, 4)  # a Monday
    for week in range(9):
        make_workout(id=week + 1, distance_meters=10_000, time_seconds=2000,
                      workout_date=start + timedelta(weeks=week))
    earned, _, achieved_date = _check_load_master()
    assert earned is True
    assert achieved_date is not None
    assert achieved_date.weekday() == 6  # Sunday — end of the qualifying ISO week


def test_load_master_not_earned_with_too_little_history(app_ctx, make_workout):
    start = date(2024, 3, 4)
    for week in range(3):
        make_workout(id=week + 1, distance_meters=10_000, time_seconds=2000,
                      workout_date=start + timedelta(weeks=week))
    assert _check_load_master()[0] is False


# ---------------------------------------------------------------------------
# evaluate_badges() — orchestration
# ---------------------------------------------------------------------------

def test_seed_badges_creates_all_definitions_and_is_idempotent(app_ctx):
    seed_badges()
    assert Badge.query.count() == len(BADGE_DEFINITIONS)

    seed_badges()  # calling twice must not duplicate rows
    assert Badge.query.count() == len(BADGE_DEFINITIONS)


def test_evaluate_badges_awards_and_persists(app_ctx, make_workout, days_ago):
    seed_badges()
    workout_date = days_ago(200)
    make_workout(id=1, distance_meters=2000, time_seconds=480, workout_date=workout_date)

    newly_awarded = evaluate_badges()
    assert "2k_legend" in newly_awarded

    badge = Badge.query.filter_by(badge_key="2k_legend").first()
    assert badge.is_earned
    assert badge.workout_id == 1
    # Regression: earned_date must be when the milestone actually happened,
    # not date.today() (the day evaluation ran) — otherwise a bulk-imported
    # history stamps every already-true badge with the same "today" date.
    assert badge.earned_date == workout_date


def test_evaluate_badges_skips_already_earned(app_ctx, make_workout):
    seed_badges()
    make_workout(id=1, distance_meters=2000, time_seconds=480)

    first_pass = evaluate_badges()
    assert "2k_legend" in first_pass

    second_pass = evaluate_badges()
    assert "2k_legend" not in second_pass


def test_evaluate_badges_survives_a_failing_check(app_ctx, monkeypatch):
    seed_badges()

    def _boom():
        raise RuntimeError("simulated failure")

    monkeypatch.setitem(CHECK_FUNCTIONS, "2k_legend", _boom)

    newly_awarded = evaluate_badges()  # must not raise
    assert "2k_legend" not in newly_awarded
    assert Badge.query.filter_by(badge_key="2k_legend").first().earned_date is None


def test_every_badge_definition_has_a_check_function():
    for badge_key, _, _ in BADGE_DEFINITIONS:
        assert badge_key in CHECK_FUNCTIONS, f"missing check function for {badge_key}"
