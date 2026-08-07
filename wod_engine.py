"""
wod_engine.py — Rule-based Workout of the Day generator.

Periodization logic:
  - Looks at last 7 days of workouts
  - Determines next session type from target weekly distribution
  - Applies CAWR modifier (high load → easier; low load → quality work)
  - Pace targets derived from 2k PB in personal_bests table

No Claude API key required. AI-assisted mode is Build 2B (feature-flagged).
"""

from __future__ import annotations

import calendar
import logging
import random
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Optional

from sqlalchemy import func

from models import db, PersonalBest, Workout, WodHistory

logger = logging.getLogger(__name__)


# ── Zone offsets (seconds / 500m above 2k pace) ──────────────────────────

ZONE_OFFSETS = {
    "UT2": (24, 28),   # Aerobic base
    "UT1": (16, 20),   # Aerobic power
    "AT":  ( 8, 12),   # Threshold
    "TR":  ( 4,  6),   # Transport
    "AN":  ( 0,  3),   # Anaerobic
    "Max": ( 0,  0),   # At or below 2k pace
}

# ── Target weekly distribution (per 5 sessions) ──────────────────────────

TARGET_DISTRIBUTION = {
    "steady_state": 2,
    "interval":     1,
    "threshold":    1,
    "long":         1,   # alternates with "test" — engine handles rotation
}

# Minimum days between test pieces (2k, 5k)
TEST_PIECE_COOLDOWN_DAYS = 14


# ── Dataclass for a structured WOD ───────────────────────────────────────

@dataclass
class WodSpec:
    wod_type:       str           # steady_state / interval / threshold / long / test
    title:          str
    structure_key:  str           # key into WOD_LIBRARY
    intervals:      list[dict]    # list of {label, meters, seconds, type: work|rest}
    pace_zone:      str
    target_pace_seconds: int
    target_pace_str: str
    warm_up:        str
    cool_down:      str
    coaching_notes: str
    total_work_meters: int
    total_work_seconds: int

    def to_dict(self) -> dict:
        return {
            "wod_type":             self.wod_type,
            "title":                self.title,
            "structure_key":        self.structure_key,
            "intervals":            self.intervals,
            "pace_zone":            self.pace_zone,
            "target_pace_seconds":  self.target_pace_seconds,
            "target_pace_str":      self.target_pace_str,
            "warm_up":              self.warm_up,
            "cool_down":            self.cool_down,
            "coaching_notes":       self.coaching_notes,
            "total_work_meters":    self.total_work_meters,
            "total_work_seconds":   self.total_work_seconds,
        }


# ── WOD Library definitions ───────────────────────────────────────────────
# Each entry is a callable that accepts (pace_seconds_by_zone) and returns
# the intervals list + metadata.

def _fmt_pace(seconds: int) -> str:
    m, s = divmod(int(seconds), 60)
    return f"{m}:{s:02d}"


def _work(label: str, meters: int = 0, seconds: int = 0) -> dict:
    return {"label": label, "meters": meters, "seconds": seconds, "type": "work"}


def _rest(label: str, seconds: int) -> dict:
    return {"label": label, "meters": 0, "seconds": seconds, "type": "rest"}


