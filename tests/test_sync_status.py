"""
Tests for sync_status.py — the single-row "is the sync actually working"
tracker that powers the Dashboard's last-synced indicator.
"""

from models import SyncStatus
import sync_status


def test_get_status_is_none_before_any_sync(full_app_ctx):
    assert sync_status.get_status() is None


def test_record_success_creates_the_row(full_app_ctx):
    sync_status.record_success("3 new workouts")

    status = sync_status.get_status()
    assert status is not None
    assert status.last_result == "3 new workouts"
    assert status.last_error is None
    assert status.last_attempt_at is not None
    assert status.last_success_at is not None
    assert status.last_attempt_at == status.last_success_at


def test_record_failure_creates_the_row_without_a_success_time(full_app_ctx):
    sync_status.record_failure("C2 API returned 401")

    status = sync_status.get_status()
    assert status is not None
    assert status.last_error == "C2 API returned 401"
    assert status.last_success_at is None
    assert status.last_attempt_at is not None


def test_record_success_clears_a_previous_error(full_app_ctx):
    sync_status.record_failure("C2 API returned 401")
    sync_status.record_success("Sync complete. 1 new workouts added.")

    status = sync_status.get_status()
    assert status.last_error is None
    assert status.last_success_at is not None


def test_record_failure_after_success_keeps_last_success_time(full_app_ctx):
    sync_status.record_success("Sync complete. 0 new workouts added.")
    first_success = sync_status.get_status().last_success_at

    sync_status.record_failure("C2 API request failed: timeout")

    status = sync_status.get_status()
    assert status.last_error == "C2 API request failed: timeout"
    assert status.last_success_at == first_success  # untouched by the failure
    assert status.last_attempt_at >= first_success


def test_only_one_row_ever_exists(full_app_ctx):
    sync_status.record_success("first")
    sync_status.record_failure("second")
    sync_status.record_success("third")

    assert SyncStatus.query.count() == 1
