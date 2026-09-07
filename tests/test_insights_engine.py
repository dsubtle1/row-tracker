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
    generate_insights_and_gates,
    group_insights_and_gates,
    GateStatus,
    MIN_TOTAL,
    _bar_chart,
    _sparkline,
    _linfit_slope,
    _current_streak,
    _consistency,
    _fastest_rate_steady,
    _year_over_year_volume,
    _best_day_of_week,
    _rest_gap_effect,
    _milestone_longevity,
    _milestone_biggest_day,
    _milestone_time_on_erg,
    _milestone_total_workouts,
    _milestone_total_calories,
    _milestone_total_strokes,
    _milestone_max_heart_rate,
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


def test_generate_insights_and_gates_matches_generate_insights_for_found(app_ctx):
    """The new wrapper must not change which insights fire, only add gate info."""
    found, gated = generate_insights_and_gates()
    assert found == generate_insights() == []
    # Empty history: best_day_of_week and rest_gap_effect both report their
    # own insufficient-sample status; every other rule still returns bare None.
    assert {g.key for g in gated} == {"best_day_of_week", "rest_gap_effect"}
    assert all(g.reason == "insufficient_sample" for g in gated)


# --------------------------------------------------------------------------- #
#  Rule: best day of week — sample-size vs. no-effect gating                   #
# --------------------------------------------------------------------------- #

def _rows_on_weekdays(weekdays, count_per_day, pace=120):
    """count_per_day rows on each given weekday index (0=Mon..6=Sun), one per
    distinct week so every row lands on a different calendar date."""
    base = date(2026, 1, 5)   # a Monday
    rows = []
    for wd in weekdays:
        d = base + timedelta(days=wd)
        for i in range(count_per_day):
            rows.append(W(workout_date=d + timedelta(weeks=i), avg_pace_seconds=pace))
    return rows


def test_best_day_of_week_insufficient_total_sample():
    rows = _rows_on_weekdays(range(7), 5)   # 35 paced rows, under MIN_TOTAL
    ins, status = _best_day_of_week(rows)
    assert ins is None
    assert status.reason == "insufficient_sample"
    assert str(len(rows)) in status.message


def test_best_day_of_week_insufficient_per_weekday_sample():
    rows = _rows_on_weekdays([0, 2, 4], 22)   # 66 total, but 4 weekdays have zero
    assert len(rows) >= MIN_TOTAL
    ins, status = _best_day_of_week(rows)
    assert ins is None
    assert status.reason == "insufficient_sample"


def test_best_day_of_week_no_effect_when_pace_is_flat():
    rows = _rows_on_weekdays(range(7), 9, pace=120)   # 63 rows, identical pace everywhere
    ins, status = _best_day_of_week(rows)
    assert ins is None
    assert status.reason == "no_effect"
    assert status.category == "timing"


def test_best_day_of_week_fires_when_one_day_is_clearly_faster():
    rows = _rows_on_weekdays(range(1, 7), 9, pace=120)
    rows += _rows_on_weekdays([0], 9, pace=100)   # Monday well ahead of the rest
    ins, status = _best_day_of_week(rows)
    assert status is None
    assert ins is not None
    assert ins.key == "best_day_of_week"


# --------------------------------------------------------------------------- #
#  Rule: rest-gap effect — sample-size vs. no-effect gating                    #
# --------------------------------------------------------------------------- #

def _rest_gap_rows(gaps_and_paces):
    """Build rows from a list of (gap_from_previous, avg_pace_seconds); the
    first entry's gap is ignored since there's no previous date yet."""
    rows = []
    d = date(2026, 1, 1)
    for i, (gap, pace) in enumerate(gaps_and_paces):
        if i > 0:
            d = d + timedelta(days=gap)
        rows.append(W(workout_date=d, avg_pace_seconds=pace))
    return rows


def test_rest_gap_effect_insufficient_total_sample():
    rows = _rest_gap_rows([(1, 120)] * 20)   # 20 distinct dates, under MIN_TOTAL
    ins, status = _rest_gap_effect(rows)
    assert ins is None
    assert status.reason == "insufficient_sample"


