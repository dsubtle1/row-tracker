"""
Route tests for blueprints/wod.py — Workout of the Day pages and APIs.

wod_engine.py's generation logic (periodization, target pace, templates)
already has its own dedicated test file; these confirm the routes call it
correctly, persist WodHistory rows, and return the right status/shape.
"""

from datetime import date

from models import WodHistory, db


def test_wod_page_auto_creates_todays_wod(client, full_app_ctx):
    resp = client.get("/wod")
    assert resp.status_code == 200
    assert WodHistory.query.filter_by(generated_date=date.today()).count() == 1


def test_wod_page_reuses_existing_today_row(client, full_app_ctx):
    first = client.get("/wod")
    assert first.status_code == 200
    count_after_first = WodHistory.query.filter_by(generated_date=date.today()).count()

    second = full_app_ctx.test_client().get("/wod")
    assert second.status_code == 200
    assert WodHistory.query.filter_by(generated_date=date.today()).count() == count_after_first


def test_wod_generate_adds_a_new_row_for_today(client, full_app_ctx):
    """
    generate_wod()+save_wod() always inserts — get_or_create_today() then
    picks the most recent row for the date, so Force Regenerate effectively
    replaces what's *shown* without deleting history.
    """
    client.get("/wod")  # seed today's row
    before_count = WodHistory.query.filter_by(generated_date=date.today()).count()

    resp = client.post("/wod/generate")
    assert resp.status_code == 302
    assert resp.headers["Location"].endswith("/wod")

    after_count = WodHistory.query.filter_by(generated_date=date.today()).count()
    assert after_count == before_count + 1


def test_wod_complete_marks_completed(client, full_app_ctx):
    client.get("/wod")
    row = WodHistory.query.filter_by(generated_date=date.today()).first()

    resp = client.post("/wod/complete", data={"wod_id": row.id})
    assert resp.status_code == 302

    refreshed = full_app_ctx.test_client().get("/wod")
    assert refreshed.status_code == 200
    updated = db.session.get(WodHistory, row.id)
    assert updated.completed is True


def test_wod_complete_links_actual_workout(client, full_make_workout):
    client.get("/wod")
    row = WodHistory.query.filter_by(generated_date=date.today()).first()
    workout = full_make_workout(id=1, distance_meters=2000, time_seconds=480)

    client.post("/wod/complete", data={"wod_id": row.id, "workout_id": workout.id})

    updated = db.session.get(WodHistory, row.id)
    assert updated.completed is True
    assert updated.actual_workout_id == workout.id


def test_wod_complete_missing_id_is_404(client):
    resp = client.post("/wod/complete", data={"wod_id": 999999})
    assert resp.status_code == 404


# --------------------------------------------------------------------------- #
#  Auto-link on completion + actual-vs-planned comparison                    #
#                                                                              #
#  The UI has never had a manual workout picker (only the wod_id form field  #
#  is ever submitted), so auto-linking the one same-day workout is what      #
#  makes actual_workout_id — and the comparison it powers — reachable at     #
#  all in normal use.                                                        #
# --------------------------------------------------------------------------- #

def test_wod_complete_auto_links_the_one_same_day_workout(client, full_make_workout):
    client.get("/wod")
    row = WodHistory.query.filter_by(generated_date=date.today()).first()
    workout = full_make_workout(id=1, distance_meters=2000, time_seconds=480)

    client.post("/wod/complete", data={"wod_id": row.id})   # no workout_id given

    updated = db.session.get(WodHistory, row.id)
    assert updated.actual_workout_id == workout.id


def test_wod_complete_does_not_auto_link_when_ambiguous(client, full_make_workout):
    client.get("/wod")
    row = WodHistory.query.filter_by(generated_date=date.today()).first()
    full_make_workout(id=1, distance_meters=2000, time_seconds=480)
    full_make_workout(id=2, distance_meters=6000, time_seconds=1500)

    client.post("/wod/complete", data={"wod_id": row.id})

    updated = db.session.get(WodHistory, row.id)
    assert updated.actual_workout_id is None


