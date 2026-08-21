"""
Insights Engine
===============
Deterministic pattern-spotting across the whole workout history. Each rule
inspects the data, and only returns an insight once the pattern clears a
minimum-sample and significance check — noise never earns a card.

Design note — facts vs phrasing
--------------------------------
Every Insight separates *facts* (the structured numbers a rule computed) from
*phrasing* (the warm headline/detail/recommendation strings). That split is
deliberate: it keeps the rules testable, and it's the seam an optional AI
narrative layer plugs into later (see insights_ai.py) — the AI only ever
rephrases these facts, it never computes or invents a number.

Called on demand by the /insights route. Cheap enough to run per request:
every rule works off the three aggregate columns (pace, stroke rate, distance/
time) already on each workout row — no per-stroke fetch.
"""

from __future__ import annotations

import calendar
import statistics
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Optional

from sqlalchemy import func

from models import db, Workout, PersonalBest


# --------------------------------------------------------------------------- #
#  Insight model                                                               #
# --------------------------------------------------------------------------- #

# Category display order + labels (drives the page's section order).
CATEGORIES = [
    ("timing",     "Timing & Rhythm"),
    ("progress",   "Progress & Trends"),
    ("technique",  "Technique & Efficiency"),
    ("habits",     "Habits"),
    ("milestones", "Milestones"),
]


@dataclass
class Insight:
    key:            str                       # stable identifier, e.g. "best_day_of_week"
    category:       str                       # one of CATEGORIES keys
    confidence:     str                       # "strong" | "early"
    headline:       str                       # warm one-liner
    detail:         str                       # supporting sentence(s)
    facts:          dict                      # structured numbers (AI seam + tests)
    recommendation: Optional[str] = None      # "so do this" — only on strong insights
    action:         Optional[dict] = None     # {"label": str, "endpoint": str} → a button
    chart:          Optional[dict] = None      # {"type": ..., ...} render hint for the template

    @property
    def is_strong(self) -> bool:
        return self.confidence == "strong"


# --------------------------------------------------------------------------- #
#  Gating thresholds (tuned to stay quiet until a pattern is real)             #
# --------------------------------------------------------------------------- #

MIN_TOTAL          = 60      # workouts before most rules will speak at all
PACE_DELTA_STRONG  = 2.5     # sec/500m gap that reads as a strong pattern
PACE_DELTA_MIN     = 1.5     # sec/500m gap below which we stay silent


# --------------------------------------------------------------------------- #
#  Small helpers                                                               #
# --------------------------------------------------------------------------- #

def _rows():
    """All rowing-erg workouts, oldest first."""
    return (
        Workout.query
        .filter_by(workout_type="rower")
        .order_by(Workout.workout_date.asc())
        .all()
    )


def _fmt_pace(seconds) -> str:
    if seconds is None:
        return "—"
    m, s = divmod(int(round(seconds)), 60)
    return f"{m}:{s:02d}"


def _current_streak(rows) -> int:
    """Consecutive-day streak ending today or yesterday (mirrors dashboard)."""
    dates = sorted({w.workout_date for w in rows}, reverse=True)
    if not dates:
        return 0
    today = date.today()
    if dates[0] < today - timedelta(days=1):
        return 0
    streak = 1
    for i in range(1, len(dates)):
        if dates[i - 1] - dates[i] == timedelta(days=1):
            streak += 1
        else:
            break
    return streak


def _linfit_slope(xs, ys):
    """Ordinary least-squares slope of ys over xs. None if degenerate."""
    n = len(xs)
    if n < 2:
        return None
    mx = sum(xs) / n
    my = sum(ys) / n
    denom = sum((x - mx) ** 2 for x in xs)
    if denom == 0:
        return None
    return sum((xs[i] - mx) * (ys[i] - my) for i in range(n)) / denom


# -- render-ready chart builders (kept here so the template stays logic-free) --

def _bar_chart(labels, values, best_index, lower_is_better):
    """Bars scaled 40–100% of height, best one flagged. 'Better' is always the
    tallest bar regardless of whether lower or higher raw values are good."""
    lo, hi = min(values), max(values)
    span = (hi - lo) or 1
    bars = []
    for i, v in enumerate(values):
        frac = (hi - v) / span if lower_is_better else (v - lo) / span
        bars.append({
            "label": labels[i],
            "height": round(40 + frac * 60),
            "best": i == best_index,
        })
    return {"type": "bars", "bars": bars}