WOD_LIBRARY = {

    # ── Intervals ────────────────────────────────────────────────────────

    "intervals_short": {
        "title":       "8 × 500m",
        "wod_type":    "interval",
        "pace_zone":   "AN",
        "coaching":    "Drive hard off the catch. These are short — commit to the pace from stroke one. "
                       "Keep your split consistent across all 8 reps; avoid going out too hot.",
        "build": lambda z: (
            [item for _ in range(8) for item in [
                _work("500m", meters=500),
                _rest("2:00 rest", seconds=120),
            ]][:-1],   # drop trailing rest
            8 * 500,
            0,
        ),
    },

    "intervals_medium": {
        "title":       "6 × 750m",
        "wod_type":    "interval",
        "pace_zone":   "TR",
        "coaching":    "Aim for negative splits — the last rep should be your fastest. "
                       "Focus on connecting your drive through the handle at the finish.",
        "build": lambda z: (
            [item for _ in range(6) for item in [
                _work("750m", meters=750),
                _rest("2:30 rest", seconds=150),
            ]][:-1],
            6 * 750,
            0,
        ),
    },

    "intervals_long": {
        "title":       "4 × 1000m",
        "wod_type":    "interval",
        "pace_zone":   "AT",
        "coaching":    "These are long enough to require pacing discipline. "
                       "Settle into rhythm by 200m and hold. The rest is generous — use it fully.",
        "build": lambda z: (
            [item for _ in range(4) for item in [
                _work("1000m", meters=1000),
                _rest("3:00 rest", seconds=180),
            ]][:-1],
            4 * 1000,
            0,
        ),
    },

    "fixed_ratio": {
        "title":       "4 × 4 min",
        "wod_type":    "interval",
        "pace_zone":   "AT",
        "coaching":    "Time-based intervals remove the temptation to watch the distance count down. "
                       "Lock in your split and focus on technique under fatigue.",
        "build": lambda z: (
            [item for _ in range(4) for item in [
                _work("4 min", seconds=240),
                _rest("2:00 rest", seconds=120),
            ]][:-1],
            0,
            4 * 240,
        ),
    },

    "pyramid": {
        "title":       "Pyramid 250–1000–250",
        "wod_type":    "interval",
        "pace_zone":   "TR",
        "coaching":    "Each rep is a different challenge. Build confidence on the short pieces, "
                       "then hold form through the 1000m peak. The descending reps should feel controlled.",
        "build": lambda z: (
            [
                _work("250m",  meters=250),  _rest("1:00 rest", seconds=60),
                _work("500m",  meters=500),  _rest("1:00 rest", seconds=60),
                _work("750m",  meters=750),  _rest("1:00 rest", seconds=60),
                _work("1000m", meters=1000), _rest("1:00 rest", seconds=60),
                _work("750m",  meters=750),  _rest("1:00 rest", seconds=60),
                _work("500m",  meters=500),  _rest("1:00 rest", seconds=60),
                _work("250m",  meters=250),
            ],
            250+500+750+1000+750+500+250,
            0,
        ),
    },

    "pete_plan_4x2k": {
        "title":       "Pete Plan — 4 × 2000m",
        "wod_type":    "interval",
        "pace_zone":   "TR",
        "coaching":    "The Pete Plan staple. Treat each 2k as a standalone effort — "
                       "consistent split, strong finish. The 4-minute rest keeps quality high.",
        "build": lambda z: (
            [item for _ in range(4) for item in [
                _work("2000m", meters=2000),
                _rest("4:00 rest", seconds=240),
            ]][:-1],
            4 * 2000,
            0,
        ),
    },

    "pete_plan_6x1k": {
        "title":       "Pete Plan — 6 × 1000m",
        "wod_type":    "interval",
        "pace_zone":   "TR",
        "coaching":    "Six reps gives you room to find rhythm. The goal is consistency — "
                       "every rep within 2 seconds of your target split.",
        "build": lambda z: (
            [item for _ in range(6) for item in [
                _work("1000m", meters=1000),
                _rest("3:00 rest", seconds=180),
            ]][:-1],
            6 * 1000,
            0,
        ),
    },

    # ── Steady State ─────────────────────────────────────────────────────

    "steady_state_40": {
        "title":       "Steady State 40 min",
        "wod_type":    "steady_state",
        "pace_zone":   "UT2",
        "coaching":    "This is aerobic base work — resist the urge to push. "
                       "If you can't hold a conversation, you're going too hard. "
                       "Focus on long strokes and a clean catch.",
        "build": lambda z: (
            [_work("40 min steady state", seconds=2400)],
            0,
            2400,
        ),
    },

    "steady_state_50": {
        "title":       "Steady State 50 min",
        "wod_type":    "steady_state",
        "pace_zone":   "UT2",
        "coaching":    "Settle in early. The first 10 minutes should feel almost too easy — "
                       "that's the right pace. Use this session to dial in your stroke mechanics.",
        "build": lambda z: (
            [_work("50 min steady state", seconds=3000)],
            0,
            3000,
        ),
    },

    "steady_state_60": {
        "title":       "Steady State 60 min",
        "wod_type":    "steady_state",
        "pace_zone":   "UT2",
        "coaching":    "Long aerobic session. Your main job is to stay aerobic the entire time. "
                       "Break it mentally into 20-minute thirds — the last third is where fitness is built.",
        "build": lambda z: (
            [_work("60 min steady state", seconds=3600)],
            0,
            3600,
        ),
    },

    "technique": {
        "title":       "Technique — 20 min at 18 SPM",
        "wod_type":    "steady_state",
        "pace_zone":   "UT2",
        "coaching":    "Rate-capped session. Hold 18–20 SPM strictly — use a metronome if needed. "
                       "Every stroke should be deliberate: sequence, connection, hang. "
                       "Pace doesn't matter; mechanics do.",
        "build": lambda z: (
            [_work("20 min @ 18 SPM", seconds=1200)],
            0,
            1200,
        ),
    },

    # ── Threshold ────────────────────────────────────────────────────────

    "threshold_3x8": {
        "title":       "Threshold — 3 × 8 min",
        "wod_type":    "threshold",
        "pace_zone":   "AT",
        "coaching":    "Threshold work sits at the uncomfortable middle — hard enough to feel it, "
                       "controlled enough to sustain. Keep your split within 2 seconds of target throughout.",
        "build": lambda z: (
            [item for _ in range(3) for item in [
                _work("8 min", seconds=480),
                _rest("3:00 rest", seconds=180),
            ]][:-1],
            0,
            3 * 480,
        ),
    },

    "threshold_2x12": {
        "title":       "Threshold — 2 × 12 min",
        "wod_type":    "threshold",
        "pace_zone":   "AT",
        "coaching":    "Longer threshold blocks demand more mental discipline than physical. "
                       "Find your pace in the first 2 minutes and don't touch it. "
                       "The second rep should feel harder — that's correct.",
        "build": lambda z: (
            [
                _work("12 min", seconds=720),
                _rest("4:00 rest", seconds=240),
                _work("12 min", seconds=720),
            ],
            0,
            2 * 720,
        ),
    },

    # ── Long ─────────────────────────────────────────────────────────────

    "long_row_60": {
        "title":       "Long Row — 60 min",
        "wod_type":    "long",
        "pace_zone":   "UT1",
        "coaching":    "A proper long row at UT1 — slightly brisker than your usual steady state. "
                       "You should feel the effort but never be gasping. "
                       "This builds aerobic capacity and mental toughness simultaneously.",
        "build": lambda z: (
            [_work("60 min long row", seconds=3600)],
            0,
            3600,
        ),
    },

    "long_row_75": {
        "title":       "Long Row — 75 min",
        "wod_type":    "long",
        "pace_zone":   "UT1",
        "coaching":    "Your longest session. Treat the first 30 minutes as warm-up, "
                       "then find your stride. Split it into three 25-minute blocks mentally. "
                       "The last 15 is where the adaptation happens.",
        "build": lambda z: (
            [_work("75 min long row", seconds=4500)],
            0,
            4500,
        ),
    },

    # ── Test Pieces ──────────────────────────────────────────────────────

    "time_trial_2k": {
        "title":       "Time Trial — 2000m",
        "wod_type":    "test",
        "pace_zone":   "Max",
        "coaching":    "The benchmark. Go out at your target split and hold on. "
                       "The first 500m should feel controlled — resist the adrenaline. "
                       "The last 500m is pure willpower. Leave nothing on the erg.",
        "build": lambda z: (
            [_work("2000m time trial", meters=2000)],
            2000,
            0,
        ),
    },

    "time_trial_5k": {
        "title":       "Time Trial — 5000m",
        "wod_type":    "test",
        "pace_zone":   "Max",
        "coaching":    "Longer than the 2k, so pacing is everything. "
                       "Start 2–3 seconds slower than 2k pace and build through. "
                       "Your goal is an even split or negative split — not a fast first kilometer.",
        "build": lambda z: (
            [_work("5000m time trial", meters=5000)],
            5000,
            0,
        ),
    },
}


