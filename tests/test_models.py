"""Tests for Workout.total_distance_meters (work + rest, never mixed into pace/PBs)."""

from sqlalchemy import func

from models import db, Workout


def test_total_distance_meters_adds_rest(make_workout):
    w = make_workout(1, distance_meters=5000, rest_distance_meters=1200)
    assert w.total_distance_meters == 6200


def test_total_distance_meters_treats_null_rest_as_zero(make_workout):
    w = make_workout(2, distance_meters=5000, rest_distance_meters=None)
    assert w.total_distance_meters == 5000


def test_total_distance_meters_usable_in_sql_sum(make_workout):
    make_workout(1, distance_meters=5000, rest_distance_meters=1200)
    make_workout(2, distance_meters=3000, rest_distance_meters=None)
    total = db.session.query(func.sum(Workout.total_distance_meters)).scalar()
    assert total == 9200


def test_total_time_seconds_adds_rest(make_workout):
    w = make_workout(1, time_seconds=1200, rest_time_seconds=300)
    assert w.total_time_seconds == 1500


def test_total_time_seconds_treats_null_time_as_zero():
    # A workout with no time recorded at all shouldn't crash the property —
    # it should degrade to 0, same as a missing rest value.
    w = Workout(workout_type="rower", time_seconds=None, rest_time_seconds=200)
    assert w.total_time_seconds == 200
