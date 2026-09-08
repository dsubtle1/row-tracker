"""
Route tests for blueprints/tracker.py — dashboard, workouts, PBs, charts,
sync, CSV import/export, static pages.

These exercise the real app factory (see conftest.full_app) rather than
re-testing business logic already covered by test_pb_engine.py /
test_badge_engine.py — the goal is confirming each route is wired up,
renders without a Jinja error, and returns the right shape/status.
"""

import io
import re

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


def test_mobile_nav_has_every_desktop_nav_link(client):
    """
    Regression test: the "Insights" link was added to the desktop nav
    (templates/base.html) when that feature shipped, but never added to
    the mobile drawer, so it was invisible on phones for weeks. Every href
    in the desktop nav-links block should also appear in the mobile
    drawer's nav-links block.
    """
    html = client.get("/").data.decode()

    desktop_block = re.search(r'id="navLinks">(.*?)</div>\s*<div class="nav-actions"', html, re.S)
    mobile_block  = re.search(r'class="mobile-nav-links">(.*?)</div>\s*<div class="mobile-nav-footer"', html, re.S)
    assert desktop_block and mobile_block, "Couldn't locate nav blocks — base.html markup changed?"

    desktop_hrefs = set(re.findall(r'href="([^"]+)"', desktop_block.group(1)))
    mobile_hrefs  = set(re.findall(r'href="([^"]+)"', mobile_block.group(1)))

    assert desktop_hrefs, "Desktop nav block matched but contained no links"
    missing_from_mobile = desktop_hrefs - mobile_hrefs
    assert not missing_from_mobile, f"Links on desktop but missing from mobile nav: {missing_from_mobile}"


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


def test_workout_list_filters_by_date_range(client, full_make_workout):
    from datetime import date
    full_make_workout(id=1, workout_date=date(2026, 1, 1), distance_meters=2000, time_seconds=480)
    full_make_workout(id=2, workout_date=date(2026, 6, 1), distance_meters=2000, time_seconds=480)

    resp = client.get("/workouts?date_from=2026-05-01&date_to=2026-07-01")
    assert resp.status_code == 200
    assert b"2026-06-01" in resp.data
    assert b"2026-01-01" not in resp.data


def test_workout_list_filters_by_distance_range(client, full_make_workout):
    full_make_workout(id=1, distance_meters=2000, time_seconds=480)
    full_make_workout(id=2, distance_meters=10000, time_seconds=2400)

    resp = client.get("/workouts?min_distance=5000")
    assert resp.status_code == 200
    assert b"10,000" in resp.data
    assert b">2,000m<" not in resp.data


def test_workout_list_invalid_date_is_ignored_not_400(client, full_make_workout):
    full_make_workout(id=1, distance_meters=2000, time_seconds=480)
    resp = client.get("/workouts?date_from=not-a-date")
    assert resp.status_code == 200


def test_workout_list_no_matches_shows_clear_filters_message(client, full_make_workout):
    full_make_workout(id=1, distance_meters=2000, time_seconds=480)
    resp = client.get("/workouts?min_distance=999999")
    assert resp.status_code == 200
    assert b"No workouts match these filters" in resp.data


def test_workout_list_pagination_links_preserve_filters(client, full_make_workout):
    for i in range(1, 61):   # 60 rows > per_page=50, forces a second page
        full_make_workout(id=i, distance_meters=5000, time_seconds=1200)

    resp = client.get("/workouts?min_distance=1000")
    assert resp.status_code == 200
    assert b"min_distance=1000" in resp.data   # carried into the Next link
    assert b"Page 1 of 2" in resp.data


def test_workout_detail_found(client, full_make_workout):
    full_make_workout(id=42, distance_meters=2000, time_seconds=480)
    resp = client.get("/workouts/42")
    assert resp.status_code == 200


def test_workout_detail_missing_is_404(client):
    resp = client.get("/workouts/999999")
    assert resp.status_code == 404


# --------------------------------------------------------------------------- #
#  Unified Day View                                                           #
# --------------------------------------------------------------------------- #