# ── Pace targeting ────────────────────────────────────────────────────────

def get_2k_pace_seconds() -> Optional[int]:
    """Return 2k PB pace in seconds/500m, or None if no PB recorded."""
    pb = PersonalBest.query.filter_by(category="2000m").first()
    if pb and pb.value_seconds:
        return pb.value_seconds // 4   # 2k time → 500m split
    # Fall back to nearest distance PB with adjustment
    for cat, factor in [("1000m", 0.52), ("5000m", 0.46)]:
        pb = PersonalBest.query.filter_by(category=cat).first()
        if pb and pb.value_seconds:
            return int(pb.value_seconds * factor)
    return None


def pace_for_zone(zone: str, base_pace_seconds: int) -> int:
    """Return target pace in seconds/500m for a given zone."""
    lo, hi = ZONE_OFFSETS[zone]
    offset = (lo + hi) // 2
    return base_pace_seconds + offset


def zones_from_pb(base_pace: int) -> dict[str, int]:
    return {zone: pace_for_zone(zone, base_pace) for zone in ZONE_OFFSETS}


# ── Periodization logic ───────────────────────────────────────────────────

def _recent_wod_types(days: int = 7) -> dict[str, int]:
    """Count WOD types completed in the last `days` days."""
    since = date.today() - timedelta(days=days)
    rows = (
        WodHistory.query
        .filter(WodHistory.generated_date >= since)
        .filter(WodHistory.completed == True)   # noqa: E712
        .all()
    )
    counts: dict[str, int] = {k: 0 for k in TARGET_DISTRIBUTION}
    for row in rows:
        t = row.wod_type
        if t in counts:
            counts[t] += 1
        elif t == "test":
            counts["long"] = counts.get("long", 0) + 1
    return counts


