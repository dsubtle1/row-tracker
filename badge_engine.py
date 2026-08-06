"""
badge_engine.py — Phase 3A
Evaluates all badge conditions against the local database.
Called after every C2 sync and via the on-demand API endpoint.
Once a badge is earned (earned_date set), it is never re-evaluated.
"""

import logging
from collections import defaultdict
from datetime import date, timedelta
from sqlalchemy import func, and_, extract
from models import db, Workout, PersonalBest, Badge, WodHistory

logger = logging.getLogger(__name__)

# Minimum planned WOD days in a calendar month for Iron Month to be
# meaningful — otherwise a couple of visits with nothing missed would
# trivially qualify.
IRON_MONTH_MIN_PLANNED_SESSIONS = 20

# ---------------------------------------------------------------------------
# Badge definitions
# Each entry: (badge_key, badge_name, badge_desc)
# The check function is registered separately below.
# ---------------------------------------------------------------------------

BADGE_DEFINITIONS = [
    # Performance
    ("sub_2_06_pace",   "Sub-2:06 Pacer",     "Averaged sub-2:06/500m in a single workout"),
    ("sub_2_00_pace",   "Sub-2:00 Pacer",     "Averaged sub-2:00/500m in a single workout"),
    ("sub_1_55_pace",   "Sub-1:55 Pacer",     "Averaged sub-1:55/500m in a single workout"),
    ("pb_crusher",      "PB Crusher",         "Improved any PB by more than 5 seconds in one session"),
    ("2k_legend",       "2k Legend",          "Completed a 2,000m test piece"),
    ("10k_club",        "10k Club",           "Rowed 10,000m in a single workout"),
    ("half_marathon",   "Half Marathoner",    "Rowed 21,097m in a single session"),
    # Volume
    ("first_100k",      "First 100k",         "Lifetime metres crossed 100,000"),
    ("quarter_million", "Quarter Million",    "250,000 lifetime metres"),
    ("half_million",    "Half Million",       "500,000 lifetime metres"),
    ("one_million",     "One Million",        "1,000,000 lifetime metres — elite territory"),
    ("century_month",   "Century Month",      "100,000 metres in a single calendar month"),
    # Consistency
    ("week_warrior",    "Week Warrior",       "5 workouts in any 7-day window"),
    ("iron_month",      "Iron Month",         "No missed planned session days in a calendar month"),
    ("streak_30",       "30-Day Streak",      "30 consecutive days with at least one workout"),
    # Efficiency
    ("technique_gain",  "Technique Gain",     "Same pace as 6 months ago but 3+ SPM lower stroke rate"),
    ("load_master",     "Load Master",        "CAWR stayed in the optimal 0.8–1.3 zone for 4 consecutive weeks"),
]


# ---------------------------------------------------------------------------
# Seed badges table with all definitions (run once on startup / migration)
# ---------------------------------------------------------------------------

def seed_badges():
    """Insert badge rows that don't exist yet. Safe to call repeatedly."""
    for badge_key, badge_name, badge_desc in BADGE_DEFINITIONS:
        existing = Badge.query.filter_by(badge_key=badge_key).first()
        if not existing:
            db.session.add(Badge(
                badge_key=badge_key,
                badge_name=badge_name,
                badge_desc=badge_desc,
            ))
    db.session.commit()
    logger.info("Badge definitions seeded.")


# ---------------------------------------------------------------------------
# Individual check functions
# Each returns (earned: bool, workout_id: int|None)
# ---------------------------------------------------------------------------

def _check_sub_2_06_pace():
    w = Workout.query.filter(Workout.avg_pace_seconds < 126).first()
    return (True, w.id) if w else (False, None)

def _check_sub_2_00_pace():
    w = Workout.query.filter(Workout.avg_pace_seconds < 120).first()
    return (True, w.id) if w else (False, None)

def _check_sub_1_55_pace():
    w = Workout.query.filter(Workout.avg_pace_seconds < 115).first()
    return (True, w.id) if w else (False, None)

def _check_pb_crusher():
    """Any PB improvement > 5 seconds."""
    pb = PersonalBest.query.filter(
        PersonalBest.previous_value != None,
        PersonalBest.previous_value - PersonalBest.value_seconds > 5
    ).first()
    return (True, pb.workout_id) if pb else (False, None)

