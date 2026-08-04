"""
Shared pytest fixtures for the engine test suite.

Engine modules (pb_engine, badge_engine, wod_engine, ...) talk to the
database through the module-level `db` object in models.py, so tests
just need a Flask app context bound to a throwaway database — they
don't need the full app.py factory (blueprints, mail, scheduler).

The sqlite in-memory DB is kept alive for the life of one test via
StaticPool, so all queries within a test see the same data.
"""

from datetime import date, timedelta

import pytest
from flask import Flask
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
              workout_type="rower", commit=True):
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