def _last_test_piece_date() -> Optional[date]:
    """Return date of most recent completed test piece, or None."""
    row = (
        WodHistory.query
        .filter(WodHistory.wod_type == "test")
        .filter(WodHistory.completed == True)   # noqa: E712
        .order_by(WodHistory.generated_date.desc())
        .first()
    )
    return row.generated_date if row else None


def _current_cawr() -> Optional[float]:
    """Return the most recent CAWR value (today or yesterday)."""
    today = date.today()
    rows = (
        db.session.query(Workout.workout_date, func.sum(Workout.distance_meters))
        .filter_by(workout_type="rower")
        .group_by(Workout.workout_date)
        .order_by(Workout.workout_date.asc())
        .all()
    )
    if not rows:
        return None

    by_date = {r[0]: r[1] for r in rows}
    first_day = min(by_date.keys())

    all_days = []
    d = first_day
    while d <= today:
        all_days.append((d, by_date.get(d, 0)))
        d += timedelta(days=1)

    if len(all_days) < 42:
        return None

    acute_window   = [m for _, m in all_days[-7:]]
    chronic_window = [m for _, m in all_days[-42:]]
    acute_avg   = sum(acute_window)   / 7
    chronic_avg = sum(chronic_window) / 42
    if chronic_avg == 0:
        return None
    return round(acute_avg / chronic_avg, 3)


def _choose_session_type(cawr: Optional[float]) -> str:
    """
    Choose next session type based on:
    1. What's under-represented in last 7 days vs target distribution
    2. CAWR modifier — high load biases toward steady state
    """
    recent = _recent_wod_types(days=7)

    # CAWR modifier
    if cawr is not None:
        if cawr > 1.3:
            # High load — force steady state
            return "steady_state"
        if cawr < 0.8:
            # Under-training — bias toward quality (interval or threshold)
            return random.choice(["interval", "threshold"])

    # Find most under-represented type
    deficits = {}
    for stype, target in TARGET_DISTRIBUTION.items():
        actual = recent.get(stype, 0)
        deficits[stype] = target - actual

    # Check test piece cooldown
    last_test = _last_test_piece_date()
    if last_test and (date.today() - last_test).days < TEST_PIECE_COOLDOWN_DAYS:
        deficits.pop("long", None)
        # Replace long/test slot with steady state
        deficits["steady_state"] = deficits.get("steady_state", 0) + 1

    # Pick the most overdue type; break ties randomly
    max_deficit = max(deficits.values())
    candidates = [t for t, d in deficits.items() if d == max_deficit]
    return random.choice(candidates)


def _pick_wod_key(session_type: str) -> str:
    """Pick a specific WOD from the library for the given session type."""
    by_type = {
        "interval":    ["intervals_short", "intervals_medium", "intervals_long",
                        "fixed_ratio", "pyramid", "pete_plan_4x2k", "pete_plan_6x1k"],
        "steady_state": ["steady_state_40", "steady_state_50", "steady_state_60", "technique"],
        "threshold":   ["threshold_3x8", "threshold_2x12"],
        "long":        ["long_row_60", "long_row_75"],
        "test":        ["time_trial_2k", "time_trial_5k"],
    }
    options = by_type.get(session_type, ["steady_state_40"])

    # Avoid repeating the same WOD as yesterday
    yesterday = date.today() - timedelta(days=1)
    last_wod = (
        WodHistory.query
        .filter(WodHistory.generated_date == yesterday)
        .order_by(WodHistory.id.desc())
        .first()
    )
    last_key = last_wod.wod_json.get("structure_key") if last_wod and last_wod.wod_json else None
    if last_key and last_key in options and len(options) > 1:
        options = [o for o in options if o != last_key]

    return random.choice(options)


# ── AI-assisted coaching narrative (optional, feature-flagged) ───────────

def _apply_ai_coaching(spec: WodSpec, **extra_context) -> None:
    """
    Best-effort: if USE_AI_WOD is on and configured, replace spec's
    warm_up/cool_down/coaching_notes in place with an AI-generated
    narrative. Leaves spec untouched on any failure — the rule-based
    text set by the caller is always the fallback.
    """
    try:
        from ai_coach import generate_coaching_narrative
        result = generate_coaching_narrative({
            "wod_type":           spec.wod_type,
            "title":              spec.title,
            "pace_zone":          spec.pace_zone,
            "target_pace_str":    spec.target_pace_str,
            "total_work_meters":  spec.total_work_meters,
            **extra_context,
        })
    except Exception as e:
        logger.error(f"AI coaching narrative unavailable: {e}")
        return

    if result:
        spec.warm_up        = result["warm_up"]
        spec.cool_down      = result["cool_down"]
        spec.coaching_notes = result["coaching_notes"]