def _check_2k_legend():
    """Any workout at exactly 2000m."""
    w = Workout.query.filter(Workout.distance_meters == 2000).first()
    return (True, w.id) if w else (False, None)

def _check_10k_club():
    w = Workout.query.filter(Workout.distance_meters >= 10000).first()
    return (True, w.id) if w else (False, None)

def _check_half_marathon():
    w = Workout.query.filter(Workout.distance_meters >= 21097).first()
    return (True, w.id) if w else (False, None)

def _check_first_100k():
    total = db.session.query(func.sum(Workout.distance_meters)).scalar() or 0
    if total >= 100_000:
        # Find the workout that pushed it over
        w = _find_milestone_workout(100_000)
        return (True, w.id if w else None)
    return (False, None)

def _check_quarter_million():
    total = db.session.query(func.sum(Workout.distance_meters)).scalar() or 0
    if total >= 250_000:
        w = _find_milestone_workout(250_000)
        return (True, w.id if w else None)
    return (False, None)

def _check_half_million():
    total = db.session.query(func.sum(Workout.distance_meters)).scalar() or 0
    if total >= 500_000:
        w = _find_milestone_workout(500_000)
        return (True, w.id if w else None)
    return (False, None)

def _check_one_million():
    total = db.session.query(func.sum(Workout.distance_meters)).scalar() or 0
    if total >= 1_000_000:
        w = _find_milestone_workout(1_000_000)
        return (True, w.id if w else None)
    return (False, None)

def _find_milestone_workout(target_metres):
    """Walk workouts in date order to find the one that crossed a cumulative target."""
    workouts = Workout.query.order_by(Workout.workout_date.asc()).all()
    cumulative = 0
    for w in workouts:
        cumulative += w.distance_meters
        if cumulative >= target_metres:
            return w
    return None

def _check_century_month():
    """100,000 metres in any single calendar month."""
    result = db.session.query(
        extract('year', Workout.workout_date).label('yr'),
        extract('month', Workout.workout_date).label('mo'),
        func.sum(Workout.distance_meters).label('total')
    ).group_by('yr', 'mo').having(func.sum(Workout.distance_meters) >= 100_000).first()
    return (True, None) if result else (False, None)

def _check_week_warrior():
    """5 workouts in any rolling 7-day window."""
    workouts = Workout.query.order_by(Workout.workout_date.asc()).all()
    dates = [w.workout_date for w in workouts]
    for i, d in enumerate(dates):
        window_end = d + timedelta(days=6)
        count = sum(1 for x in dates if d <= x <= window_end)
        if count >= 5:
            return (True, None)
    return (False, None)

def _check_iron_month():
    """
    Iron Month: every planned session (WodHistory row) in a calendar month
    was completed — genuinely no missed planned days, not a workout-count
    proxy. Requires at least IRON_MONTH_MIN_PLANNED_SESSIONS planned days
    in the month so a handful of visits can't trivially qualify.

    If a day has more than one WodHistory row (e.g. "Generate another"
    was used), the latest one generated that day is treated as the plan
    for that day — matching get_or_create_today()'s "today's WOD" semantics.
    """
    rows = WodHistory.query.order_by(
        WodHistory.generated_date.asc(), WodHistory.id.asc()
    ).all()
    if not rows:
        return (False, None)

    latest_by_day = {}
    for row in rows:
        latest_by_day[row.generated_date] = row

    by_month = defaultdict(list)
    for day, row in latest_by_day.items():
        by_month[(day.year, day.month)].append(row)

    for month_rows in by_month.values():
        if len(month_rows) < IRON_MONTH_MIN_PLANNED_SESSIONS:
            continue
        if all(row.completed for row in month_rows):
            return (True, None)

    return (False, None)

def _check_streak_30():
    """30 consecutive calendar days each with at least one workout."""
    workouts = Workout.query.order_by(Workout.workout_date.asc()).all()
    if not workouts:
        return (False, None)
    active_days = sorted(set(w.workout_date for w in workouts))
    streak = 1
    for i in range(1, len(active_days)):
        if (active_days[i] - active_days[i - 1]).days == 1:
            streak += 1
            if streak >= 30:
                return (True, None)
        else:
            streak = 1
    return (False, None)

