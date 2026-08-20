"""
Shared pytest fixtures for the engine test suite.

Engine modules (pb_engine, badge_engine, wod_engine, ...) talk to the
database through the module-level `db` object in models.py, so tests
just need a Flask app context bound to a throwaway database — they
don't need the full app.py factory (blueprints, mail, scheduler).

The sqlite in-memory DB is kept alive for the life of one test via
StaticPool, so all queries within a test see the same data.
"""

import os
from datetime import date, timedelta

import pytest
from flask import Flask
from flask_mail import email_dispatched
from sqlalchemy.pool import StaticPool

from models import db, Workout


@pytest.fixture()
def app():
    flask_app = Flask(__name__)
    flask_app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite://"
    flask_app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {
        "poolclass": StaticPool,
        "connect_args": {"check_same_thread": False},
    }
    db.init_app(flask_app)

    with flask_app.app_context():
        db.create_all()
        yield flask_app
        db.session.remove()
        db.drop_all()


@pytest.fixture()
def app_ctx(app):
    """Convenience alias — most engine tests just need an active app context."""
    with app.app_context():
        yield app


@pytest.fixture()
def make_workout(app_ctx):
    """
    Factory for a Workout row with sensible rower defaults.
    Pass overrides as kwargs; `id` must be unique per test.
    """
    created = []

    def _make(id, workout_date=None, distance_meters=2000, time_seconds=480,
              avg_pace_seconds=None, avg_stroke_rate=None, total_calories=None,
              rest_distance_meters=0, workout_type="rower", commit=True):
        if workout_date is None:
            workout_date = date.today()
        if avg_pace_seconds is None and distance_meters:
            avg_pace_seconds = round((time_seconds / distance_meters) * 500)

        w = Workout(
            id=id,
            workout_date=workout_date,
            workout_type=workout_type,
            time_seconds=time_seconds,
            distance_meters=distance_meters,
            rest_distance_meters=rest_distance_meters,
            avg_pace_seconds=avg_pace_seconds,
            avg_stroke_rate=avg_stroke_rate,
            total_calories=total_calories,
        )
        db.session.add(w)
        if commit:
            db.session.commit()
        created.append(w)
        return w

    yield _make


@pytest.fixture()
def days_ago():
    """Helper: date N days before today."""
    def _days_ago(n):
        return date.today() - timedelta(days=n)
    return _days_ago


# --------------------------------------------------------------------------- #
#  Full-app fixtures — for route/blueprint tests                              #
# --------------------------------------------------------------------------- #
#
# These build the real app via app.create_app() (blueprints, Jinja filters,
# CSRF, mail — everything the fixtures above deliberately skip) instead of
# a bare Flask app, so route tests exercise the actual wiring. A file-backed
# temp database is used rather than in-memory sqlite — the test client
# pushes its own app context per request, and a fresh in-memory db has no
# data across separate connections without StaticPool tricks, whereas a
# real file persists naturally between requests exactly like production.
#
# TESTING=true (read by create_app()) does two things that make this safe:
# it skips starting a real APScheduler background thread against a
# throwaway db, and it makes Flask-Mail suppress actual SMTP sends so
# /feedback/submit doesn't try to reach smtp.gmail.com.

@pytest.fixture()
def full_app(monkeypatch, tmp_path):
    monkeypatch.setenv("TESTING", "true")
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "test.db"))
    monkeypatch.setenv("SECRET_KEY", "test-secret-key")
    monkeypatch.setenv("C2_CLIENT_ID", "")
    monkeypatch.setenv("C2_CLIENT_SECRET", "")
    monkeypatch.setenv("C2_REFRESH_TOKEN", "")
    # A real-looking address, not empty — MAIL_DEFAULT_SENDER derives from
    # this, and Flask-Mail refuses to build a Message with no sender at all,
    # which would 500 every /feedback/submit test before suppression even
    # gets a chance to skip the (never-attempted) SMTP connection.
    monkeypatch.setenv("MAIL_USERNAME", "test@example.com")
    monkeypatch.setenv("MAIL_PASSWORD", "")

    from app import create_app
    flask_app = create_app()
    flask_app.config["WTF_CSRF_ENABLED"] = False

    yield flask_app


@pytest.fixture()
def full_app_ctx(full_app):
    with full_app.app_context():
        yield full_app


@pytest.fixture()
def client(full_app):
    return full_app.test_client()


@pytest.fixture()
def full_make_workout(full_app_ctx):
    """Same shape as make_workout, bound to the full_app's temp database."""
    created = []

    def _make(id, workout_date=None, distance_meters=2000, time_seconds=480,
              avg_pace_seconds=None, avg_stroke_rate=None, total_calories=None,
              rest_distance_meters=0, workout_type="rower", commit=True):
        if workout_date is None:
            workout_date = date.today()
        if avg_pace_seconds is None and distance_meters:
            avg_pace_seconds = round((time_seconds / distance_meters) * 500)

        w = Workout(
            id=id,
            workout_date=workout_date,
            workout_type=workout_type,
            time_seconds=time_seconds,
            distance_meters=distance_meters,
            rest_distance_meters=rest_distance_meters,
            avg_pace_seconds=avg_pace_seconds,
            avg_stroke_rate=avg_stroke_rate,
            total_calories=total_calories,
        )
        db.session.add(w)
        if commit:
            db.session.commit()
        created.append(w)
        return w

    yield _make


@pytest.fixture()
def sent_messages(full_app_ctx):
    """
    Capture Message objects Flask-Mail would have sent, via its
    email_dispatched signal — fires even when MAIL_SUPPRESS_SEND is on
    (see full_app's TESTING note above), so this inspects the actually
    composed email without opening an SMTP connection.
    """
    captured = []

    def _record(sender, message, **extra):
        captured.append(message)

    email_dispatched.connect(_record, full_app_ctx)
    yield captured
    email_dispatched.disconnect(_record, full_app_ctx)