# ── Main generator ────────────────────────────────────────────────────────

def generate_wod(force_type: Optional[str] = None) -> WodSpec:
    """
    Generate today's WOD. Returns a WodSpec.
    If force_type is provided, skip periodization and use that type directly.
    """
    base_pace = get_2k_pace_seconds()
    if base_pace is None:
        # Fallback: assume a reasonable 2k pace of 2:10/500m (130s) if no PB data
        base_pace = 130

    zones = zones_from_pb(base_pace)
    cawr  = _current_cawr()

    session_type = force_type or _choose_session_type(cawr)
    wod_key      = _pick_wod_key(session_type)
    defn         = WOD_LIBRARY[wod_key]

    intervals, total_meters, total_seconds = defn["build"](zones)

    zone      = defn["pace_zone"]
    target_ps = zones[zone]
    target_str = _fmt_pace(target_ps)

    spec = WodSpec(
        wod_type            = defn["wod_type"],
        title               = defn["title"],
        structure_key       = wod_key,
        intervals           = intervals,
        pace_zone           = zone,
        target_pace_seconds = target_ps,
        target_pace_str     = target_str,
        warm_up             = (
            "Row easy for 10 minutes at UT2 pace, building stroke rate gradually. "
            "Include 4–6 pick-up strokes at target pace in the final 2 minutes to prime the system."
        ),
        cool_down           = (
            "10 minutes easy paddling at low rate (18–20 SPM). "
            "Focus on long, relaxed strokes. Let your heart rate return below 120 bpm before stopping."
        ),
        coaching_notes      = defn["coaching"],
        total_work_meters   = total_meters,
        total_work_seconds  = total_seconds,
    )

    last_test = _last_test_piece_date()
    _apply_ai_coaching(
        spec,
        cawr=cawr,
        days_since_last_test=(date.today() - last_test).days if last_test else None,
        recent_session_types=_recent_wod_types(days=7),
    )

    return spec


def save_wod(spec: WodSpec) -> WodHistory:
    """Persist a WodSpec to the wod_history table and return the row."""
    row = WodHistory(
        generated_date = date.today(),
        wod_type       = spec.wod_type,
        wod_json       = spec.to_dict(),
        completed      = False,
    )
    db.session.add(row)
    db.session.commit()
    return row


def get_or_create_today() -> tuple[WodHistory, bool]:
    """
    Return (WodHistory row, created).
    If today's WOD already exists, return it. Otherwise generate and save.
    """
    today = date.today()
    existing = (
        WodHistory.query
        .filter(WodHistory.generated_date == today)
        .order_by(WodHistory.id.desc())
        .first()
    )
    if existing:
        return existing, False

    spec = generate_wod()
    row  = save_wod(spec)
    return row, True


def build_month_calendar(year: int, month: int) -> list[list[dict]]:
    """
    Return a Mon-Sun week grid for the given year/month.

    Each cell is a dict:
        {"date": date, "day": int, "in_month": bool,
         "status": "none" | "pending" | "completed"}

    Days outside the requested month (padding to complete the first/last
    week) always get status "none" and in_month=False.
    """
    first_day = date(year, month, 1)
    last_day = date(year, month, calendar.monthrange(year, month)[1])

    rows = (
        WodHistory.query
        .filter(WodHistory.generated_date >= first_day, WodHistory.generated_date <= last_day)
        .order_by(WodHistory.id.asc())
        .all()
    )
    # A day can have multiple rows if the WOD was regenerated — the latest
    # (highest id) row wins, matching get_or_create_today()'s convention.
    latest_by_date: dict[date, WodHistory] = {}
    for row in rows:
        latest_by_date[row.generated_date] = row

    weeks = []
    for week in calendar.Calendar(firstweekday=0).monthdatescalendar(year, month):
        week_cells = []
        for d in week:
            in_month = d.month == month
            row = latest_by_date.get(d) if in_month else None
            if row is None:
                status = "none"
            else:
                status = "completed" if row.completed else "pending"
            week_cells.append({"date": d, "day": d.day, "in_month": in_month, "status": status})
        weeks.append(week_cells)
    return weeks


def get_wod_for_date(target_date: date) -> Optional[WodHistory]:
    """Return the most recently created WodHistory row for target_date, or None."""
    return (
        WodHistory.query
        .filter(WodHistory.generated_date == target_date)
        .order_by(WodHistory.id.desc())
        .first()
    )