def _sparkline(points, lower_is_better, accent):
    """Polyline over a 300×56 viewBox, oriented so 'better' sits higher on the
    chart (up-and-to-the-right always reads as good)."""
    lo, hi = min(points), max(points)
    span = (hi - lo) or 1
    coords = []
    n = len(points)
    for i, v in enumerate(points):
        x = round(i / (n - 1) * 300, 1) if n > 1 else 0
        good = (hi - v) / span if lower_is_better else (v - lo) / span
        y = round(48 - good * 40, 1)
        coords.append((x, y))
    return {
        "type": "sparkline",
        "svg_points": " ".join(f"{x},{y}" for x, y in coords),
        "end_x": coords[-1][0],
        "end_y": coords[-1][1],
        "accent": accent,
    }


# --------------------------------------------------------------------------- #
#  Rules — each returns an Insight or None                                     #
# --------------------------------------------------------------------------- #

def _best_day_of_week(rows) -> Optional[Insight]:
    """Which weekday your splits come in fastest. Median pace resists the
    sprint-vs-long-piece spread, so a fast 100m doesn't skew a day."""
    paced = [w for w in rows if w.avg_pace_seconds]
    if len(paced) < MIN_TOTAL:
        return None

    by_dow: dict[int, list[int]] = {i: [] for i in range(7)}
    for w in paced:
        by_dow[w.workout_date.weekday()].append(w.avg_pace_seconds)

    # Every weekday needs a real sample before we compare them.
    if any(len(v) < 6 for v in by_dow.values()):
        return None

    medians = {d: statistics.median(v) for d, v in by_dow.items()}
    overall = statistics.median([p for v in by_dow.values() for p in v])
    best_dow = min(medians, key=medians.get)
    delta = overall - medians[best_dow]          # positive = faster than typical
    if delta < PACE_DELTA_MIN:
        return None

    best_n = len(by_dow[best_dow])
    day = calendar.day_name[best_dow]
    confidence = "strong" if (delta >= PACE_DELTA_STRONG and best_n >= 15) else "early"

    return Insight(
        key="best_day_of_week",
        category="timing",
        confidence=confidence,
        headline=f"Something about {day}s just clicks",
        detail=(
            f"Your {day} splits land about {round(delta)}s/500m faster than a "
            f"typical day — and that's across {best_n} of them, so it's no fluke."
        ),
        recommendation=(
            f"Save your test pieces and PB attempts for {day}s."
            if confidence == "strong" else None
        ),
        facts={
            "best_dow": best_dow,
            "best_day_name": day,
            "delta_seconds": round(delta, 1),
            "best_day_median_pace": round(medians[best_dow], 1),
            "overall_median_pace": round(overall, 1),
            "sample_size": best_n,
        },
        chart=_bar_chart(
            labels=[calendar.day_abbr[i] for i in range(7)],
            values=[round(medians[i], 1) for i in range(7)],
            best_index=best_dow,
            lower_is_better=True,      # lower pace = faster = the highlighted bar
        ),
    )


