"""
Tests for insights_engine.py — the deterministic pattern-spotting rules.

Two layers:
  * The pure chart/stat helpers and individual rules are tested by handing them
    plain in-memory Workout objects (the rules take an already-queried list, so
    no database is needed).
  * generate_insights() and the /insights route are exercised against real
    fixtures to confirm the gating and end-to-end rendering.
"""

from datetime import date, timedelta

from models import Workout
import insights_engine as ie
from insights_engine import (
    generate_insights,
    _bar_chart,
    _sparkline,
    _linfit_slope,
    _current_streak,
    _consistency,
    _fastest_rate_steady,
    _year_over_year_volume,
    _milestone_longevity,
    _milestone_biggest_day,
    _milestone_time_on_erg,
    _milestone_total_workouts,
    _milestone_total_calories,
    _milestone_longest_streak,
)


def W(**kw):
    """A bare rower Workout object (not persisted) for feeding rules directly."""
    return Workout(workout_type="rower", **kw)


# --------------------------------------------------------------------------- #
#  Chart / stat helpers                                                        #
# --------------------------------------------------------------------------- #

def test_bar_chart_lower_is_better_makes_the_min_tallest():
    chart = _bar_chart(["a", "b", "c"], [130, 128, 126], best_index=2, lower_is_better=True)
    heights = [b["height"] for b in chart["bars"]]
    assert heights[2] == 100           # lowest pace → tallest bar
    assert heights[0] == 40            # highest pace → shortest bar
    assert chart["bars"][2]["best"] is True
    assert chart["bars"][0]["best"] is False


def test_bar_chart_higher_is_better_makes_the_max_tallest():
    chart = _bar_chart(["a", "b", "c"], [1, 2, 3], best_index=2, lower_is_better=False)
    heights = [b["height"] for b in chart["bars"]]
    assert heights[2] == 100
    assert heights[0] == 40


def test_sparkline_orients_better_values_higher():
    # Improving pace (decreasing, lower is better): the final point is best and
    # should sit higher on the chart, i.e. a smaller y in SVG coordinates.
    chart = _sparkline([130, 120, 110], lower_is_better=True, accent="accent")
    ys = [float(pair.split(",")[1]) for pair in chart["svg_points"].split(" ")]
    assert ys[-1] < ys[0]
    assert chart["end_y"] == ys[-1]


def test_linfit_slope_detects_direction():
    assert _linfit_slope([0, 1, 2, 3], [10, 8, 6, 4]) < 0     # falling
    assert _linfit_slope([0, 1, 2, 3], [4, 6, 8, 10]) > 0     # rising
    assert _linfit_slope([1, 1, 1], [1, 2, 3]) is None        # degenerate x


def test_current_streak_counts_consecutive_days():
    rows = [W(workout_date=date.today() - timedelta(days=n)) for n in range(5)]
    assert _current_streak(rows) == 5
    # A gap breaks it.
    rows = [W(workout_date=date.today()), W(workout_date=date.today() - timedelta(days=3))]
    assert _current_streak(rows) == 1


# --------------------------------------------------------------------------- #
#  Rule: consistency — and the self-contradiction regression                   #
# --------------------------------------------------------------------------- #

def test_consistency_earns_the_strong_headline_when_gaps_stay_tight():
    rows = [W(workout_date=date.today() - timedelta(days=n)) for n in range(70)]
    ins = _consistency(rows)
    assert ins is not None
    assert ins.confidence == "strong"
    assert "almost never" in ins.headline.lower()
    assert ins.facts["longest_gap_last_year"] <= 4


def test_consistency_does_not_boast_when_a_long_break_exists():
    # 40 tight days, a 40-day break, then 40 more tight days ending today.
    recent = [date.today() - timedelta(days=n) for n in range(40)]
    older_anchor = recent[-1] - timedelta(days=40)
    older = [older_anchor - timedelta(days=n) for n in range(40)]
    rows = [W(workout_date=d) for d in recent + older]
    ins = _consistency(rows)
    assert ins is not None
    # Most gaps are still 1 day, so it fires — but must not claim "almost never".
    assert "almost never" not in ins.headline.lower()
    assert ins.facts["longest_gap_last_year"] >= 40


# --------------------------------------------------------------------------- #
#  Rule: fastest_rate_steady                                                   #
# --------------------------------------------------------------------------- #

def test_fastest_rate_steady_picks_the_fastest_band_in_long_pieces():
    rows = []
    # band 24 clearly fastest (110), 20 and 28 slower (120/122); ≥40 steady rows
    # total to clear the sample floor, and 16 at the best band for strong.
    for rate, pace, count in [(20, 120, 12), (24, 110, 16), (28, 122, 12)]:
        for _ in range(count):
            rows.append(W(workout_date=date.today(), time_seconds=1500,
                          avg_stroke_rate=rate, avg_pace_seconds=pace,
                          distance_meters=6000))
    ins = _fastest_rate_steady(rows)
    assert ins is not None
    assert ins.facts["best_band"] == 24
    assert "24 spm" in ins.headline
    assert ins.confidence == "strong"
    assert ins.recommendation is not None
    assert ins.action["endpoint"] == "wod.wod"