def test_day_view_invalid_date_is_404(client):
    resp = client.get("/day/not-a-date")
    assert resp.status_code == 404


def test_day_view_empty_day_shows_empty_states(client, full_app_ctx):
    from datetime import date
    resp = client.get(f"/day/{date.today().isoformat()}")
    assert resp.status_code == 200
    assert b"No WOD was generated for this day" in resp.data
    assert b"No workouts synced for this day" in resp.data


def test_day_view_shows_a_workout_and_its_notes(client, full_app_ctx, full_make_workout):
    from datetime import date
    from models import db
    today = date.today()
    w = full_make_workout(id=1, distance_meters=2000, time_seconds=480, workout_date=today)
    w.notes = "Felt strong today"
    db.session.commit()

    resp = client.get(f"/day/{today.isoformat()}")
    assert resp.status_code == 200
    assert b"2,000m" in resp.data
    assert b"Felt strong today" in resp.data


def test_day_view_numbers_multiple_workouts(client, full_app_ctx, full_make_workout):
    from datetime import date
    today = date.today()
    full_make_workout(id=1, distance_meters=2000, time_seconds=480, workout_date=today)
    full_make_workout(id=2, distance_meters=5000, time_seconds=1200, workout_date=today)

    resp = client.get(f"/day/{today.isoformat()}")
    assert resp.status_code == 200
    assert b"Workout 1" in resp.data
    assert b"Workout 2" in resp.data


def test_day_view_shows_pb_banner(client, full_app_ctx, full_make_workout):
    from datetime import date
    from models import db, PersonalBest
    today = date.today()
    w = full_make_workout(id=1, distance_meters=2000, time_seconds=420, workout_date=today)
    db.session.add(PersonalBest(category="2000m", value_seconds=420, workout_id=w.id, achieved_date=today))
    db.session.commit()

    resp = client.get(f"/day/{today.isoformat()}")
    assert resp.status_code == 200
    assert b"New PB" in resp.data
    assert b"2000m" in resp.data


def test_day_view_shows_wod_and_comparison_when_linked(client, full_app_ctx, full_make_workout):
    from datetime import date
    from models import db
    from wod_engine import generate_wod, save_wod

    spec = generate_wod()
    row = save_wod(spec)
    workout = full_make_workout(
        id=1, avg_pace_seconds=spec.target_pace_seconds,
        distance_meters=2000, time_seconds=spec.target_pace_seconds * 4,
        workout_date=row.generated_date,
    )
    row.actual_workout_id = workout.id
    row.completed = True
    db.session.commit()

    resp = client.get(f"/day/{row.generated_date.isoformat()}")
    assert resp.status_code == 200
    assert b"Hit target pace within" in resp.data
    assert b"Completed" in resp.data


def test_day_view_links_from_workout_detail(client, full_app_ctx, full_make_workout):
    from datetime import date
    today = date.today()
    full_make_workout(id=1, distance_meters=2000, time_seconds=480, workout_date=today)
    resp = client.get("/workouts/1")
    assert f"/day/{today.isoformat()}".encode() in resp.data


def test_workout_detail_shows_existing_notes(client, full_app_ctx, full_make_workout):
    from models import db
    w = full_make_workout(id=1, distance_meters=2000, time_seconds=480)
    w.notes = "Felt strong today"
    db.session.commit()

    resp = client.get("/workouts/1")
    assert b"Felt strong today" in resp.data


def test_save_notes_sets_the_workout_notes(client, full_app_ctx, full_make_workout):
    from models import db, Workout
    full_make_workout(id=1, distance_meters=2000, time_seconds=480)

    resp = client.post("/workouts/1/notes", data={"notes": "New PB attempt, fell short"})
    assert resp.status_code == 302
    assert db.session.get(Workout, 1).notes == "New PB attempt, fell short"


def test_save_notes_strips_whitespace_and_empty_becomes_null(client, full_app_ctx, full_make_workout):
    from models import db, Workout
    full_make_workout(id=1, distance_meters=2000, time_seconds=480)

    client.post("/workouts/1/notes", data={"notes": "   "})
    assert db.session.get(Workout, 1).notes is None