def _rest_gap_effect(rows) -> Optional[Insight]:
    """Does a rest day sharpen the next session? Bucket each workout by the
    gap since the previous rowing day and compare median pace."""
    dates = sorted({w.workout_date for w in rows})
    if len(dates) < MIN_TOTAL:
        return None
    prev_of = {dates[i]: dates[i - 1] for i in range(1, len(dates))}

    # gap bucket -> list of paces for the first session after that gap
    buckets: dict[str, list[int]] = {"1": [], "2": [], "3+": []}
    for w in rows:
        if not w.avg_pace_seconds:
            continue
        prev = prev_of.get(w.workout_date)
        if prev is None:
            continue
        gap = (w.workout_date - prev).days
        if gap <= 0:
            continue
        key = "1" if gap == 1 else "2" if gap == 2 else "3+"
        buckets[key].append(w.avg_pace_seconds)

    if any(len(buckets[k]) < 10 for k in ("1", "2")):
        return None

    med = {k: statistics.median(v) for k, v in buckets.items() if v}
    baseline = med["1"]                                  # rowed again next day
    peak_key = min(med, key=med.get)
    gain = baseline - med.get(peak_key, baseline)        # positive = faster after rest
    if peak_key == "1" or gain < PACE_DELTA_MIN:
        return None

    peak_label = {"2": "2-day", "3+": "3-day+"}.get(peak_key, peak_key)
    confidence = "strong" if gain >= PACE_DELTA_STRONG else "early"

    # State-aware recommendation: if they're mid-streak, nudge a rest day.
    streak = _current_streak(rows)
    if confidence == "strong":
        if streak >= 3:
            rec = (f"You've rowed {streak} days straight — a rest day now sets up "
                   f"a stronger session.")
        else:
            rec = "Don't be shy about a rest day — your next row tends to thank you for it."
    else:
        rec = None

    return Insight(
        key="rest_gap_effect",
        category="timing",
        confidence=confidence,
        headline="A rest day, and you come back flying",
        detail=(
            f"After a {peak_label} breather your first row is about {round(gain)}s/500m "
            f"quicker than rowing again the very next day."
        ),
        recommendation=rec,
        facts={
            "peak_gap": peak_key,
            "gain_seconds": round(gain, 1),
            "medians": {k: round(v, 1) for k, v in med.items()},
            "current_streak": streak,
        },
        chart={
            "type": "gap_scale",
            "segments": [
                {"label": "1 day",  "key": "next-day", "peak": peak_key == "1"},
                {"label": "2 days", "key": "rest",     "peak": peak_key == "2"},
                {"label": "3+ days","key": "long",     "peak": peak_key == "3+"},
            ],
        },
    )


def _pace_trend(rows, window_days=90) -> Optional[Insight]:
    """Is your steady-state pace trending down over the recent window? Restricted
    to steady pieces (20 min+) so a shift in workout mix — more sprints, more easy
    volume — can't masquerade as a pace change."""
    cutoff = date.today() - timedelta(days=window_days)
    recent = [w for w in rows
              if w.avg_pace_seconds and w.time_seconds and w.time_seconds >= 20 * 60
              and w.workout_date >= cutoff]
    if len(recent) < 15:
        return None
    span = (recent[-1].workout_date - recent[0].workout_date).days
    if span < 30:
        return None

    xs = [(w.workout_date - recent[0].workout_date).days for w in recent]
    ys = [w.avg_pace_seconds for w in recent]
    slope = _linfit_slope(xs, ys)           # sec/500m per day
    if slope is None:
        return None
    total_change = slope * span             # negative = got faster over the window

    if total_change > -2.0:                 # not improving meaningfully → stay quiet
        return None
    improved = round(-total_change)
    n = len(recent)
    confidence = "strong" if (improved >= 4 and n >= 25) else "early"

    # Monthly medians make a clean, honest sparkline.
    by_month: dict[str, list[int]] = {}
    for w in recent:
        by_month.setdefault(w.workout_date.strftime("%Y-%m"), []).append(w.avg_pace_seconds)
    points = [round(statistics.median(v), 1) for _, v in sorted(by_month.items())]

    return Insight(
        key="pace_trend",
        category="progress",
        confidence=confidence,
        headline="Your steady-state pace keeps dropping",
        detail=(
            f"Down about {improved}s/500m on your longer pieces over the last "
            f"{window_days // 30} months — a genuine improvement stretch. Whatever "
            f"you're doing, keep doing it."
        ),
        facts={
            "window_days": window_days,
            "total_change_seconds": round(total_change, 1),
            "slope_per_day": round(slope, 4),
            "start_pace": round(ys[0], 1),
            "end_pace": round(ys[-1], 1),
            "sample_size": n,
        },
        chart={
            **_sparkline(points, lower_is_better=True, accent="accent"),
            "start_label": _fmt_pace(points[0]) if points else "—",
            "end_label": _fmt_pace(points[-1]) if points else "—",
        },
    )