def test_rest_gap_effect_insufficient_bucket_sample():
    # 61 distinct dates all 3+ days apart — buckets "1" and "2" never populate.
    rows = _rest_gap_rows([(3, 120)] * 61)
    ins, status = _rest_gap_effect(rows)
    assert ins is None
    assert status.reason == "insufficient_sample"


def test_rest_gap_effect_no_effect_when_pace_is_flat():
    # One continuous sequence of dates (each group's gap chains onto the last
    # date of the previous group) — same uniform pace throughout.
    rows = _rest_gap_rows([(1, 120)] * 20 + [(2, 120)] * 20 + [(3, 120)] * 20)
    ins, status = _rest_gap_effect(rows)
    assert ins is None
    assert status.reason == "no_effect"
    assert status.category == "timing"


def test_rest_gap_effect_fires_when_rest_clearly_helps():
    rows = _rest_gap_rows(
        [(1, 130)] * 20     # back-to-back days: slower
        + [(2, 110)] * 20   # a rest day: notably faster
        + [(3, 120)] * 20   # padding to keep dates well past MIN_TOTAL
    )
    ins, status = _rest_gap_effect(rows)
    assert status is None
    assert ins is not None
    assert ins.key == "rest_gap_effect"


# --------------------------------------------------------------------------- #
#  group_insights_and_gates()                                                 #
# --------------------------------------------------------------------------- #

def test_group_insights_and_gates_includes_a_category_with_only_notices():
    gated = [GateStatus(key="best_day_of_week", category="timing",
                         reason="no_effect", message="Checked — nothing here.")]
    sections = group_insights_and_gates([], gated)
    assert len(sections) == 1
    assert sections[0]["key"] == "timing"
    assert sections[0]["insights"] == []
    assert sections[0]["notices"] == gated


def test_group_insights_and_gates_omits_categories_with_neither():
    assert group_insights_and_gates([], []) == []


def test_insights_page_renders(client):
    resp = client.get("/insights")
    assert resp.status_code == 200
    assert b"What your rowing" in resp.data       # header copy
    assert b"Sessions analyzed" in resp.data      # stat strip


def test_insights_page_shows_progress_banner_below_sample_floor(client):
    resp = client.get("/insights")   # empty db — 0 workouts, well under MIN_TOTAL
    assert f"0/{MIN_TOTAL} workouts".encode() in resp.data


def test_insights_page_hides_progress_banner_at_or_above_sample_floor(client, full_app_ctx, full_make_workout):
    from datetime import date as _date
    for i in range(MIN_TOTAL):
        full_make_workout(id=i + 1, workout_date=_date.today() - timedelta(days=i))
    resp = client.get("/insights")
    assert b"workouts \xe2\x80\x94 most patterns need" not in resp.data


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
    assert _milestone_total_strokes(rows) is None
    assert _milestone_max_heart_rate(rows) is None


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


def test_milestone_total_strokes_sums_every_session():
    rows = _sixty_daily_rows(stroke_count=400)     # 60 × 400
    ins = _milestone_total_strokes(rows)
    assert ins is not None
    assert ins.facts["strokes"] == 24_000


def test_milestone_total_strokes_silent_without_data():
    rows = _sixty_daily_rows()     # stroke_count defaults to None
    assert _milestone_total_strokes(rows) is None


def test_milestone_max_heart_rate_picks_the_highest_reading():
    rows = _sixty_daily_rows(heart_rate_max=150)
    rows.append(W(workout_date=date.today() - timedelta(days=3), heart_rate_max=182))
    ins = _milestone_max_heart_rate(rows)
    assert ins is not None
    assert ins.facts["heart_rate_max"] == 182


def test_milestone_max_heart_rate_silent_without_any_hr_data():
    rows = _sixty_daily_rows()     # heart_rate_max defaults to None
    assert _milestone_max_heart_rate(rows) is None
