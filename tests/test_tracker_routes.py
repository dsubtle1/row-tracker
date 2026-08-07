"""
Route tests for blueprints/tracker.py — dashboard, workouts, PBs, charts,
sync, CSV import/export, static pages.

These exercise the real app factory (see conftest.full_app) rather than
re-testing business logic already covered by test_pb_engine.py /
test_badge_engine.py — the goal is confirming each route is wired up,
renders without a Jinja error, and returns the right shape/status.
"""

import io

from models import PersonalBest


# --------------------------------------------------------------------------- #
#  Dashboard / pages                                                          #
# --------------------------------------------------------------------------- #

def test_dashboard_loads_empty(client):
    resp = client.get("/")
    assert resp.status_code == 200
    assert b"Row Tracker" in resp.data


def test_dashboard_loads_with_data(client, full_make_workout):
    full_make_workout(id=1, distance_meters=2000, time_seconds=480)
    resp = client.get("/")
    assert resp.status_code == 200


def test_faq_and_quickstart_pages(client):
    assert client.get("/faq").status_code == 200
    assert client.get("/quickstart").status_code == 200


def test_app_version_is_read_and_rendered(full_app, client):
    # VERSION file exists and parses as dotted digits, e.g. "0.9.0"
    assert full_app.config["VERSION"] != "0.0.0-dev"
    parts = full_app.config["VERSION"].split(".")
    assert len(parts) == 3
    assert all(p.isdigit() for p in parts)

    # rendered into the site-wide footer via the app_version Jinja global
    resp = client.get("/")
    assert f"v{full_app.config['VERSION']}".encode() in resp.data


def test_auth_callback(client):
    resp = client.get("/auth/callback")
    assert resp.status_code == 200
    assert resp.get_json()["status"] == "ok"


# --------------------------------------------------------------------------- #
#  Workout list / detail                                                      #
# --------------------------------------------------------------------------- #

def test_workout_list_empty(client):
    resp = client.get("/workouts")
    assert resp.status_code == 200


def test_workout_list_with_data(client, full_make_workout):
    for i in range(1, 4):
        full_make_workout(id=i, distance_meters=2000, time_seconds=480)
    resp = client.get("/workouts")
    assert resp.status_code == 200


def test_workout_detail_found(client, full_make_workout):
    full_make_workout(id=42, distance_meters=2000, time_seconds=480)
    resp = client.get("/workouts/42")
    assert resp.status_code == 200


def test_workout_detail_missing_is_404(client):
    resp = client.get("/workouts/999999")
    assert resp.status_code == 404


# --------------------------------------------------------------------------- #
#  Personal bests                                                             #
# --------------------------------------------------------------------------- #

def test_pb_page_empty(client):
    resp = client.get("/pb")
    assert resp.status_code == 200


def test_pb_page_with_data(client, full_app_ctx):
    from models import db
    db.session.add(PersonalBest(category="2000m", value_seconds=450, achieved_date=None))
    db.session.commit()
    resp = full_app_ctx.test_client().get("/pb")
    assert resp.status_code == 200


# --------------------------------------------------------------------------- #
#  Charts (HTML shells) + JSON data APIs                                      #
# --------------------------------------------------------------------------- #

def test_chart_pages(client):
    assert client.get("/charts/pace").status_code == 200
    assert client.get("/charts/efficiency").status_code == 200
    assert client.get("/charts/load").status_code == 200


def test_api_heatmap(client):
    resp = client.get("/api/data/heatmap")
    assert resp.status_code == 200
    assert isinstance(resp.get_json(), list)


def test_api_summary_empty(client):
    resp = client.get("/api/data/summary")
    data = resp.get_json()
    assert resp.status_code == 200
    assert data["lifetime_meters"] == 0
    assert data["total_workouts"] == 0
    assert data["last_workout"]["date"] is None


def test_api_summary_with_data(client, full_make_workout):
    full_make_workout(id=1, distance_meters=2000, time_seconds=480)
    resp = client.get("/api/data/summary")
    data = resp.get_json()
    assert data["lifetime_meters"] == 2000
    assert data["total_workouts"] == 1
    assert data["last_workout"]["distance"] == 2000


def test_api_pace_and_efficiency_and_load(client, full_make_workout):
    full_make_workout(id=1, distance_meters=2000, time_seconds=480, avg_stroke_rate=24)
    assert client.get("/api/data/pace").status_code == 200
    assert client.get("/api/data/efficiency").status_code == 200
    assert client.get("/api/data/load").status_code == 200


def test_api_workouts_by_date_valid(client, full_make_workout):
    w = full_make_workout(id=1, distance_meters=2000, time_seconds=480)
    resp = client.get(f"/api/data/workouts_by_date?date={w.workout_date.isoformat()}")
    assert resp.status_code == 200
    data = resp.get_json()
    assert len(data) == 1
    assert data[0]["id"] == 1