def _volume_trend(rows) -> Optional[Insight]:
    """Weekly meters climbing or falling — recent 4 weeks vs the 4 before."""
    # Drop the current, still-in-progress ISO week — a half-finished week would
    # read as a volume drop that hasn't actually happened.
    cur = date.today().isocalendar()
    cur_key = f"{cur[0]}-{cur[1]:02d}"
    by_week: dict[str, int] = {}
    for w in rows:
        iso = w.workout_date.isocalendar()
        key = f"{iso[0]}-{iso[1]:02d}"
        if key == cur_key:
            continue
        by_week[key] = by_week.get(key, 0) + (w.distance_meters or 0)
    weeks = [v for _, v in sorted(by_week.items())]
    if len(weeks) < 8:
        return None

    recent = weeks[-4:]
    prior = weeks[-8:-4]
    recent_avg = sum(recent) / 4
    prior_avg = sum(prior) / 4
    if prior_avg == 0:
        return None
    pct = (recent_avg - prior_avg) / prior_avg * 100
    if abs(pct) < 15:
        return None

    rising = pct > 0
    confidence = "strong" if abs(pct) >= 25 else "early"
    return Insight(
        key="volume_trend",
        category="progress",
        confidence=confidence,
        headline=("You're piling on the meters lately" if rising
                  else "You've eased off the volume lately"),
        detail=(
            f"Averaging {round(recent_avg / 1000, 1)} km/week, "
            f"{'up' if rising else 'down'} from {round(prior_avg / 1000, 1)} km a month ago — "
            f"a {round(abs(pct))}% {'jump' if rising else 'drop'}."
        ),
        facts={
            "recent_weekly_avg": round(recent_avg),
            "prior_weekly_avg": round(prior_avg),
            "pct_change": round(pct, 1),
            "rising": rising,
        },
        chart={
            **_sparkline([round(v / 1000, 1) for v in weeks[-12:]],
                         lower_is_better=False, accent="cool"),
            "start_label": f"{round(weeks[-12] / 1000, 1)} km" if len(weeks) >= 12 else "",
            "end_label": f"{round(weeks[-1] / 1000, 1)} km",
        },
    )


def _fastest_rate_steady(rows) -> Optional[Insight]:
    """Which stroke rate gives your best pace *in steady pieces*. Restricting to
    20-min+ rows removes the sprint confound — in short intervals you naturally
    rate high, so mixing them in would just rediscover 'sprints are fast'."""
    STEADY_MIN_SECONDS = 20 * 60
    bands: dict[int, list[int]] = {}
    for w in rows:
        if not (w.avg_stroke_rate and w.avg_pace_seconds and w.time_seconds):
            continue
        if w.time_seconds < STEADY_MIN_SECONDS:
            continue
        band = int(round(w.avg_stroke_rate / 2) * 2)   # nearest 2 spm
        bands.setdefault(band, []).append(w.avg_pace_seconds)

    qualified = {b: vs for b, vs in bands.items() if len(vs) >= 8}
    total = sum(len(v) for v in qualified.values())
    if len(qualified) < 3 or total < 40:
        return None

    med = {b: statistics.median(v) for b, v in qualified.items()}       # pace: lower = faster
    overall = statistics.median([p for v in qualified.values() for p in v])
    best_band = min(med, key=med.get)
    edge = overall - med[best_band]         # how much faster than a typical steady row
    if edge < PACE_DELTA_MIN:
        return None

    best_n = len(qualified[best_band])
    confidence = "strong" if (edge >= PACE_DELTA_STRONG and best_n >= 15) else "early"
    ordered = sorted(med.keys())
    rates_above = [b for b in ordered if b > best_band]
    higher_note = ("not your highest rates" if rates_above else "right in your comfort zone")

    return Insight(
        key="fastest_rate_steady",
        category="technique",
        confidence=confidence,
        headline=f"Your steady rows fly at {best_band} spm",
        detail=(
            f"In your longer pieces (20 min+), your quickest splits come at {best_band} spm — "
            f"{higher_note}. There's more speed in a strong, patient stroke than in rating up."
        ),
        recommendation=(f"On steady rows, settle in at {best_band} spm and hold it."
                        if confidence == "strong" else None),
        action=({"label": "Plan a steady row", "endpoint": "wod.wod"}
                if confidence == "strong" else None),
        facts={
            "best_band": best_band,
            "best_band_pace": round(med[best_band], 1),
            "overall_steady_pace": round(overall, 1),
            "edge_seconds": round(edge, 1),
            "sample_size": best_n,
            "band_medians": {b: round(med[b], 1) for b in ordered},
        },
        chart=_bar_chart(
            labels=[str(b) for b in ordered],
            values=[round(med[b], 1) for b in ordered],
            best_index=ordered.index(best_band),
            lower_is_better=True,      # lower pace = faster
        ),
    )