def _check_technique_gain():
    """
    Same pace as 6 months ago but 3+ SPM lower stroke rate.
    Compares 28-day average (recent) vs 28-day average (6 months ago ±14 days).
    """
    today = date.today()
    recent_start = today - timedelta(days=28)
    old_end = today - timedelta(days=168)       # ~6 months
    old_start = old_end - timedelta(days=28)

    recent = Workout.query.filter(
        Workout.workout_date >= recent_start,
        Workout.avg_pace_seconds != None,
        Workout.avg_stroke_rate != None,
    ).all()

    old = Workout.query.filter(
        Workout.workout_date >= old_start,
        Workout.workout_date <= old_end,
        Workout.avg_pace_seconds != None,
        Workout.avg_stroke_rate != None,
    ).all()

    if not recent or not old:
        return (False, None)

    recent_pace = sum(w.avg_pace_seconds for w in recent) / len(recent)
    recent_spm  = sum(w.avg_stroke_rate  for w in recent) / len(recent)
    old_pace    = sum(w.avg_pace_seconds for w in old)    / len(old)
    old_spm     = sum(w.avg_stroke_rate  for w in old)    / len(old)

    # Pace within 3 seconds AND stroke rate dropped 3+ SPM
    pace_similar = abs(recent_pace - old_pace) <= 3
    spm_dropped  = (old_spm - recent_spm) >= 3

    return (True, None) if (pace_similar and spm_dropped) else (False, None)

def _check_load_master():
    """
    CAWR in optimal zone (0.8–1.3) for 4 consecutive complete weeks.
    Computes weekly metres for each ISO week in the data, then checks runs.
    """
    workouts = Workout.query.order_by(Workout.workout_date.asc()).all()
    if not workouts:
        return (False, None)

    # Build dict: iso_week_key -> total metres
    from collections import defaultdict
    weekly = defaultdict(int)
    for w in workouts:
        iso = w.workout_date.isocalendar()
        weekly[(iso[0], iso[1])] += w.distance_meters

    keys = sorted(weekly.keys())
    if len(keys) < 4:
        return (False, None)

    # Need at least 5 weeks of data to compute a 28-day chronic average
    consecutive = 0
    for i in range(4, len(keys)):
        acute    = weekly[keys[i]]
        chronic  = sum(weekly[keys[j]] for j in range(i - 4, i)) / 4
        if chronic == 0:
            consecutive = 0
            continue
        cawr = acute / chronic
        if 0.8 <= cawr <= 1.3:
            consecutive += 1
            if consecutive >= 4:
                return (True, None)
        else:
            consecutive = 0

    return (False, None)


# ---------------------------------------------------------------------------
# Check function registry — maps badge_key -> check function
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Badge icons — one distinct emoji per badge, shown instead of a generic
# medal so the grid reads as 17 different achievements, not 17 copies of
# the same icon.
# ---------------------------------------------------------------------------

BADGE_ICONS = {
    "sub_2_06_pace":   "💨",
    "sub_2_00_pace":   "⚡",
    "sub_1_55_pace":   "🚀",
    "pb_crusher":      "💥",
    "2k_legend":       "🏆",
    "10k_club":        "🎽",
    "half_marathon":   "🏔️",
    "first_100k":      "🌊",
    "quarter_million": "🚣",
    "half_million":    "⚓",
    "one_million":     "🐋",
    "century_month":   "📆",
    "week_warrior":    "⚔️",
    "iron_month":      "🛡️",
    "streak_30":       "🔥",
    "technique_gain":  "🎯",
    "load_master":     "⚖️",
}


CHECK_FUNCTIONS = {
    "sub_2_06_pace":   _check_sub_2_06_pace,
    "sub_2_00_pace":   _check_sub_2_00_pace,
    "sub_1_55_pace":   _check_sub_1_55_pace,
    "pb_crusher":      _check_pb_crusher,
    "2k_legend":       _check_2k_legend,
    "10k_club":        _check_10k_club,
    "half_marathon":   _check_half_marathon,
    "first_100k":      _check_first_100k,
    "quarter_million": _check_quarter_million,
    "half_million":    _check_half_million,
    "one_million":     _check_one_million,
    "century_month":   _check_century_month,
    "week_warrior":    _check_week_warrior,
    "iron_month":      _check_iron_month,
    "streak_30":       _check_streak_30,
    "technique_gain":  _check_technique_gain,
    "load_master":     _check_load_master,
}