def test_wod_complete_does_not_auto_link_a_workout_already_linked_elsewhere(client, full_make_workout):
    client.get("/wod")
    row1 = WodHistory.query.filter_by(generated_date=date.today()).first()
    workout = full_make_workout(id=1, distance_meters=2000, time_seconds=480)
    row1.actual_workout_id = workout.id
    db.session.commit()

    # A second WOD row for the same date (e.g. after a Force Regenerate) must
    # not steal the workout that's already linked to the first.
    row2 = WodHistory(generated_date=date.today(), wod_type="steady_state", wod_json={}, completed=False)
    db.session.add(row2)
    db.session.commit()

    client.post("/wod/complete", data={"wod_id": row2.id})

    assert db.session.get(WodHistory, row2.id).actual_workout_id is None


def test_wod_complete_explicit_workout_id_skips_auto_link(client, full_make_workout):
    client.get("/wod")
    row = WodHistory.query.filter_by(generated_date=date.today()).first()
    # Two same-day candidates would make auto-link ambiguous — an explicit
    # choice must still work regardless.
    full_make_workout(id=1, distance_meters=2000, time_seconds=480, workout_date=date.today())
    chosen = full_make_workout(id=2, distance_meters=6000, time_seconds=1500, workout_date=date.today())

    client.post("/wod/complete", data={"wod_id": row.id, "workout_id": chosen.id})

    assert db.session.get(WodHistory, row.id).actual_workout_id == chosen.id


def test_wod_page_shows_hit_target_comparison(client, full_app_ctx, full_make_workout):
    from wod_engine import generate_wod
    from wod_engine import save_wod

    spec = generate_wod()
    row = save_wod(spec)
    # Match the actual workout's pace to the generated target almost exactly.
    workout = full_make_workout(id=1, avg_pace_seconds=spec.target_pace_seconds,
                                 distance_meters=2000, time_seconds=spec.target_pace_seconds * 4,
                                 workout_date=row.generated_date)
    row.actual_workout_id = workout.id
    row.completed = True
    db.session.commit()

    resp = client.get("/wod")
    assert b"Hit target pace within" in resp.data


def test_wod_page_shows_miss_when_pace_is_far_off(client, full_app_ctx, full_make_workout):
    from wod_engine import generate_wod, save_wod

    spec = generate_wod()
    row = save_wod(spec)
    slow_pace = spec.target_pace_seconds + 20   # well outside a 2% margin
    workout = full_make_workout(id=1, avg_pace_seconds=slow_pace,
                                 distance_meters=2000, time_seconds=slow_pace * 4,
                                 workout_date=row.generated_date)
    row.actual_workout_id = workout.id
    row.completed = True
    db.session.commit()

    resp = client.get("/wod")
    assert b"off target" in resp.data


def test_wod_history_current_month(client):
    resp = client.get("/wod/history")
    assert resp.status_code == 200


def test_wod_history_specific_month(client):
    resp = client.get("/wod/history?year=2024&month=3")
    assert resp.status_code == 200


def test_wod_history_invalid_month_falls_back_to_today(client):
    resp = client.get("/wod/history?year=2024&month=13")
    assert resp.status_code == 200


def test_wod_library(client):
    resp = client.get("/wod/library")
    assert resp.status_code == 200


def test_wod_random_generates_and_redirects(client):
    resp = client.post("/wod/random", data={
        "intensity": "medium", "effort": "medium", "wod_type": "steady_state", "notes": "",
    })
    assert resp.status_code == 302
    assert "/wod/random/" in resp.headers["Location"]


def test_wod_random_result_page(client, full_app_ctx):
    post_resp = client.post("/wod/random", data={
        "intensity": "light", "effort": "low", "wod_type": "surprise", "notes": "",
    })
    wod_id = post_resp.headers["Location"].rstrip("/").split("/")[-1]

    resp = full_app_ctx.test_client().get(f"/wod/random/{wod_id}")
    assert resp.status_code == 200


def test_wod_random_result_missing_is_404(client):
    resp = client.get("/wod/random/999999")
    assert resp.status_code == 404


def test_api_wod_today(client):
    resp = client.get("/api/wod/today")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["date"] == date.today().isoformat()
    assert "target_pace_str" in data


def test_api_wod_day_exists(client):
    client.get("/wod")  # seed today's row
    resp = client.get(f"/api/wod/day?date={date.today().isoformat()}")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["exists"] is True


def test_api_wod_day_does_not_exist(client):
    resp = client.get("/api/wod/day?date=2020-01-01")
    assert resp.status_code == 200
    assert resp.get_json() == {"exists": False}


def test_api_wod_day_invalid_date(client):
    resp = client.get("/api/wod/day?date=nope")
    assert resp.status_code == 400
