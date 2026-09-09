"""
Custom Goals Engine
====================
Every target elsewhere in the app is hardcoded (200,000m/quarter,
80,000m/month, 15 workouts/30 days, badge thresholds). This lets the user
set their own — "row 1,000,000m this year," "break 7:00 for 2k by
December" — and computes progress/ETA live, the same pattern already
built for badges (badge_engine.weekly_avg_meters) and journeys, rather
than a snapshot/history table.
"""

from datetime import date, timedelta

from sqlalchemy import func

from models import db, Workout, PersonalBest, CustomGoal
from pb_engine import DISTANCE_CATEGORIES, TIME_CATEGORIES
from badge_engine import weekly_avg_meters

PB_CATEGORY_CHOICES = list(DISTANCE_CATEGORIES) + list(TIME_CATEGORIES)


def parse_time_str(s: str) -> int | None:
    """'M:SS' or 'MM:SS' -> total seconds. None if empty/unparseable."""
    if not s or not s.strip():
        return None
    try:
        minutes_part, seconds_part = s.strip().split(":")
        return int(minutes_part) * 60 + int(float(seconds_part))
    except (ValueError, AttributeError):
        return None


def _fmt_time(seconds: int) -> str:
    m, s = divmod(int(seconds), 60)
    return f"{m}:{s:02d}"


def create_goal(goal_type, label, target_value, pb_category=None, deadline=None):
    goal = CustomGoal(
        goal_type=goal_type,
        label=label,
        target_value=target_value,
        pb_category=pb_category,
        deadline=deadline,
        start_date=date.today(),
    )
    db.session.add(goal)
    db.session.commit()
    return goal


def active_goals():
    return CustomGoal.query.filter_by(archived=False).order_by(CustomGoal.created_at.desc()).all()


def _distance_progress(goal: CustomGoal) -> dict:
    current = db.session.query(func.sum(Workout.total_distance_meters)).filter(
        Workout.workout_date >= goal.start_date,
        Workout.workout_type == "rower",
    ).scalar() or 0

    remaining = max(goal.target_value - current, 0)
    avg = weekly_avg_meters()
    eta = None
    if avg > 0 and remaining > 0:
        eta = (date.today() + timedelta(weeks=remaining / avg)).isoformat()

    return {
        "current": current,
        "target":  goal.target_value,
        "current_display": f"{current:,}m",
        "target_display":  f"{goal.target_value:,}m",
        "pct":     min(100, round(current / goal.target_value * 100, 1)) if goal.target_value else 0,
        "hit":     current >= goal.target_value,
        "eta":     eta,
    }


def _pb_pace_progress(goal: CustomGoal) -> dict:
    """
    For a distance category (100m..10000m), the PB value is total time —
    lower is better, so "hit" means the current PB is at or under target.
    For a time category (30min/60min), the PB value is metres covered —
    higher is better, so "hit" means the current PB is at or over target.
    No ETA — pace improvement doesn't extrapolate from a rolling average
    the way cumulative distance does.
    """
    is_time_based = goal.pb_category in DISTANCE_CATEGORIES   # total time, lower is better
    pb = PersonalBest.query.filter_by(category=goal.pb_category).first()
    current = pb.value_seconds if (pb and is_time_based) else \
              (pb.value_meters if (pb and not is_time_based) else None)

    target_display = _fmt_time(goal.target_value) if is_time_based else f"{goal.target_value:,}m"

    if current is None:
        return {
            "current": None, "target": goal.target_value, "pct": 0, "hit": False, "eta": None,
            "current_display": "No PB yet", "target_display": target_display,
        }

    current_display = _fmt_time(current) if is_time_based else f"{current:,}m"

    if is_time_based:
        hit = current <= goal.target_value
        pct = min(100, round(goal.target_value / current * 100, 1)) if current else 0
    else:
        hit = current >= goal.target_value
        pct = min(100, round(current / goal.target_value * 100, 1)) if goal.target_value else 0

    return {
        "current": current, "target": goal.target_value, "pct": pct, "hit": hit, "eta": None,
        "current_display": current_display, "target_display": target_display,
    }


def goal_progress(goal: CustomGoal) -> dict:
    """
    Progress dict for one goal, marking it achieved (once, like a badge's
    earned_date) the first time this is called after it's been hit.
    """
    progress = _distance_progress(goal) if goal.goal_type == "distance" else _pb_pace_progress(goal)
    if progress["hit"] and not goal.achieved_date:
        goal.achieved_date = date.today()
        db.session.commit()
    return progress
