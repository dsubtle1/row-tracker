"""
Route tests for blueprints/gamification.py — hub, badges, journeys
(Rhine/Holland/Trans-Canada/Route 66), season challenges, versus board.

badge_engine.py's evaluation rules already have their own dedicated test
file; these confirm the routes render, journeys can be started/restarted,
and the JSON APIs return the expected shape.
"""

import pytest

from models import Journey
from blueprints.gamification import (
    _layout_geo_route,
    RHINE_WAYPOINTS, HOLLAND_WAYPOINTS, ROUTE66_WAYPOINTS, TRANSCAN_WAYPOINTS,
)


# --------------------------------------------------------------------------- #
#  _layout_geo_route() — marker interpolation for the real Leaflet maps       #
# --------------------------------------------------------------------------- #

def test_layout_geo_route_marker_at_first_waypoint_when_pct_zero():
    waypoints = [{"lat": 10.0, "lon": 20.0}, {"lat": 12.0, "lon": 24.0}, {"lat": 14.0, "lon": 28.0}]
    out, marker = _layout_geo_route(waypoints, pct=0)
    assert out is waypoints
    assert marker == {"lat": 10.0, "lon": 20.0}


def test_layout_geo_route_marker_at_last_waypoint_when_pct_100():
    waypoints = [{"lat": 10.0, "lon": 20.0}, {"lat": 12.0, "lon": 24.0}, {"lat": 14.0, "lon": 28.0}]
    _, marker = _layout_geo_route(waypoints, pct=100)
    assert marker == {"lat": 14.0, "lon": 28.0}


def test_layout_geo_route_marker_interpolates_between_flanking_waypoints():
    # 3 waypoints -> 2 index-segments; 50% overall progress lands exactly on
    # the middle waypoint (same index-based interpolation the old SVG used).
    waypoints = [{"lat": 0.0, "lon": 0.0}, {"lat": 10.0, "lon": 10.0}, {"lat": 20.0, "lon": 20.0}]
    _, marker = _layout_geo_route(waypoints, pct=50)
    assert marker == {"lat": 10.0, "lon": 10.0}

    _, marker = _layout_geo_route(waypoints, pct=25)
    assert marker["lat"] == 5.0
    assert marker["lon"] == 5.0


@pytest.mark.parametrize("waypoints", [RHINE_WAYPOINTS, HOLLAND_WAYPOINTS, ROUTE66_WAYPOINTS, TRANSCAN_WAYPOINTS])
def test_every_route_waypoint_has_real_coordinates(waypoints):
    for wp in waypoints:
        assert -90 <= wp["lat"] <= 90
        assert -180 <= wp["lon"] <= 180
        # A (0, 0) placeholder would pass the range check above but is never
        # a real waypoint on any of these four routes (mid-Atlantic/Gulf of
        # Guinea) — catches a copy-paste-left-blank mistake.
        assert (wp["lat"], wp["lon"]) != (0.0, 0.0)


# --------------------------------------------------------------------------- #
#  Hub / badges                                                               #
# --------------------------------------------------------------------------- #

def test_hub_page_empty(client):
    resp = client.get("/gamification/")
    assert resp.status_code == 200


def test_hub_page_with_data(client, full_make_workout):
    full_make_workout(id=1, distance_meters=2000, time_seconds=480)
    resp = client.get("/gamification/")
    assert resp.status_code == 200


def test_badges_page(client):
    resp = client.get("/gamification/badges")
    assert resp.status_code == 200


def test_api_badges_check(client):
    resp = client.post("/gamification/api/badges/check")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["status"] == "ok"
    assert isinstance(data["newly_awarded"], list)


def test_api_badges_check_emails_newly_awarded(client, full_make_workout, sent_messages):
    """A workout crossing the 2k-legend threshold should both award the
    badge and send exactly one notification email for it."""
    full_make_workout(id=1, distance_meters=2000, time_seconds=480)

    resp = client.post("/gamification/api/badges/check")
    data = resp.get_json()
    assert "2k_legend" in data["newly_awarded"]

    assert len(sent_messages) == 1
    assert "badge" in sent_messages[0].subject.lower()


def test_api_badges_check_no_email_when_nothing_new(client, sent_messages):
    resp = client.post("/gamification/api/badges/check")
    assert resp.get_json()["newly_awarded"] == []
    assert sent_messages == []


def test_api_badges_list(client):
    resp = client.get("/gamification/api/badges")
    assert resp.status_code == 200
    data = resp.get_json()
    assert isinstance(data, list)
    assert len(data) > 0  # seed_badges() runs at app creation
    assert "badge_key" in data[0]


# --------------------------------------------------------------------------- #
#  Journeys — page loads with no active journey                               #
# --------------------------------------------------------------------------- #

def test_journeys_hub_page(client):
    resp = client.get("/gamification/journeys")
    assert resp.status_code == 200


def test_route_pages_with_no_active_journey(client):
    assert client.get("/gamification/route").status_code == 200
    assert client.get("/gamification/route/holland").status_code == 200
    assert client.get("/gamification/route/transcan").status_code == 200
    assert client.get("/gamification/route/route66").status_code == 200


# --------------------------------------------------------------------------- #
#  Journeys — start / restart                                                 #
# --------------------------------------------------------------------------- #

