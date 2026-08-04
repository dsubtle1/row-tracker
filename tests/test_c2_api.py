"""
Tests for c2_api.py — mapping a raw Concept2 API result dict to a Workout.

_map_result_to_workout is a pure transform (it instantiates a Workout but
never touches the session), so no DB fixture is required — a Flask app
context is still needed because models.py binds Workout to Flask-SQLAlchemy.
"""

from datetime import date

import pytest

from c2_api import C2ApiClient, _map_result_to_workout


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


def test_stroke_data_column_starts_empty_regardless_of_the_availability_flag(app_ctx):
    """
    result["stroke_data"] is just a boolean "detail exists on C2" flag, not
    the actual per-stroke array — the real array is fetched lazily via
    C2ApiClient.get_stroke_data() from the workout detail page, so the
    column must start out None at sync time either way.
    """
    w = _map_result_to_workout(_raw_result(stroke_data=True))
    assert w.stroke_data is None

    w2 = _map_result_to_workout(_raw_result(stroke_data=False))
    assert w2.stroke_data is None


# ---------------------------------------------------------------------------
# C2ApiClient.get_stroke_data
# ---------------------------------------------------------------------------

class _FakeResponse:
    def __init__(self, status_code=200, json_data=None):
        self.status_code = status_code
        self._json_data = json_data or {}

    def raise_for_status(self):
        if self.status_code >= 400:
            import requests
            raise requests.HTTPError(f"{self.status_code} error")

    def json(self):
        return self._json_data


def _client():
    return C2ApiClient(client_id="id", client_secret="secret", refresh_token="token")


def test_get_stroke_data_returns_the_stroke_array(monkeypatch):
    strokes = [{"t": 11, "d": 27, "p": 2082, "spm": 0, "hr": 150}]
    monkeypatch.setattr("c2_api.requests.get", lambda *a, **k: _FakeResponse(200, {"data": strokes}))

    client = _client()
    result = client.get_stroke_data(12345)
    assert result == strokes


def test_get_stroke_data_refreshes_token_if_missing(monkeypatch):
    monkeypatch.setattr("c2_api.requests.get", lambda *a, **k: _FakeResponse(200, {"data": []}))
    client = _client()
    assert client.access_token is None

    client.get_stroke_data(12345)
    assert client.access_token == "token"


def test_get_stroke_data_returns_none_on_http_error(monkeypatch):
    monkeypatch.setattr("c2_api.requests.get", lambda *a, **k: _FakeResponse(404))
    client = _client()
    assert client.get_stroke_data(12345) is None


def test_get_stroke_data_returns_none_when_not_configured():
    client = C2ApiClient(client_id="", client_secret="", refresh_token="")
    assert client.get_stroke_data(12345) is None