# ── Random WOD Generator ──────────────────────────────────────────────────
#
# Intensity:   light (1–15 min) / medium (15–30 min) / heavy (30+ min)
# Effort:      low / medium / high  (maps to pace zone, self-judged)
# Workout type: steady_state / intervals / threshold / surprise
#
# Effort → pace zone mapping:
#   low    → UT2 (aerobic base)
#   medium → UT1 / AT (aerobic power / threshold)
#   high   → TR / AN (transport / anaerobic)

EFFORT_ZONE_MAP = {
    "low":    "UT2",
    "medium": "AT",
    "high":   "TR",
}

# Library of random WOD templates keyed by (intensity, wod_type)
# Each entry: dict with title, coaching, build fn → (intervals, total_m, total_s)

RANDOM_WOD_TEMPLATES = {

    # ── LIGHT (1–15 min work) ─────────────────────────────────────────────

    ("light", "steady_state"): [
        {
            "title": "Easy 10",
            "coaching": "A short aerobic flush. Stay well below threshold — long strokes, relaxed grip. "
                        "This is recovery work, not fitness work. Enjoy the movement.",
            "build": lambda z: ([_work("10 min easy", seconds=600)], 0, 600),
        },
        {
            "title": "Easy 15",
            "coaching": "Keep your effort conversational throughout. Focus on ratio — "
                        "slow the recovery and let the drive feel powerful by contrast.",
            "build": lambda z: ([_work("15 min easy", seconds=900)], 0, 900),
        },
    ],

    ("light", "intervals"): [
        {
            "title": "4 × 1 min / 1 min rest",
            "coaching": "Short and punchy. Each minute should feel controlled but purposeful. "
                        "Full rest between — quality over quantity.",
            "build": lambda z: (
                [item for _ in range(4) for item in [
                    _work("1 min", seconds=60), _rest("1:00 rest", seconds=60),
                ]][:-1], 0, 4 * 60,
            ),
        },
        {
            "title": "6 × 90 sec / 90 sec rest",
            "coaching": "Aim for a consistent split across all six reps. "
                        "The rest matches the work — don't rush it.",
            "build": lambda z: (
                [item for _ in range(6) for item in [
                    _work("90 sec", seconds=90), _rest("90 sec rest", seconds=90),
                ]][:-1], 0, 6 * 90,
            ),
        },
        {
            "title": "3 × 500m / 2 min rest",
            "coaching": "Three quality pieces. Hit your target split on rep one and hold it. "
                        "These should feel hard but controlled.",
            "build": lambda z: (
                [item for _ in range(3) for item in [
                    _work("500m", meters=500), _rest("2:00 rest", seconds=120),
                ]][:-1], 3 * 500, 0,
            ),
        },
    ],

    ("light", "threshold"): [
        {
            "title": "2 × 4 min / 2 min rest",
            "coaching": "Short threshold pieces — sustainable hard effort. "
                        "Find your pace in the first minute and lock it in.",
            "build": lambda z: (
                [
                    _work("4 min", seconds=240), _rest("2:00 rest", seconds=120),
                    _work("4 min", seconds=240),
                ], 0, 2 * 240,
            ),
        },
    ],

    # ── MEDIUM (15–30 min work) ───────────────────────────────────────────

    ("medium", "steady_state"): [
        {
            "title": "Steady State 20 min",
            "coaching": "Settle in and hold a comfortable pace. This is aerobic base — "
                        "resist any urge to push. Focus on clean technique throughout.",
            "build": lambda z: ([_work("20 min steady state", seconds=1200)], 0, 1200),
        },
        {
            "title": "Steady State 25 min",
            "coaching": "A solid aerobic session. Keep your split steady and your stroke long. "
                        "If your rate creeps up, consciously slow the recovery.",
            "build": lambda z: ([_work("25 min steady state", seconds=1500)], 0, 1500),
        },
        {
            "title": "Steady State 30 min",
            "coaching": "The classic aerobic base session. Comfortable, controlled, consistent. "
                        "Your heart rate should plateau and stay there after the first 5 minutes.",
            "build": lambda z: ([_work("30 min steady state", seconds=1800)], 0, 1800),
        },
    ],

    ("medium", "intervals"): [
        {
            "title": "5 × 3 min / 2 min rest",
            "coaching": "Find your rhythm in rep one and replicate it across all five. "
                        "The 2-minute rest is enough — resist the urge to extend it.",
            "build": lambda z: (
                [item for _ in range(5) for item in [
                    _work("3 min", seconds=180), _rest("2:00 rest", seconds=120),
                ]][:-1], 0, 5 * 180,
            ),
        },
        {
            "title": "4 × 2000m / 3 min rest",
            "coaching": "Long interval work. Each 2k should be a controlled effort — "
                        "aim for even splits across all four reps.",
            "build": lambda z: (
                [item for _ in range(4) for item in [
                    _work("2000m", meters=2000), _rest("3:00 rest", seconds=180),
                ]][:-1], 4 * 2000, 0,
            ),
        },
        {
            "title": "Ladder: 1–2–3–2–1 min",
            "coaching": "The ladder keeps it interesting. Build into the 3-minute peak, "
                        "then hold your form on the way down. Rest equals work.",
            "build": lambda z: (
                [
                    _work("1 min",  seconds=60),  _rest("1:00 rest",  seconds=60),
                    _work("2 min",  seconds=120), _rest("2:00 rest",  seconds=120),
                    _work("3 min",  seconds=180), _rest("3:00 rest",  seconds=180),
                    _work("2 min",  seconds=120), _rest("2:00 rest",  seconds=120),
                    _work("1 min",  seconds=60),
                ], 0, (1+2+3+2+1) * 60,
            ),
        },
    ],

    ("medium", "threshold"): [
        {
            "title": "3 × 8 min / 3 min rest",
            "coaching": "Classic threshold work. Sustainable hard effort — you should be working "
                        "but not red-lining. The 3-minute rest lets you go again at quality.",
            "build": lambda z: (
                [item for _ in range(3) for item in [
                    _work("8 min", seconds=480), _rest("3:00 rest", seconds=180),
                ]][:-1], 0, 3 * 480,
            ),
        },
        {
            "title": "2 × 12 min / 4 min rest",
            "coaching": "Two long threshold pieces. The first 3 minutes of each rep will feel hard — "
                        "stay patient and your body will settle into the effort.",
            "build": lambda z: (
                [
                    _work("12 min", seconds=720), _rest("4:00 rest", seconds=240),
                    _work("12 min", seconds=720),
                ], 0, 2 * 720,
            ),
        },
    ],

    # ── HEAVY (30+ min work) ──────────────────────────────────────────────

    ("heavy", "steady_state"): [
        {
            "title": "Steady State 40 min",
            "coaching": "Long aerobic base work. This is the foundation of your fitness — "
                        "protect the pace zone, keep the rate honest, and focus on ratio.",
            "build": lambda z: ([_work("40 min steady state", seconds=2400)], 0, 2400),
        },
        {
            "title": "Steady State 50 min",
            "coaching": "A long aerobic session. Settle in early, find your rhythm, and stay there. "
                        "The goal is sustained aerobic stimulus — not pace.",
            "build": lambda z: ([_work("50 min steady state", seconds=3000)], 0, 3000),
        },
        {
            "title": "Steady State 60 min",
            "coaching": "The full long row. Keep it easy and aerobic throughout. "
                        "If you feel good at 40 minutes, resist the urge to push — "
                        "the adaptation comes from duration, not intensity.",
            "build": lambda z: ([_work("60 min steady state", seconds=3600)], 0, 3600),
        },
    ],

    ("heavy", "intervals"): [
        {
            "title": "8 × 500m / 2 min rest",
            "coaching": "Classic high-volume interval set. Commit to your target split from rep one. "
                        "Keep splits consistent — rep 8 should match rep 1.",
            "build": lambda z: (
                [item for _ in range(8) for item in [
                    _work("500m", meters=500), _rest("2:00 rest", seconds=120),
                ]][:-1], 8 * 500, 0,
            ),
        },
        {
            "title": "6 × 1000m / 3 min rest",
            "coaching": "Six quality kilometres. These are long enough to demand pacing discipline. "
                        "Settle into each rep by the 200m mark and hold.",
            "build": lambda z: (
                [item for _ in range(6) for item in [
                    _work("1000m", meters=1000), _rest("3:00 rest", seconds=180),
                ]][:-1], 6 * 1000, 0,
            ),
        },
        {
            "title": "Pete Plan — 4 × 2000m / 4 min rest",
            "coaching": "The Pete Plan anchor session. Each 2k is a standalone piece — "
                        "consistent split, strong last 500m. The 4-minute rest keeps quality high.",
            "build": lambda z: (
                [item for _ in range(4) for item in [
                    _work("2000m", meters=2000), _rest("4:00 rest", seconds=240),
                ]][:-1], 4 * 2000, 0,
            ),
        },
    ],

    ("heavy", "threshold"): [
        {
            "title": "4 × 8 min / 3 min rest",
            "coaching": "Four threshold pieces — serious aerobic work. "
                        "Stay at a sustainable hard effort and focus on holding form as fatigue builds.",
            "build": lambda z: (
                [item for _ in range(4) for item in [
                    _work("8 min", seconds=480), _rest("3:00 rest", seconds=180),
                ]][:-1], 0, 4 * 480,
            ),
        },
        {
            "title": "60 min Threshold Pyramid",
            "coaching": "Build through the pyramid — each step harder than the last, "
                        "then back down. Stay in control throughout.",
            "build": lambda z: (
                [
                    _work("10 min", seconds=600), _rest("2:00 rest", seconds=120),
                    _work("15 min", seconds=900), _rest("2:00 rest", seconds=120),
                    _work("20 min", seconds=1200), _rest("2:00 rest", seconds=120),
                    _work("15 min", seconds=900), _rest("2:00 rest", seconds=120),
                    _work("10 min", seconds=600),
                ], 0, (10+15+20+15+10) * 60,
            ),
        },
    ],
}

