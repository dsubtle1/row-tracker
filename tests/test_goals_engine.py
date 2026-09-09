"""
Tests for goals_engine.py — custom user-defined targets, computed live
against workouts/personal_bests the same way badge and journey progress
already are.
"""

from datetime import date, timedelta

from models import db, PersonalBest
from goals_engine import (
    create_goal, active_goals, goal_progress, parse_time_str,
    PB_CATEGORY_CHOICES,
)


# ---------------------------------------------------------------------------
# parse_time_str
# ---------------------------------------------------------------------------

def test_parse_time_str_parses_minutes_and_seconds():
    assert parse_time_str("7:00") == 420


def test_parse_time_str_handles_empty_and_malformed():
    assert parse_time_str("") is None
    assert parse_time_str("not-a-time") is None


# ---------------------------------------------------------------------------
# create_goal / active_goals
# ---------------------------------------------------------------------------

def test_create_and_list_active_goal(app_ctx):
    goal = create_goal("distance", "Row 1,000,000m this year", 1_000_000)
    assert goal.id is not None
    assert goal.start_date == date.today()
    assert goal in active_goals()


def test_archived_goal_excluded_from_active_list(app_ctx):
    goal = create_goal("distance", "Test goal", 1000)
    goal.archived = True
    db.session.commit()
    assert goal not in active_goals()


# ---------------------------------------------------------------------------
# goal_progress — distance goals
# ---------------------------------------------------------------------------

def test_distance_goal_progress_counts_metres_since_start_date(app_ctx, make_workout):
    goal = create_goal("distance", "Row 5000m", 5000)
    make_workout(id=1, distance_meters=3000, time_seconds=700, workout_date=date.today())

    progress = goal_progress(goal)
    assert progress["current"] == 3000
    assert progress["target"] == 5000
    assert progress["pct"] == 60.0
    assert progress["hit"] is False


def test_distance_goal_ignores_workouts_before_start_date(app_ctx, make_workout):
    goal = create_goal("distance", "Row 5000m", 5000)
    goal.start_date = date.today()
    db.session.commit()
    make_workout(id=1, distance_meters=3000, time_seconds=700, workout_date=date.today() - timedelta(days=5))

    progress = goal_progress(goal)
    assert progress["current"] == 0


def test_distance_goal_marks_achieved_once_hit(app_ctx, make_workout):
    goal = create_goal("distance", "Row 2000m", 2000)
    make_workout(id=1, distance_meters=2000, time_seconds=480, workout_date=date.today())

    assert goal.achieved_date is None
    progress = goal_progress(goal)
    assert progress["hit"] is True
    assert goal.achieved_date == date.today()


# ---------------------------------------------------------------------------
# goal_progress — PB-pace goals
# ---------------------------------------------------------------------------

def test_pb_pace_goal_no_pb_yet(app_ctx):
    goal = create_goal("pb_pace", "Break 7:00 for 2k", 420, pb_category="2000m")
    progress = goal_progress(goal)
    assert progress["current"] is None
    assert progress["hit"] is False
    assert progress["current_display"] == "No PB yet"


def test_pb_pace_goal_distance_category_lower_is_better(app_ctx):
    goal = create_goal("pb_pace", "Break 7:00 for 2k", 420, pb_category="2000m")
    db.session.add(PersonalBest(category="2000m", value_seconds=410))
    db.session.commit()

    progress = goal_progress(goal)
    assert progress["hit"] is True   # 410s is faster (lower) than 420s target
    assert goal.achieved_date == date.today()


def test_pb_pace_goal_distance_category_not_yet_hit(app_ctx):
    goal = create_goal("pb_pace", "Break 7:00 for 2k", 420, pb_category="2000m")
    db.session.add(PersonalBest(category="2000m", value_seconds=450))
    db.session.commit()

    progress = goal_progress(goal)
    assert progress["hit"] is False
    assert goal.achieved_date is None


def test_pb_pace_goal_time_category_higher_is_better(app_ctx):
    goal = create_goal("pb_pace", "Break 10000m in 30min", 10_000, pb_category="30min")
    db.session.add(PersonalBest(category="30min", value_meters=10_500))
    db.session.commit()

    progress = goal_progress(goal)
    assert progress["hit"] is True   # 10,500m exceeds the 10,000m target


def test_pb_category_choices_cover_all_standard_categories():
    assert set(PB_CATEGORY_CHOICES) == {
        "100m", "500m", "1000m", "2000m", "5000m", "10000m", "30min", "60min",
    }
