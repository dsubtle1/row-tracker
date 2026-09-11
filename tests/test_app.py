"""Tests for app.py's own routes/handlers (not blueprint routes)."""


def test_unknown_url_gets_the_branded_404_page_not_the_raw_werkzeug_page(client):
    resp = client.get("/this-page-does-not-exist")
    assert resp.status_code == 404
    assert b"Back to the Dashboard" in resp.data
    assert b"Werkzeug" not in resp.data