def test_api_workouts_by_date_invalid(client):
    resp = client.get("/api/data/workouts_by_date?date=not-a-date")
    assert resp.status_code == 400


# --------------------------------------------------------------------------- #
#  Sync                                                                       #
# --------------------------------------------------------------------------- #

def test_sync_without_credentials_returns_400(client):
    """No C2 credentials configured in the test env — must fail fast, not touch the network."""
    resp = client.post("/sync")
    assert resp.status_code == 400
    assert "credentials" in resp.get_json()["message"].lower()


# --------------------------------------------------------------------------- #
#  CSV import                                                                 #
# --------------------------------------------------------------------------- #

def test_import_page_get(client):
    resp = client.get("/import")
    assert resp.status_code == 200


def test_import_csv_inserts_rower_rows(client, full_app_ctx):
    from models import Workout, db

    csv_content = (
        "Type,Log ID,Date,Work Time (Seconds),Work Distance,Pace,Stroke Rate/Cadence,Total Cal\n"
        "RowErg,555001,2024-01-15 08:00:00,480.0,2000,2:00.0,24,220\n"
        "SkiErg,555002,2024-01-16 08:00:00,480.0,2000,2:00.0,24,220\n"
    )
    data = {
        "csv_files": (io.BytesIO(csv_content.encode("utf-8")), "season.csv"),
    }
    resp = client.post("/import", data=data, content_type="multipart/form-data")
    assert resp.status_code == 200
    assert db.session.get(Workout, 555001) is not None
    assert db.session.get(Workout, 555002) is None  # SkiErg — filtered out


def test_import_rejects_non_csv_file(client):
    data = {"csv_files": (io.BytesIO(b"not a csv"), "notes.txt")}
    resp = client.post("/import", data=data, content_type="multipart/form-data")
    assert resp.status_code == 200
    assert b"Not a .csv file" in resp.data


# --------------------------------------------------------------------------- #
#  Data export                                                                #
# --------------------------------------------------------------------------- #

def test_export_page(client):
    resp = client.get("/export")
    assert resp.status_code == 200


def test_export_workouts_csv(client, full_make_workout):
    full_make_workout(id=1, distance_meters=2000, time_seconds=480)
    resp = client.get("/export/workouts.csv")
    assert resp.status_code == 200
    assert resp.mimetype == "text/csv"
    assert "attachment" in resp.headers["Content-Disposition"]
    body = resp.data.decode("utf-8")
    assert body.startswith("id,date,time_seconds")
    assert ",2000," in body


def test_export_workouts_json(client, full_make_workout):
    full_make_workout(id=1, distance_meters=2000, time_seconds=480)
    resp = client.get("/export/workouts.json")
    assert resp.status_code == 200
    assert "attachment" in resp.headers["Content-Disposition"]
    data = resp.get_json()
    assert len(data) == 1
    assert data[0]["distance_meters"] == 2000


def test_export_pbs_csv_and_json(client, full_app_ctx):
    from models import db
    db.session.add(PersonalBest(category="2000m", value_seconds=450))
    db.session.commit()

    csv_resp = full_app_ctx.test_client().get("/export/pbs.csv")
    assert csv_resp.status_code == 200
    assert "attachment" in csv_resp.headers["Content-Disposition"]
    assert "2000m" in csv_resp.data.decode("utf-8")

    json_resp = full_app_ctx.test_client().get("/export/pbs.json")
    assert json_resp.status_code == 200
    data = json_resp.get_json()
    assert data[0]["category"] == "2000m"


def test_export_empty_db_still_returns_valid_files(client):
    csv_resp = client.get("/export/workouts.csv")
    assert csv_resp.status_code == 200
    assert csv_resp.data.decode("utf-8").strip() == (
        "id,date,time_seconds,time_formatted,distance_meters,avg_pace_seconds,"
        "avg_pace_formatted,avg_stroke_rate,total_calories,synced_at"
    )
    json_resp = client.get("/export/workouts.json")
    assert json_resp.get_json() == []


# --------------------------------------------------------------------------- #
#  Static / PWA plumbing (registered directly on the app, not the blueprint)  #
# --------------------------------------------------------------------------- #

def test_service_worker_served_at_root_scope(client):
    resp = client.get("/sw.js")
    assert resp.status_code == 200
    assert resp.headers.get("Service-Worker-Allowed") == "/"
    assert resp.headers.get("Cache-Control") == "no-cache"
    assert resp.mimetype == "application/javascript"


def test_service_worker_cache_name_tracks_app_version(full_app, client):
    resp = client.get("/sw.js")
    version = full_app.config["VERSION"]
    assert f'CACHE_NAME = "row-tracker-static-v{version}"'.encode() in resp.data


def test_manifest_served(client):
    resp = client.get("/static/manifest.json")
    assert resp.status_code == 200
    assert resp.get_json()["name"] == "Row Tracker"
