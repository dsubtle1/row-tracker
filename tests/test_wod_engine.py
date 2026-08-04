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