def test_save_notes_truncates_to_2000_chars(client, full_app_ctx, full_make_workout):
    from models import db, Workout
    full_make_workout(id=1, distance_meters=2000, time_seconds=480)

    client.post("/workouts/1/notes", data={"notes": "x" * 3000})
    assert len(db.session.get(Workout, 1).notes) == 2000


def test_save_notes_missing_workout_is_404(client):
    resp = client.post("/workouts/999999/notes", data={"notes": "hi"})
    assert resp.status_code == 404


# --------------------------------------------------------------------------- #
#  Head-to-head workout comparison                                            #
# --------------------------------------------------------------------------- #

def _raw_json_with_splits(n, base_pace_tenths=1200):
    """A raw_json blob shaped like a real C2 result, with n even 500m splits."""
    return {"workout": {"splits": [
        {"time": base_pace_tenths, "distance": 500, "stroke_rate": 24, "calories_total": 12}
        for _ in range(n)
    ]}}


def test_workout_compare_missing_params_shows_prompt(client):
    resp = client.get("/workouts/compare")
    assert resp.status_code == 200
    assert b"Pick two workouts" in resp.data


def test_workout_compare_same_id_is_rejected(client, full_app_ctx, full_make_workout):
    w = full_make_workout(id=1, distance_meters=2000, time_seconds=480)
    w.raw_json = _raw_json_with_splits(4)
    from models import db
    db.session.commit()

    resp = client.get(f"/workouts/compare?a={w.id}&b={w.id}")
    assert resp.status_code == 200
    assert b"two different workouts" in resp.data


def test_workout_compare_missing_workout_is_reported(client, full_app_ctx, full_make_workout):
    w = full_make_workout(id=1, distance_meters=2000, time_seconds=480)
    w.raw_json = _raw_json_with_splits(4)
    from models import db
    db.session.commit()

    resp = client.get(f"/workouts/compare?a={w.id}&b=999999")
    assert resp.status_code == 200
    assert b"couldn&#39;t be found" in resp.data


def test_workout_compare_no_splits_shows_explanation(client, full_app_ctx, full_make_workout):
    # Neither workout has raw_json — e.g. both CSV-imported.
    w1 = full_make_workout(id=1, distance_meters=2000, time_seconds=480)
    w2 = full_make_workout(id=2, distance_meters=2000, time_seconds=470)

    resp = client.get(f"/workouts/compare?a={w1.id}&b={w2.id}")
    assert resp.status_code == 200
    assert b"no split data to compare" in resp.data


def test_workout_compare_renders_chart_data_for_two_valid_workouts(client, full_app_ctx, full_make_workout):
    from models import db
    w1 = full_make_workout(id=1, distance_meters=2000, time_seconds=480)
    w1.raw_json = _raw_json_with_splits(4, base_pace_tenths=1200)
    w2 = full_make_workout(id=2, distance_meters=2000, time_seconds=460)
    w2.raw_json = _raw_json_with_splits(4, base_pace_tenths=1150)
    db.session.commit()

    resp = client.get(f"/workouts/compare?a={w1.id}&b={w2.id}")
    assert resp.status_code == 200
    assert resp.data.count(b"pace_seconds") >= 8   # 4 splits each, in the JSON fed to Chart.js


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


def test_api_pb_progression_returns_the_staircase(client, full_make_workout):
    from datetime import date, timedelta
    today = date.today()
    full_make_workout(id=1, distance_meters=2000, time_seconds=460, workout_date=today - timedelta(days=10))
    full_make_workout(id=2, distance_meters=2000, time_seconds=440, workout_date=today - timedelta(days=1))
    resp = client.get("/api/data/pb_progression/2000m")
    assert resp.status_code == 200
    data = resp.get_json()
    assert len(data) >= 1
    assert data[-1]["value_seconds"] == 440