def _session_length_clusters(rows) -> Optional[Insight]:
    """Do your sessions cluster around a favourite length (or two)?"""
    mins = [round(w.time_seconds / 60) for w in rows if w.time_seconds]
    if len(mins) < 40:
        return None

    # Histogram by nearest 5 minutes.
    hist: dict[int, int] = {}
    for m in mins:
        band = int(round(m / 5) * 5)
        hist[band] = hist.get(band, 0) + 1
    total = len(mins)
    ranked = sorted(hist.items(), key=lambda kv: kv[1], reverse=True)
    top_band, top_count = ranked[0]
    top_share = top_count / total
    if top_share < 0.25:
        return None

    # Is there a clear second mode, well separated from the first?
    second = next((b for b, c in ranked[1:]
                   if c / total >= 0.15 and abs(b - top_band) >= 10), None)

    pills = [{"label": f"~{b} min", "pct": round(c / total * 100), "hot": b in (top_band, second)}
             for b, c in ranked[:3]]

    if second is not None:
        lo, hi = sorted((top_band, second))
        headline = "You're a short-and-long kind of rower"
        detail = (f"Most of your rows land near {lo} min or {hi} min — you've got two "
                  f"favourite session shapes rather than one default.")
    else:
        headline = f"Your rows gravitate to ~{top_band} minutes"
        detail = (f"About {round(top_share * 100)}% of your sessions land near {top_band} "
                  f"minutes — that's your comfort distance.")

    return Insight(
        key="session_length_clusters",
        category="habits",
        confidence="strong" if total >= 100 else "early",
        headline=headline,
        detail=detail,
        facts={
            "top_band": top_band,
            "top_share": round(top_share, 3),
            "second_band": second,
            "sample_size": total,
        },
        chart={"type": "pills", "pills": pills},
    )


def _consistency(rows) -> Optional[Insight]:
    """How rarely you let a gap open up — consistency as a superpower."""
    dates = sorted({w.workout_date for w in rows})
    if len(dates) < MIN_TOTAL:
        return None

    gaps = [(dates[i] - dates[i - 1]).days for i in range(1, len(dates))]
    within2 = sum(1 for g in gaps if g <= 2) / len(gaps)
    if within2 < 0.60:
        return None

    # Longest gap in the last year, so the claim stays current.
    year_ago = date.today() - timedelta(days=365)
    recent_gaps = [(dates[i] - dates[i - 1]).days
                   for i in range(1, len(dates)) if dates[i] >= year_ago]
    longest_recent = max(recent_gaps) if recent_gaps else max(gaps)

    seg3 = sum(1 for g in gaps if g == 3) / len(gaps)
    seg4 = sum(1 for g in gaps if g >= 4) / len(gaps)

    # Only wear the "almost never miss" headline if the year genuinely backs it
    # up — a single long break shouldn't get to boast about a small longest gap.
    tight = longest_recent <= 4
    if tight:
        headline = "You almost never let two days slip"
        detail = (
            f"Your longest gap this past year was just {longest_recent} days, and "
            f"{round(within2 * 100)}% of your rows follow within 48h of the last. "
            f"Consistency is genuinely your superpower."
        )
    else:
        headline = "You keep a steady rhythm going"
        detail = (
            f"{round(within2 * 100)}% of your rows follow within 48h of the last — you "
            f"hold a tight cadence most of the year, give or take the odd break."
        )

    return Insight(
        key="consistency",
        category="habits",
        confidence="strong",
        headline=headline,
        detail=detail,
        facts={
            "within_2_days_pct": round(within2 * 100, 1),
            "longest_gap_last_year": longest_recent,
            "total_sessions": len(dates),
        },
        chart={
            "type": "gap_scale",
            "segments": [
                {"label": "≤ 2 days", "key": f"{round(within2 * 100)}%", "peak": True},
                {"label": "3 days",   "key": f"{round(seg3 * 100)}%",   "peak": False},
                {"label": "4+ days",  "key": f"{round(seg4 * 100)}%",   "peak": False},
            ],
        },
    )