def test_fastest_rate_steady_ignores_short_intervals():
    # Same fast band-24 rows but all under 20 min → not steady → no insight.
    rows = [W(workout_date=date.today(), time_seconds=300, avg_stroke_rate=24,
              avg_pace_seconds=105, distance_meters=1000) for _ in range(40)]
    assert _fastest_rate_steady(rows) is None


# --------------------------------------------------------------------------- #
#  Gating + end-to-end                                                         #
# --------------------------------------------------------------------------- #

def test_generate_insights_is_silent_on_an_empty_history(app_ctx):
    assert generate_insights() == []


def test_insights_page_renders(client):
    resp = client.get("/insights")
    assert resp.status_code == 200
    assert b"What your rowing" in resp.data       # header copy
    assert b"Sessions analyzed" in resp.data      # stat strip


# --------------------------------------------------------------------------- #
#  Rule: year-over-year volume                                                 #
# --------------------------------------------------------------------------- #

def test_year_over_year_fires_when_well_ahead():
    today = date.today()
    this_start = date(today.year, 1, 1)
    last_start = date(today.year - 1, 1, 1)
    rows = [W(workout_date=this_start, distance_meters=50_000),
            W(workout_date=last_start, distance_meters=10_000)]
    ins = _year_over_year_volume(rows)
    assert ins is not None
    assert ins.facts["ahead"] is True
    assert "ahead" in ins.headline.lower()


def test_year_over_year_silent_without_a_prior_year():
    today = date.today()
    rows = [W(workout_date=date(today.year, 1, 1), distance_meters=50_000)]
    assert _year_over_year_volume(rows) is None


# --------------------------------------------------------------------------- #
#  Rules: milestones — always-true facts, gated on a real history              #
# --------------------------------------------------------------------------- #

def _sixty_daily_rows(**extra):
    return [W(workout_date=date.today() - timedelta(days=n), **extra) for n in range(60)]


def test_milestones_stay_silent_below_the_history_floor():
    rows = [W(workout_date=date.today() - timedelta(days=n)) for n in range(10)]
    assert _milestone_longevity(rows) is None
    assert _milestone_biggest_day(rows) is None
    assert _milestone_longest_streak(rows) is None
    assert _milestone_total_workouts(rows) is None
    assert _milestone_total_calories(rows) is None


def test_milestone_longevity_reports_span_and_count():
    rows = _sixty_daily_rows()
    rows.append(W(workout_date=date.today() - timedelta(days=500)))   # push span past a year
    ins = _milestone_longevity(rows)
    assert ins is not None
    assert ins.facts["years"] >= 1
    assert ins.facts["sessions"] == 61
    assert ins.chart["type"] == "stat"


def test_milestone_biggest_day_picks_the_single_day_high():
    rows = _sixty_daily_rows(distance_meters=5_000)
    rows.append(W(workout_date=date.today() - timedelta(days=3), distance_meters=30_000))
    ins = _milestone_biggest_day(rows)
    assert ins is not None
    # The 30k row shares its date with a 5k row → 35k that day.
    assert ins.facts["meters"] == 35_000


def test_milestone_longest_streak_counts_the_longest_run():
    rows = _sixty_daily_rows()          # 60 consecutive days
    ins = _milestone_longest_streak(rows)
    assert ins is not None
    assert ins.facts["longest_streak"] == 60


def test_milestone_time_on_erg_sums_hours():
    rows = _sixty_daily_rows(time_seconds=3600)     # 60 × 1h
    ins = _milestone_time_on_erg(rows)
    assert ins is not None
    assert ins.facts["hours"] == 60.0


def test_milestone_time_on_erg_includes_rest_time():
    # 60 × (1h work + 10min rest) — rest counts toward real time on the erg.
    rows = _sixty_daily_rows(time_seconds=3600, rest_time_seconds=600)
    ins = _milestone_time_on_erg(rows)
    assert ins is not None
    assert ins.facts["hours"] == 70.0


def test_milestone_total_workouts_counts_every_session():
    rows = _sixty_daily_rows()
    ins = _milestone_total_workouts(rows)
    assert ins is not None
    assert ins.facts["workouts"] == 60


def test_milestone_total_calories_sums_every_session():
    rows = _sixty_daily_rows(total_calories=300)     # 60 × 300
    ins = _milestone_total_calories(rows)
    assert ins is not None
    assert ins.facts["calories"] == 18_000


def test_milestone_total_calories_silent_without_data():
    rows = _sixty_daily_rows()     # total_calories defaults to None
    assert _milestone_total_calories(rows) is None