def test_journey_start_creates_active_journey(client, full_app_ctx):
    resp = client.post("/gamification/journey/start")
    assert resp.status_code == 302
    assert resp.headers["Location"].endswith("/gamification/route")

    journeys = Journey.query.filter_by(route_key="rhine").all()
    assert len(journeys) == 1
    assert journeys[0].completed is False


def test_journey_restart_completes_previous_and_starts_new(client, full_app_ctx):
    client.post("/gamification/journey/start")
    client.post("/gamification/journey/start")  # restart

    journeys = Journey.query.filter_by(route_key="rhine").order_by(Journey.id).all()
    assert len(journeys) == 2
    assert journeys[0].completed is True   # old one force-completed
    assert journeys[1].completed is False  # new active one


def test_journey_start_holland_transcan_route66(client, full_app_ctx):
    client.post("/gamification/journey/holland/start")
    client.post("/gamification/journey/transcan/start")
    client.post("/gamification/journey/route66/start")

    assert Journey.query.filter_by(route_key="holland").count() == 1
    assert Journey.query.filter_by(route_key="transcan").count() == 1
    assert Journey.query.filter_by(route_key="route66").count() == 1


def test_route_page_reflects_active_journey(client, full_make_workout):
    client.post("/gamification/journey/start")
    full_make_workout(id=1, distance_meters=10_000, time_seconds=2400)
    resp = client.get("/gamification/route")
    assert resp.status_code == 200


# --------------------------------------------------------------------------- #
#  Season challenges / versus                                                 #
# --------------------------------------------------------------------------- #

def test_challenges_page(client):
    resp = client.get("/gamification/challenges")
    assert resp.status_code == 200


def test_versus_page(client):
    resp = client.get("/gamification/versus")
    assert resp.status_code == 200


def test_months_ago_start_lands_on_correct_calendar_month():
    """
    Regression test: the old implementation derived "3 months ago" via a
    fixed timedelta(days=89), which actually spanned a 3-month range rather
    than the single calendar month 3 months prior, and derived "12 months
    ago" by chaining off that already-wrong value instead of counting back
    from today — landing ~4-5 months back instead of 12.
    """
    from datetime import date
    from blueprints.gamification import _months_ago_start

    today = date(2026, 9, 9)
    assert _months_ago_start(today, 1)  == date(2026, 8, 1)
    assert _months_ago_start(today, 3)  == date(2026, 6, 1)
    assert _months_ago_start(today, 12) == date(2025, 9, 1)

    # Year-boundary case
    jan = date(2026, 1, 15)
    assert _months_ago_start(jan, 1)  == date(2025, 12, 1)
    assert _months_ago_start(jan, 12) == date(2025, 1, 1)


def test_versus_data_three_months_ago_is_exactly_one_month_wide(monkeypatch, client, full_app_ctx, full_make_workout):
    """
    The old bug summed a 3-month range (May-July) into the "3 months ago"
    column when today was in September, instead of just June — this pins
    a workout in the month that range incorrectly used to include.
    """
    import blueprints.gamification as gam
    from datetime import date

    class FixedDate(date):
        @classmethod
        def today(cls):
            return date(2026, 9, 9)

    monkeypatch.setattr(gam, "date", FixedDate)

    # Real "3 months ago" (June 2026) — must be included.
    full_make_workout(id=1, distance_meters=1000, time_seconds=240, workout_date=date(2026, 6, 15))
    # Previously wrongly swept into the same column (May 2026) — must not be.
    full_make_workout(id=2, distance_meters=5000, time_seconds=1200, workout_date=date(2026, 5, 15))

    data = gam._get_versus_data()
    three_mo_cell = data["rows"][0]["cells"]["three_months_ago"]
    assert three_mo_cell["raw"] == 1000


def test_api_challenges(client):
    resp = client.get("/gamification/api/challenges")
    assert resp.status_code == 200
    data = resp.get_json()
    assert "quarter" in data
    assert "pb_season" in data


def test_api_versus(client):
    resp = client.get("/gamification/api/versus")
    assert resp.status_code == 200
    data = resp.get_json()
    assert "rows" in data
    assert "col_order" in data


# --------------------------------------------------------------------------- #
#  Journey JSON APIs                                                          #
# --------------------------------------------------------------------------- #

def test_api_rhine_no_active_journey(client):
    resp = client.get("/gamification/api/rhine")
    data = resp.get_json()
    assert resp.status_code == 200
    assert data["active"] is False
    assert data["position_km"] == 0


def test_api_rhine_active_journey_position(client, full_make_workout):
    client.post("/gamification/journey/start")
    full_make_workout(id=1, distance_meters=82_000, time_seconds=20000)  # 10% of 820km route

    resp = client.get("/gamification/api/rhine")
    data = resp.get_json()
    assert data["active"] is True
    assert data["journey_metres"] == 82_000
    assert data["pct"] == 10.0


def test_api_holland_transcan_route66_shapes(client):
    for endpoint in ["/gamification/api/holland", "/gamification/api/transcan", "/gamification/api/route66"]:
        resp = client.get(endpoint)
        assert resp.status_code == 200
        data = resp.get_json()
        assert "waypoints" in data
        assert "active" in data