def _pb_cadence(rows) -> Optional[Insight]:
    """Do your PBs arrive in clusters rather than steadily?"""
    pbs = [pb for pb in PersonalBest.query.all() if pb.achieved_date]
    if len(pbs) < 4:
        return None
    pbs.sort(key=lambda p: p.achieved_date, reverse=True)
    recent = pbs[:4]
    span = (recent[0].achieved_date - recent[-1].achieved_date).days
    if span > 21:                           # not clustered → nothing to say
        return None

    pills = [{"label": f"{p.category} · {p.achieved_date.strftime('%b %-d')}",
              "pct": None, "hot": True} for p in recent]
    return Insight(
        key="pb_cadence",
        category="progress",
        confidence="early",
        headline="Your PBs travel in packs",
        detail=(
            f"Your last {len(recent)} personal bests all landed inside a {span}-day window. "
            f"You don't chip away steadily — you break through in bursts."
        ),
        facts={
            "recent_pb_count": len(recent),
            "span_days": span,
            "categories": [p.category for p in recent],
        },
        chart={"type": "pills", "pills": pills},
    )


def _year_over_year_volume(rows) -> Optional[Insight]:
    """Are you ahead of where you were a year ago? Compares meters logged from
    Jan 1 through today against the identical span of last year."""
    today = date.today()
    this_start = date(today.year, 1, 1)
    days_in = (today - this_start).days
    last_start = date(today.year - 1, 1, 1)
    last_end = last_start + timedelta(days=days_in)     # same number of days into the year

    this_m = sum(w.distance_meters or 0 for w in rows if this_start <= w.workout_date <= today)
    last_m = sum(w.distance_meters or 0 for w in rows if last_start <= w.workout_date <= last_end)
    if last_m <= 0 or this_m <= 0:
        return None

    pct = (this_m - last_m) / last_m * 100
    if abs(pct) < 10:
        return None
    ahead = pct > 0

    return Insight(
        key="year_over_year_volume",
        category="progress",
        confidence="strong",
        headline=("You're ahead of last year's pace" if ahead
                  else "You're behind last year's meters — for now"),
        detail=(
            f"By this point in {today.year} you've rowed {round(this_m / 1000):,} km, "
            f"{'up' if ahead else 'down'} {round(abs(pct))}% on the {round(last_m / 1000):,} km "
            f"you'd logged by the same date in {today.year - 1}."
        ),
        facts={
            "this_year_meters": this_m,
            "last_year_meters": last_m,
            "pct_change": round(pct, 1),
            "ahead": ahead,
        },
        chart={"type": "pills", "pills": [
            {"label": f"{today.year} · {round(this_m / 1000):,} km", "pct": None, "hot": ahead},
            {"label": f"{today.year - 1} · {round(last_m / 1000):,} km", "pct": None, "hot": not ahead},
        ]},
    )


# -- Milestones: always-true fun facts. No significance test — these aren't
#    patterns, they're the headline numbers of a long rowing life. Gated only on
#    having a real history behind them so a brand-new log doesn't show "0.1 years".

def _milestone_longevity(rows) -> Optional[Insight]:
    if len(rows) < MIN_TOTAL:
        return None
    first = min(w.workout_date for w in rows)
    last = max(w.workout_date for w in rows)
    years = (last - first).days / 365.25
    if years < 1:
        return None
    return Insight(
        key="milestone_longevity",
        category="milestones",
        confidence="strong",
        headline=f"{years:.1f} years and still pulling",
        detail=(
            f"{len(rows):,} sessions logged since {first.strftime('%B %Y')}. "
            f"That's a rowing habit most people never build."
        ),
        facts={"years": round(years, 1), "sessions": len(rows), "since": first.isoformat()},
        chart={"type": "stat", "value": f"{years:.1f}", "unit": "years",
               "sub": f"since {first.strftime('%b %Y')}"},
    )