# "Surprise me" pools by intensity
SURPRISE_TYPES = {
    "light":  ["steady_state", "intervals", "threshold"],
    "medium": ["steady_state", "intervals", "threshold"],
    "heavy":  ["steady_state", "intervals", "threshold"],
}


def generate_random_wod(
    intensity: str,       # light / medium / heavy
    effort: str,          # low / medium / high
    wod_type: str,        # steady_state / intervals / threshold / surprise
    notes: str = "",
) -> WodSpec:
    """
    Generate a random WOD from user-specified parameters.
    Does not use periodization logic — purely parameter-driven.
    """
    # Resolve "surprise" to a concrete type
    if wod_type == "surprise":
        wod_type = random.choice(SURPRISE_TYPES.get(intensity, ["steady_state"]))

    # Normalise wod_type key (UI sends "intervals", library key is "intervals")
    key = (intensity, wod_type)
    templates = RANDOM_WOD_TEMPLATES.get(key)

    # Fallback if combination doesn't exist
    if not templates:
        key = (intensity, "steady_state")
        templates = RANDOM_WOD_TEMPLATES.get(key, [])

    if not templates:
        raise ValueError(f"No templates found for intensity={intensity}, wod_type={wod_type}")

    template = random.choice(templates)

    # Pace zone from effort level
    zone     = EFFORT_ZONE_MAP.get(effort, "UT2")
    base_pace = get_2k_pace_seconds() or 130
    zones    = zones_from_pb(base_pace)
    target_ps  = zones[zone]
    target_str = _fmt_pace(target_ps)

    intervals, total_meters, total_seconds = template["build"](zones)

    # Effort-aware coaching prefix
    effort_prefix = {
        "low":    "Keep this session easy and aerobic. ",
        "medium": "Work at a sustainably hard effort — challenging but controlled. ",
        "high":   "Push the pace — this should feel hard. ",
    }.get(effort, "")

    coaching = effort_prefix + template["coaching"]
    if notes:
        coaching += f"\n\nYour note: {notes}"

    # Warm-up and cool-down scale with intensity
    if intensity == "light":
        warm_up   = "5 minutes easy paddling to loosen up. A few long strokes to find your posture."
        cool_down = "5 minutes easy. Focus on breathing and letting your rate drop naturally."
    elif intensity == "medium":
        warm_up   = "8 minutes easy rowing at UT2, building gradually. Finish with 3–4 strokes at target pace."
        cool_down = "8 minutes easy paddling, rate 18–20. Let heart rate return below 120 bpm."
    else:
        warm_up   = (
            "10 minutes easy at UT2 pace, building stroke rate gradually. "
            "Include 4–6 pick-up strokes at target pace in the final 2 minutes."
        )
        cool_down = (
            "10 minutes easy paddling at low rate (18–20 SPM). "
            "Long, relaxed strokes. Let heart rate return below 120 bpm before stopping."
        )

    # Map wod_type to WodHistory wod_type field
    wod_type_map = {
        "steady_state": "steady_state",
        "intervals":    "interval",
        "threshold":    "threshold",
    }

    spec = WodSpec(
        wod_type            = wod_type_map.get(wod_type, "steady_state"),
        title               = template["title"],
        structure_key       = f"random_{intensity}_{wod_type}",
        intervals           = intervals,
        pace_zone           = zone,
        target_pace_seconds = target_ps,
        target_pace_str     = target_str,
        warm_up             = warm_up,
        cool_down           = cool_down,
        coaching_notes      = coaching,
        total_work_meters   = total_meters,
        total_work_seconds  = total_seconds,
    )

    _apply_ai_coaching(spec, intensity=intensity, effort=effort, user_notes=notes)

    return spec
