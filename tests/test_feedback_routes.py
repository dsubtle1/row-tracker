"""
Route tests for blueprints/feedback.py.

TESTING=true (set in conftest.full_app) makes Flask-Mail suppress actual
sends (MAIL_SUPPRESS_SEND defaults to app.testing), so these hit the real
route/Message-building code without opening an SMTP connection. Flask-Mail
still fires its email_dispatched signal even when suppressed, which lets
these tests inspect the composed message instead of only the JSON response.
"""

def test_submit_with_message_succeeds(client, sent_messages):
    resp = client.post("/feedback/submit", data={
        "category": "Bug",
        "name": "Tester",
        "message": "Something broke.",
        "page": "/dashboard",
    })
    assert resp.status_code == 200
    assert resp.get_json() == {"ok": True}

    assert len(sent_messages) == 1
    msg = sent_messages[0]
    assert "Bug" in msg.subject
    assert "Tester" in msg.subject
    assert "Something broke." in msg.body
    assert "/dashboard" in msg.body


def test_submit_without_message_is_rejected(client, sent_messages):
    resp = client.post("/feedback/submit", data={
        "category": "Bug",
        "name": "Tester",
        "message": "",
        "page": "/dashboard",
    })
    assert resp.status_code == 400
    data = resp.get_json()
    assert data["ok"] is False
    assert "required" in data["error"].lower()
    assert sent_messages == []  # rejected before any mail is composed


def test_submit_defaults_name_to_anonymous(client, sent_messages):
    resp = client.post("/feedback/submit", data={
        "category": "Suggestion",
        "message": "No name given.",
        "page": "/wod",
    })
    assert resp.status_code == 200
    assert "Anonymous" in sent_messages[0].body
    assert "from: Anonymous" in sent_messages[0].subject
