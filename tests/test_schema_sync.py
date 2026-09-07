"""
Tests for app._sync_schema() — the auto-migration step that adds any model
column missing from the live database on startup (db.create_all() only
creates missing tables, never alters existing ones).

Simulates a "stale" database the way a real upgrade would produce one: a
workouts table built from an older, smaller set of columns than the
current model defines.
"""

import sqlite3

import pytest


@pytest.fixture()
def stale_db_path(tmp_path, monkeypatch):
    """A workouts table missing the `notes` column, like a pre-upgrade db."""
    db_file = tmp_path / "stale.db"
    conn = sqlite3.connect(str(db_file))
    conn.execute("""
        CREATE TABLE workouts (
            id INTEGER PRIMARY KEY,
            workout_date DATE NOT NULL,
            workout_type TEXT NOT NULL DEFAULT 'rower',
            distance_meters INTEGER
        )
    """)
    conn.commit()
    conn.close()

    monkeypatch.setenv("TESTING", "true")
    monkeypatch.setenv("DATABASE_PATH", str(db_file))
    monkeypatch.setenv("SECRET_KEY", "test-secret-key")
    monkeypatch.setenv("C2_CLIENT_ID", "")
    monkeypatch.setenv("C2_CLIENT_SECRET", "")
    monkeypatch.setenv("C2_REFRESH_TOKEN", "")
    monkeypatch.setenv("MAIL_USERNAME", "test@example.com")
    monkeypatch.setenv("MAIL_PASSWORD", "")
    return db_file


def _columns(db_path):
    conn = sqlite3.connect(str(db_path))
    cols = [row[1] for row in conn.execute("PRAGMA table_info(workouts)")]
    conn.close()
    return cols


def test_sync_schema_adds_missing_columns_to_an_existing_table(stale_db_path):
    assert "notes" not in _columns(stale_db_path)

    from app import create_app
    create_app()

    cols = _columns(stale_db_path)
    assert "notes" in cols
    assert "rest_distance_meters" in cols
    assert "heart_rate_max" in cols


def test_sync_schema_preserves_existing_data_in_the_table(stale_db_path):
    conn = sqlite3.connect(str(stale_db_path))
    conn.execute(
        "INSERT INTO workouts (id, workout_date, workout_type, distance_meters) VALUES (1, '2026-01-01', 'rower', 2000)"
    )
    conn.commit()
    conn.close()

    from app import create_app
    create_app()

    conn = sqlite3.connect(str(stale_db_path))
    row = conn.execute("SELECT id, distance_meters, notes FROM workouts WHERE id = 1").fetchone()
    conn.close()
    assert row == (1, 2000, None)


def test_sync_schema_is_idempotent_on_repeated_startup(stale_db_path):
    from app import create_app
    create_app()   # first "upgrade"
    create_app()   # second startup against the now-current schema — must not raise

    cols = _columns(stale_db_path)
    assert cols.count("notes") == 1


def test_sync_schema_noop_on_a_brand_new_database(tmp_path, monkeypatch):
    """A fresh install has no pre-existing tables at all — create_all() makes
    them with every current column, so _sync_schema() has nothing to add."""
    db_file = tmp_path / "fresh.db"
    monkeypatch.setenv("TESTING", "true")
    monkeypatch.setenv("DATABASE_PATH", str(db_file))
    monkeypatch.setenv("SECRET_KEY", "test-secret-key")
    monkeypatch.setenv("C2_CLIENT_ID", "")
    monkeypatch.setenv("C2_CLIENT_SECRET", "")
    monkeypatch.setenv("C2_REFRESH_TOKEN", "")
    monkeypatch.setenv("MAIL_USERNAME", "test@example.com")
    monkeypatch.setenv("MAIL_PASSWORD", "")

    from app import create_app
    create_app()

    assert "notes" in _columns(db_file)