def _milestone_biggest_day(rows) -> Optional[Insight]:
    if len(rows) < MIN_TOTAL:
        return None
    by_day: dict[date, int] = {}
    for w in rows:
        by_day[w.workout_date] = by_day.get(w.workout_date, 0) + (w.distance_meters or 0)
    if not by_day:
        return None
    day, meters = max(by_day.items(), key=lambda kv: kv[1])
    if meters <= 0:
        return None
    return Insight(
        key="milestone_biggest_day",
        category="milestones",
        confidence="strong",
        headline=f"Your biggest day: {meters:,} m",
        detail=(
            f"On {day.strftime('%-d %B %Y')} you put down {meters:,} m in a single day — "
            f"your all-time daily high."
        ),
        facts={"meters": meters, "date": day.isoformat()},
        chart={"type": "stat", "value": f"{meters:,}", "unit": "meters",
               "sub": day.strftime('%-d %b %Y')},
    )


def _milestone_time_on_erg(rows) -> Optional[Insight]:
    if len(rows) < MIN_TOTAL:
        return None
    # total_time_seconds = work + rest-interval time — real time spent rowing,
    # same reasoning as total_distance_meters (never mixed into pace/PBs).
    total_sec = sum(w.total_time_seconds or 0 for w in rows)
    hours = total_sec / 3600
    if hours < 10:
        return None
    days_equiv = hours / 24
    return Insight(
        key="milestone_time_on_erg",
        category="milestones",
        confidence="strong",
        headline=f"{hours:,.0f} hours on the erg",
        detail=(
            f"Add up every session and you've spent {hours:,.0f} hours rowing — "
            f"about {days_equiv:.0f} full days of pulling."
        ),
        facts={"hours": round(hours, 1), "total_seconds": total_sec},
        chart={"type": "stat", "value": f"{hours:,.0f}", "unit": "hours",
               "sub": f"≈ {days_equiv:.0f} days of rowing"},
    )


def _milestone_total_workouts(rows) -> Optional[Insight]:
    if len(rows) < MIN_TOTAL:
        return None
    count = len(rows)
    first = min(w.workout_date for w in rows)
    return Insight(
        key="milestone_total_workouts",
        category="milestones",
        confidence="strong",
        headline=f"{count:,} workouts logged",
        detail=(
            f"Every session on the erg since {first.strftime('%B %Y')}, all {count:,} of them."
        ),
        facts={"workouts": count, "since": first.isoformat()},
        chart={"type": "stat", "value": f"{count:,}", "unit": "workouts",
               "sub": f"since {first.strftime('%b %Y')}"},
    )


def _milestone_total_calories(rows) -> Optional[Insight]:
    if len(rows) < MIN_TOTAL:
        return None
    # No rest-period calorie figure exists in C2's API (no such field on the
    # interval or top-level payload) — this is exactly what total_calories
    # already was, summed.
    total_cal = sum(w.total_calories or 0 for w in rows)
    if total_cal <= 0:
        return None
    thousands = total_cal / 1000
    return Insight(
        key="milestone_total_calories",
        category="milestones",
        confidence="strong",
        headline=f"{total_cal:,} calories burned",
        detail=(
            f"{thousands:,.1f}k calories across every logged session — "
            f"roughly {round(total_cal / 2000):,} days' worth of food energy."
        ),
        facts={"calories": total_cal},
        chart={"type": "stat", "value": f"{total_cal:,}", "unit": "cal",
               "sub": f"{thousands:,.1f}k total"},
    )


def _milestone_total_strokes(rows) -> Optional[Insight]:
    if len(rows) < MIN_TOTAL:
        return None
    # Whole-session total already — C2 doesn't split stroke_count by work/rest
    # the way it does distance and time, so this is a plain sum.
    total_strokes = sum(w.stroke_count or 0 for w in rows)
    if total_strokes <= 0:
        return None
    return Insight(
        key="milestone_total_strokes",
        category="milestones",
        confidence="strong",
        headline=f"{total_strokes:,} strokes taken",
        detail=(
            f"Every drive, every finish, every recovery — {total_strokes:,} strokes "
            f"across your whole rowing history."
        ),
        facts={"strokes": total_strokes},
        chart={"type": "stat", "value": f"{total_strokes:,}", "unit": "strokes",
               "sub": "lifetime total"},
    )