# ---------------------------------------------------------------------------
# Main evaluation runner
# ---------------------------------------------------------------------------

def evaluate_badges():
    """
    Evaluate all unearned badges. Returns a list of newly awarded badge keys.
    Safe to call repeatedly — already-earned badges are skipped.
    """
    newly_awarded = []

    badges = Badge.query.filter(Badge.earned_date == None).all()

    for badge in badges:
        check_fn = CHECK_FUNCTIONS.get(badge.badge_key)
        if not check_fn:
            logger.warning(f"No check function registered for badge key: {badge.badge_key}")
            continue

        try:
            earned, workout_id = check_fn()
        except Exception as e:
            logger.error(f"Badge check failed for {badge.badge_key}: {e}")
            continue

        if earned:
            badge.earned_date = date.today()
            badge.workout_id  = workout_id
            newly_awarded.append(badge.badge_key)
            logger.info(f"Badge awarded: {badge.badge_name}")

    if newly_awarded:
        db.session.commit()

    return newly_awarded


# ---------------------------------------------------------------------------
# Progress toward locked badges
# Only badges with a single clear numeric target get a progress bar — the
# rest (pace thresholds, PB Crusher, Iron Month, Technique Gain, Load
# Master) don't reduce to a meaningful "current / target" the way a
# distance or streak count does, so they stay a plain "Locked" label.
# ---------------------------------------------------------------------------

def _make_lifetime_progress(target):
    def fn():
        total = db.session.query(func.sum(Workout.distance_meters)).scalar() or 0
        return {"current": total, "target": target}
    return fn

def _make_best_session_progress(target):
    def fn():
        best = db.session.query(func.max(Workout.distance_meters)).scalar() or 0
        return {"current": best, "target": target}
    return fn

def _progress_century_month():
    rows = db.session.query(
        extract('year', Workout.workout_date).label('yr'),
        extract('month', Workout.workout_date).label('mo'),
        func.sum(Workout.distance_meters).label('total')
    ).group_by('yr', 'mo').all()
    best = max((r.total for r in rows), default=0)
    return {"current": best, "target": 100_000}

def _progress_week_warrior():
    workouts = Workout.query.order_by(Workout.workout_date.asc()).all()
    dates = [w.workout_date for w in workouts]
    best = 0
    for d in dates:
        window_end = d + timedelta(days=6)
        count = sum(1 for x in dates if d <= x <= window_end)
        best = max(best, count)
    return {"current": best, "target": 5}

def _progress_streak_30():
    workouts = Workout.query.order_by(Workout.workout_date.asc()).all()
    if not workouts:
        return {"current": 0, "target": 30}
    active_days = sorted(set(w.workout_date for w in workouts))
    longest = streak = 1
    for i in range(1, len(active_days)):
        streak = streak + 1 if (active_days[i] - active_days[i - 1]).days == 1 else 1
        longest = max(longest, streak)
    return {"current": longest, "target": 30}

PROGRESS_FUNCTIONS = {
    "first_100k":      _make_lifetime_progress(100_000),
    "quarter_million": _make_lifetime_progress(250_000),
    "half_million":    _make_lifetime_progress(500_000),
    "one_million":     _make_lifetime_progress(1_000_000),
    "century_month":   _progress_century_month,
    "10k_club":        _make_best_session_progress(10_000),
    "half_marathon":   _make_best_session_progress(21_097),
    "week_warrior":    _progress_week_warrior,
    "streak_30":       _progress_streak_30,
}

def get_badge_progress(badge_key):
    """{'current', 'target', 'pct'} for measurable locked badges, else None."""
    fn = PROGRESS_FUNCTIONS.get(badge_key)
    if not fn:
        return None
    try:
        progress = fn()
        progress["pct"] = min(100, round(progress["current"] / progress["target"] * 100, 1))
        return progress
    except Exception as e:
        logger.error(f"Badge progress calc failed for {badge_key}: {e}")
        return None
