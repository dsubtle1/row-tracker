"""
Tests for import_csv.py — CSV row parsing (no DB, no app context required).

parse_row/parse_pace are pure functions over dict input, so these run
without any Flask/SQLAlchemy fixtures.
"""

from import_csv import parse_pace, parse_row


# ---------------------------------------------------------------------------
# parse_pace
# ---------------------------------------------------------------------------

def test_parse_pace_truncates_subsecond_fraction():
    assert parse_pace("2:28.7") == 2 * 60 + 28


def test_parse_pace_handles_empty_string():
    assert parse_pace("") is None
    assert parse_pace("   ") is None


def test_parse_pace_handles_malformed_string():
    assert parse_pace("not-a-pace") is None


# ---------------------------------------------------------------------------
# parse_row
# ---------------------------------------------------------------------------

def _valid_row(**overrides):
    row = {
        "Type": "RowErg",
        "Log ID": "12345",
        "Date": "2024-11-15 09:32:00",
        "Work Time (Seconds)": "480.0",
        "Work Distance": "2000",
        "Pace": "2:00.0",
        "Stroke Rate/Cadence": "24",
        "Total Cal": "250",
    }
    row.update(overrides)
    return row


def test_parse_row_maps_a_valid_rowerg_row():
    workout = parse_row(_valid_row())
    assert workout is not None
    assert workout.id == 12345
    assert workout.workout_type == "rower"
    assert workout.time_seconds == 480
    assert workout.distance_meters == 2000
    assert workout.avg_pace_seconds == 120
    assert workout.avg_stroke_rate == 24
    assert workout.total_calories == 250
    assert workout.stroke_data is None
    assert workout.raw_json is None


def test_parse_row_skips_non_rowerg_type():
    assert parse_row(_valid_row(Type="BikeErg")) is None


def test_parse_row_skips_missing_log_id():
    assert parse_row(_valid_row(**{"Log ID": ""})) is None


def test_parse_row_skips_non_numeric_log_id():
    assert parse_row(_valid_row(**{"Log ID": "not-a-number"})) is None


def test_parse_row_skips_missing_date():
    assert parse_row(_valid_row(Date="")) is None


def test_parse_row_skips_malformed_date():
    assert parse_row(_valid_row(Date="15/11/2024")) is None


def test_parse_row_tolerates_missing_optional_fields():
    row = _valid_row(**{
        "Work Time (Seconds)": "",
        "Work Distance": "",
        "Pace": "",
        "Stroke Rate/Cadence": "",
        "Total Cal": "",
    })
    workout = parse_row(row)
    assert workout is not None
    assert workout.time_seconds is None
    assert workout.distance_meters is None
    assert workout.avg_pace_seconds is None
    assert workout.avg_stroke_rate is None
    assert workout.total_calories is None


def test_parse_row_ignores_unparseable_numeric_fields_rather_than_crashing():
    row = _valid_row(**{"Work Distance": "N/A", "Total Cal": "N/A"})
    workout = parse_row(row)
    assert workout is not None
    assert workout.distance_meters is None
    assert workout.total_calories is None
