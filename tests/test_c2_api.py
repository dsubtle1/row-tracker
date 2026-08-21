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


def test_maps_rest_distance_from_interval_workouts(app_ctx):
    w = _map_result_to_workout(_raw_result(rest_distance=350))
    assert w.rest_distance_meters == 350
    assert w.distance_meters == 2000  # work distance untouched by rest


def test_rest_distance_defaults_to_zero_when_absent(app_ctx):
    w = _map_result_to_workout(_raw_result())
    assert w.rest_distance_meters == 0


def test_maps_stroke_count(app_ctx):
    w = _map_result_to_workout(_raw_result(stroke_count=412))
    assert w.stroke_count == 412


def test_stroke_count_is_none_when_absent(app_ctx):
    w = _map_result_to_workout(_raw_result())
    assert w.stroke_count is None


def test_maps_heart_rate_max(app_ctx):
    w = _map_result_to_workout(_raw_result(heart_rate={"min": 110, "average": 145, "max": 172, "ending": 168}))
    assert w.heart_rate_max == 172


def test_heart_rate_max_is_none_when_absent(app_ctx):
    w = _map_result_to_workout(_raw_result())
    assert w.heart_rate_max is None


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


# --------------------------------------------------------------------------- #
#  get_results() / sync_workouts() — last_error surfacing                     #
#                                                                              #
#  A 401 or network failure must be distinguishable from a call that          #
#  genuinely succeeded and found nothing new — otherwise an expired/bad       #
#  token looks identical to "already up to date" to every caller.             #
# --------------------------------------------------------------------------- #

def test_get_results_success_clears_last_error(monkeypatch):
    monkeypatch.setattr(
        "c2_api.requests.get",
        lambda *a, **k: _FakeResponse(200, {"data": [], "meta": {"pagination": {"total_pages": 1}}}),
    )
    client = _client()
    client.last_error = "stale error from a previous call"
    client.get_results()
    assert client.last_error is None


def test_get_results_follows_pagination_past_page_one(monkeypatch):
    # C2 nests page count under meta.pagination.total_pages, not meta.last_page —
    # reading the wrong key silently capped every sync at 100 results (page 1).
    pages = {
        1: {"data": [{"id": 1}], "meta": {"pagination": {"total_pages": 3}}},
        2: {"data": [{"id": 2}], "meta": {"pagination": {"total_pages": 3}}},
        3: {"data": [{"id": 3}], "meta": {"pagination": {"total_pages": 3}}},
    }

    def _fake_get(*a, **k):
        page = k["params"]["page"]
        return _FakeResponse(200, pages[page])

    monkeypatch.setattr("c2_api.requests.get", _fake_get)
    client = _client()
    results = client.get_results()
    assert [r["id"] for r in results] == [1, 2, 3]


def test_get_results_401_sets_last_error(monkeypatch):
    monkeypatch.setattr("c2_api.requests.get", lambda *a, **k: _FakeResponse(401))
    client = _client()
    results = client.get_results()
    assert results == []
    assert client.last_error is not None
    assert "401" in client.last_error


def test_get_results_request_exception_sets_last_error(monkeypatch):
    import requests

    def _raise(*a, **k):
        raise requests.ConnectionError("boom")

    monkeypatch.setattr("c2_api.requests.get", _raise)
    monkeypatch.setattr("c2_api.time.sleep", lambda *a: None)
    client = _client()
    results = client.get_results()
    assert results == []
    assert client.last_error is not None


def test_get_results_retries_transient_failure_then_succeeds(monkeypatch):
    # A bare 500 (seen from C2's API in production) shouldn't fail the whole
    # sync if a retry a couple seconds later would have worked.
    calls = {"n": 0}

    def _flaky_get(*a, **k):
        calls["n"] += 1
        if calls["n"] < 2:
            return _FakeResponse(500)
        return _FakeResponse(200, {"data": [{"id": 1}], "meta": {"pagination": {"total_pages": 1}}})

    monkeypatch.setattr("c2_api.requests.get", _flaky_get)
    monkeypatch.setattr("c2_api.time.sleep", lambda *a: None)
    client = _client()
    results = client.get_results()
    assert [r["id"] for r in results] == [1]
    assert client.last_error is None
    assert calls["n"] == 2


def test_sync_workouts_reports_error_on_401(monkeypatch, full_app_ctx):
    monkeypatch.setattr("c2_api.requests.get", lambda *a, **k: _FakeResponse(401))
    client = _client()
    result = client.sync_workouts()
    assert result["errors"] == 1
    assert "401" in result["message"]
    assert result["inserted"] == 0


def test_sync_workouts_genuinely_empty_is_not_an_error(monkeypatch, full_app_ctx):
    monkeypatch.setattr(
        "c2_api.requests.get",
        lambda *a, **k: _FakeResponse(200, {"data": [], "meta": {"pagination": {"total_pages": 1}}}),
    )
    client = _client()
    result = client.sync_workouts()
    assert result["errors"] == 0
    assert result["message"] == "No new results from C2 API."