def test_api_pb_progression_unknown_category_is_404(client):
    resp = client.get("/api/data/pb_progression/not-a-category")
    assert resp.status_code == 404


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


def test_export_workouts_includes_notes_and_extra_fields(client, full_make_workout):
    from models import db
    w = full_make_workout(
        id=1, distance_meters=2000, time_seconds=480,
        rest_distance_meters=50, rest_time_seconds=20,
    )
    w.stroke_count = 200
    w.heart_rate_max = 175
    w.notes = "Great session, negative split"
    db.session.commit()

    csv_resp = client.get("/export/workouts.csv")
    body = csv_resp.data.decode("utf-8")
    assert "stroke_count" in body and "heart_rate_max" in body
    assert "200" in body and "175" in body
    assert "Great session, negative split" in body

    json_resp = client.get("/export/workouts.json")
    data = json_resp.get_json()[0]
    assert data["stroke_count"] == 200
    assert data["heart_rate_max"] == 175
    assert data["rest_distance_meters"] == 50
    assert data["rest_time_seconds"] == 20
    assert data["notes"] == "Great session, negative split"


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
        "avg_pace_formatted,avg_stroke_rate,total_calories,stroke_count,"
        "heart_rate_max,rest_distance_meters,rest_time_seconds,notes,synced_at"
    )
    json_resp = client.get("/export/workouts.json")
    assert json_resp.get_json() == []


# --------------------------------------------------------------------------- #
#  Backup restore                                                             #
# --------------------------------------------------------------------------- #

def _make_backup_file(full_app_ctx, filename, workout_id):
    """Snapshot the live db (after inserting one workout row) to backups/<filename>."""
    from datetime import date
    from models import db, Workout
    from blueprints.tracker import _db_path, _backup_dir, _sqlite_file_copy
    import os

    db.session.add(Workout(id=workout_id, workout_date=date(2026, 1, 1), workout_type="rower",
                            distance_meters=1000, time_seconds=240))
    db.session.commit()

    backup_dir = _backup_dir()
    os.makedirs(backup_dir, exist_ok=True)
    dest = os.path.join(backup_dir, filename)
    _sqlite_file_copy(_db_path(), dest)
    return dest


def test_export_page_lists_backups(client, full_app_ctx):
    _make_backup_file(full_app_ctx, "row_tracker_2020-01-01.db", workout_id=1)
    resp = client.get("/export")
    assert resp.status_code == 200
    assert b"row_tracker_2020-01-01.db" in resp.data or b"January 1, 2020" in resp.data


def test_restore_rejects_invalid_filename(client, full_app_ctx):
    resp = client.post("/restore", data={"filename": "../../etc/passwd"})
    assert resp.status_code == 200
    assert b"Invalid or missing backup file" in resp.data


def test_restore_rejects_nonexistent_backup(client, full_app_ctx):
    resp = client.post("/restore", data={"filename": "row_tracker_does-not-exist.db"})
    assert resp.status_code == 200
    assert b"Invalid or missing backup file" in resp.data


def test_restore_replaces_live_data_and_creates_safety_copy(client, full_app_ctx):
    from datetime import date
    from models import db, Workout
    from blueprints.tracker import _backup_dir
    import os

    # Snapshot with only workout id=1, then add id=2 to the live db afterward —
    # restoring the snapshot should make id=2 disappear again.
    _make_backup_file(full_app_ctx, "row_tracker_2020-01-01.db", workout_id=1)
    db.session.add(Workout(id=2, workout_date=date(2026, 1, 2), workout_type="rower",
                            distance_meters=2000, time_seconds=480))
    db.session.commit()

    resp = client.post("/restore", data={"filename": "row_tracker_2020-01-01.db"})
    assert resp.status_code == 200
    assert b"Restored from row_tracker_2020-01-01.db" in resp.data

    assert db.session.get(Workout, 1) is not None
    assert db.session.get(Workout, 2) is None

    safety_copies = [f for f in os.listdir(_backup_dir()) if f.startswith("row_tracker_prerestore_")]
    assert len(safety_copies) == 1


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
