"""
Tests for wod_engine.py — pace targeting and periodization decisions.

Covers the pure formatting/zone math plus the DB-driven periodization
helpers (CAWR, recent WOD type mix, test-piece cooldown). generate_wod()
itself pulls from a large random WOD_LIBRARY, so it's covered with a
smoke test only — the interesting logic lives in the helpers.
"""

from datetime import date, timedelta

from models import db, PersonalBest, WodHistory
from wod_engine import (
    ZONE_OFFSETS,
    _fmt_pace,
    pace_for_zone,
    zones_from_pb,
    get_2k_pace_seconds,
    _recent_wod_types,
    _last_test_piece_date,
    _current_cawr,
    _choose_session_type,
    generate_wod,
    build_month_calendar,
    get_wod_for_date,
)


# ---------------------------------------------------------------------------
# Pure formatting / pace math
# ---------------------------------------------------------------------------

def test_fmt_pace_pads_seconds():
    assert _fmt_pace(125) == "2:05"
    assert _fmt_pace(60) == "1:00"
    assert _fmt_pace(5) == "0:05"


def test_pace_for_zone_uses_midpoint_offset():
    # UT2 offset is (24, 28) -> midpoint 26
    assert pace_for_zone("UT2", 120) == 146


def test_zones_from_pb_covers_every_zone():
    zones = zones_from_pb(120)
    assert set(zones.keys()) == set(ZONE_OFFSETS.keys())
    assert zones["Max"] == 120  # Max offset is (0, 0)


# ---------------------------------------------------------------------------
# get_2k_pace_seconds — fallback chain
# ---------------------------------------------------------------------------

def test_get_2k_pace_uses_2000m_pb_directly(app_ctx):
    db.session.add(PersonalBest(category="2000m", value_seconds=480))
    db.session.commit()
    assert get_2k_pace_seconds() == 120  # 480 / 4


def test_get_2k_pace_falls_back_to_1000m(app_ctx):
    db.session.add(PersonalBest(category="1000m", value_seconds=230))
    db.session.commit()
    assert get_2k_pace_seconds() == int(230 * 0.52)


def test_get_2k_pace_falls_back_to_5000m_when_1000m_missing(app_ctx):
    db.session.add(PersonalBest(category="5000m", value_seconds=1200))
    db.session.commit()
    assert get_2k_pace_seconds() == int(1200 * 0.46)


def test_get_2k_pace_none_with_no_pbs(app_ctx):
    assert get_2k_pace_seconds() is None


# ---------------------------------------------------------------------------
# _recent_wod_types — only counts completed rows, maps "test" -> "long"
# ---------------------------------------------------------------------------

def test_recent_wod_types_ignores_incomplete_and_old_rows(app_ctx):
    today = date.today()
    db.session.add_all([
        WodHistory(generated_date=today, wod_type="interval", completed=True),
        WodHistory(generated_date=today, wod_type="interval", completed=False),  # not completed
        WodHistory(generated_date=today - timedelta(days=30), wod_type="interval", completed=True),  # too old
        WodHistory(generated_date=today, wod_type="test", completed=True),  # counts toward "long"
    ])
    db.session.commit()

    counts = _recent_wod_types(days=7)
    assert counts["interval"] == 1
    assert counts["long"] == 1


def test_last_test_piece_date_ignores_incomplete(app_ctx):
    today = date.today()
    db.session.add_all([
        WodHistory(generated_date=today - timedelta(days=5), wod_type="test", completed=False),
        WodHistory(generated_date=today - timedelta(days=10), wod_type="test", completed=True),
    ])
    db.session.commit()

    assert _last_test_piece_date() == today - timedelta(days=10)


def test_last_test_piece_date_none_when_no_test_pieces(app_ctx):
    assert _last_test_piece_date() is None


# ---------------------------------------------------------------------------
# _current_cawr — needs 42 days of calendar history to compute
# ---------------------------------------------------------------------------

def test_current_cawr_none_with_insufficient_history(app_ctx, make_workout):
    make_workout(id=1, distance_meters=2000, time_seconds=480)
    assert _current_cawr() is None


def test_current_cawr_ratio_with_steady_load(app_ctx, make_workout):
    today = date.today()
    for i in range(42):
        make_workout(id=i + 1, distance_meters=2000, time_seconds=480,
                     workout_date=today - timedelta(days=41 - i))
    # Uniform 2000m/day for 42 days -> acute avg == chronic avg -> ratio 1.0
    assert _current_cawr() == 1.0


# ---------------------------------------------------------------------------
# _choose_session_type — CAWR modifier takes priority
# ---------------------------------------------------------------------------