def _milestone_max_heart_rate(rows) -> Optional[Insight]:
    if len(rows) < MIN_TOTAL:
        return None
    with_hr = [w for w in rows if w.heart_rate_max]
    if not with_hr:
        return None
    w = max(with_hr, key=lambda x: x.heart_rate_max)
    return Insight(
        key="milestone_max_heart_rate",
        category="milestones",
        confidence="strong",
        headline=f"Peak heart rate: {w.heart_rate_max} bpm",
        detail=(
            f"Your hardest-working heart rate on record — {w.heart_rate_max} bpm, "
            f"on {w.workout_date.strftime('%-d %B %Y')}."
        ),
        facts={"heart_rate_max": w.heart_rate_max, "date": w.workout_date.isoformat()},
        chart={"type": "stat", "value": f"{w.heart_rate_max}", "unit": "bpm",
               "sub": w.workout_date.strftime('%-d %b %Y')},
    )


def _milestone_longest_streak(rows) -> Optional[Insight]:
    dates = sorted({w.workout_date for w in rows})
    if len(dates) < MIN_TOTAL:
        return None
    best = run = 1
    for i in range(1, len(dates)):
        run = run + 1 if (dates[i] - dates[i - 1]).days == 1 else 1
        best = max(best, run)
    if best < 5:                        # a handful of days isn't a milestone
        return None
    return Insight(
        key="milestone_longest_streak",
        category="milestones",
        confidence="strong",
        headline=f"Your longest streak: {best} days",
        detail=(
            f"{best} days in a row without missing — the longest unbroken run in your log."
        ),
        facts={"longest_streak": best},
        chart={"type": "stat", "value": f"{best}", "unit": "days",
               "sub": "longest unbroken run"},
    )


# Registry — order here is the fallback order within a category.
RULES = [
    _best_day_of_week,
    _rest_gap_effect,
    _pace_trend,
    _volume_trend,
    _year_over_year_volume,
    _fastest_rate_steady,
    _session_length_clusters,
    _consistency,
    _pb_cadence,
    _milestone_longevity,
    _milestone_biggest_day,
    _milestone_time_on_erg,
    _milestone_total_workouts,
    _milestone_total_calories,
    _milestone_total_strokes,
    _milestone_max_heart_rate,
    _milestone_longest_streak,
]


# --------------------------------------------------------------------------- #
#  Public API                                                                  #
# --------------------------------------------------------------------------- #

def generate_insights() -> list[Insight]:
    """Run every rule and return the insights that cleared their checks,
    strong patterns first, then grouped-friendly by category order."""
    rows = _rows()
    found: list[Insight] = []
    for rule in RULES:
        try:
            ins = rule(rows)
        except Exception:                   # a broken rule must never break the page
            import logging
            logging.getLogger(__name__).exception("Insight rule %s failed", rule.__name__)
            ins = None
        if ins is not None:
            found.append(ins)

    cat_order = {key: i for i, (key, _) in enumerate(CATEGORIES)}
    found.sort(key=lambda i: (cat_order.get(i.category, 99), 0 if i.is_strong else 1))
    return found


def group_insights(found: list[Insight]) -> list[dict]:
    """Arrange an already-computed insight list into display sections."""
    by_cat: dict[str, list[Insight]] = {}
    for ins in found:
        by_cat.setdefault(ins.category, []).append(ins)
    return [
        {"key": key, "label": label, "insights": by_cat[key]}
        for key, label in CATEGORIES if key in by_cat
    ]


def grouped_insights() -> list[dict]:
    """Insights arranged into their display sections for the template."""
    return group_insights(generate_insights())


def dataset_overview() -> dict:
    """Headline numbers for the page's stat strip."""
    q = Workout.query.filter_by(workout_type="rower")
    n = q.count()
    meters = db.session.query(func.sum(Workout.total_distance_meters)) \
        .filter_by(workout_type="rower").scalar() or 0
    first = q.order_by(Workout.workout_date.asc()).first()
    last = q.order_by(Workout.workout_date.desc()).first()
    return {
        "sessions": n,
        "meters": meters,
        "first_date": first.workout_date if first else None,
        "last_date": last.workout_date if last else None,
    }
