"""
Tests for c2_api.py — mapping a raw Concept2 API result dict to a Workout.

_map_result_to_workout is a pure transform (it instantiates a Workout but
never touches the session), so no DB fixture is required — a Flask app
context is still needed because models.py binds Workout to Flask-SQLAlchemy.
"""

from datetime import date

from c2_api import _map_result_to_workout


def _raw_result(**overrides):
    result = {
        "id": 999,
        "date": "2024-11-15 09:32:00",
        "distance": 2000,
        "time": 4800,  # tenths of a second -> 480.0s
        "stroke_rate": "24",
        "calories_total": "250",
    }
    result.update(overrides)
    return result


def test_maps_core_fields(app_ctx):
    w = _map_result_to_workout(_raw_result())
    assert w.id == 999
    assert w.workout_date == date(2024, 11, 15)
    assert w.workout_type == "rower"
    assert w.time_seconds == 480
    assert w.distance_meters == 2000


def test_pace_calculated_from_time_and_distance(app_ctx):
    # pace = (time_seconds / distance_meters) * 500
    w = _map_result_to_workout(_raw_result(distance=2000, time=4800))
    assert w.avg_pace_seconds == round((480 / 2000) * 500)  # 120


def test_pace_is_none_without_time_or_distance(app_ctx):
    w = _map_result_to_workout(_raw_result(time=0))
    assert w.avg_pace_seconds is None

    w2 = _map_result_to_workout(_raw_result(distance=0))
    assert w2.avg_pace_seconds is None


def test_stroke_rate_and_calories_coerced_to_int(app_ctx):
    w = _map_result_to_workout(_raw_result(stroke_rate="26", calories_total="310"))
    assert w.avg_stroke_rate == 26
    assert isinstance(w.avg_stroke_rate, int)
    assert w.total_calories == 310
    assert isinstance(w.total_calories, int)


def test_missing_optional_fields_become_none(app_ctx):
    w = _map_result_to_workout(_raw_result(stroke_rate=None, calories_total=None))
    assert w.avg_stroke_rate is None
    assert w.total_calories is None


def test_malformed_date_falls_back_to_today(app_ctx):
    w = _map_result_to_workout(_raw_result(date="not-a-date"))
    assert w.workout_date == date.today()


def test_missing_date_falls_back_to_today(app_ctx):
    w = _map_result_to_workout(_raw_result(date=""))
    assert w.workout_date == date.today()