def test_choose_session_type_high_cawr_forces_steady_state(app_ctx):
    assert _choose_session_type(cawr=1.5) == "steady_state"


def test_choose_session_type_low_cawr_biases_toward_quality(app_ctx):
    assert _choose_session_type(cawr=0.5) in ("interval", "threshold")


def test_choose_session_type_no_recent_history_defers_to_distribution(app_ctx):
    # No CAWR signal, no recent WODs -> falls back to the target distribution;
    # every type is equally overdue so any configured type is a valid choice.
    result = _choose_session_type(cawr=None)
    assert result in ("steady_state", "interval", "threshold", "long")


# ---------------------------------------------------------------------------
# generate_wod — smoke test only (structure comes from a large library)
# ---------------------------------------------------------------------------

def test_generate_wod_produces_a_complete_spec(app_ctx):
    spec = generate_wod(force_type="steady_state")
    assert spec.wod_type == "steady_state"
    assert spec.intervals
    assert spec.target_pace_seconds > 0
    assert spec.target_pace_str == _fmt_pace(spec.target_pace_seconds)


# ---------------------------------------------------------------------------
# build_month_calendar — month grid shape, padding, and per-day status
# ---------------------------------------------------------------------------

def test_build_month_calendar_shape_and_padding(app_ctx):
    # August 2026: starts on a Saturday, so the grid pads 5 days from July
    # and 6 days from September to complete Mon-Sun weeks.
    weeks = build_month_calendar(2026, 8)

    assert len(weeks) == 6
    assert all(len(week) == 7 for week in weeks)

    first_week_dates = [c["date"] for c in weeks[0]]
    assert first_week_dates == [
        date(2026, 7, 27), date(2026, 7, 28), date(2026, 7, 29),
        date(2026, 7, 30), date(2026, 7, 31), date(2026, 8, 1), date(2026, 8, 2),
    ]
    first_week_in_month = [c["in_month"] for c in weeks[0]]
    assert first_week_in_month == [False, False, False, False, False, True, True]

    last_week = weeks[-1]
    assert last_week[0]["date"] == date(2026, 8, 31)
    assert last_week[0]["in_month"] is True
    assert last_week[1]["date"] == date(2026, 9, 1)
    assert last_week[1]["in_month"] is False


def test_build_month_calendar_status_per_day(app_ctx):
    db.session.add_all([
        WodHistory(generated_date=date(2026, 8, 5), wod_type="interval", wod_json={}, completed=True),
        WodHistory(generated_date=date(2026, 8, 6), wod_type="steady_state", wod_json={}, completed=False),
    ])
    db.session.commit()

    weeks = build_month_calendar(2026, 8)
    by_date = {c["date"]: c for week in weeks for c in week}

    assert by_date[date(2026, 8, 5)]["status"] == "completed"
    assert by_date[date(2026, 8, 6)]["status"] == "pending"
    assert by_date[date(2026, 8, 7)]["status"] == "none"
    # Out-of-month padding days are always "none" regardless of any data
    assert by_date[date(2026, 7, 27)]["status"] == "none"


def test_build_month_calendar_latest_row_wins_on_regeneration(app_ctx):
    # A day can have multiple WodHistory rows if the WOD was regenerated
    # (wod_generate() always inserts a new row rather than updating).
    db.session.add(WodHistory(id=1, generated_date=date(2026, 8, 5), wod_type="interval", wod_json={}, completed=True))
    db.session.commit()
    db.session.add(WodHistory(id=2, generated_date=date(2026, 8, 5), wod_type="steady_state", wod_json={}, completed=False))
    db.session.commit()

    weeks = build_month_calendar(2026, 8)
    by_date = {c["date"]: c for week in weeks for c in week}
    assert by_date[date(2026, 8, 5)]["status"] == "pending"


# ---------------------------------------------------------------------------
# get_wod_for_date
# ---------------------------------------------------------------------------

def test_get_wod_for_date_returns_latest_row(app_ctx):
    db.session.add(WodHistory(id=1, generated_date=date(2026, 8, 5), wod_type="interval", wod_json={"title": "First"}, completed=True))
    db.session.commit()
    db.session.add(WodHistory(id=2, generated_date=date(2026, 8, 5), wod_type="steady_state", wod_json={"title": "Second"}, completed=False))
    db.session.commit()

    row = get_wod_for_date(date(2026, 8, 5))
    assert row.id == 2
    assert row.wod_json["title"] == "Second"


def test_get_wod_for_date_returns_none_when_absent(app_ctx):
    assert get_wod_for_date(date(2026, 8, 5)) is None
