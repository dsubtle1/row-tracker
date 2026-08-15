"""
Tracks the status of the C2 sync — last attempt, last success, and the
last error if any — independent of whether that sync happened to find
new workouts. Powers the Dashboard's "last synced" indicator and lets
the scheduler and the manual /sync route share one source of truth for
"is this actually working."

Single-row table: there's only ever one current status for this
single-user app. Every function here requires a Flask app context
(same as any other model access) and commits its own change.
"""

from datetime import datetime

from models import db, SyncStatus


def _get_or_create() -> SyncStatus:
    status = SyncStatus.query.first()
    if status is None:
        status = SyncStatus()
        db.session.add(status)
    return status


def record_success(summary: str) -> None:
    """Call after a sync completes with no errors, whether or not anything new arrived."""
    status = _get_or_create()
    now = datetime.utcnow()
    status.last_attempt_at = now
    status.last_success_at = now
    status.last_result     = summary
    status.last_error      = None
    db.session.commit()


def record_failure(error_message: str) -> None:
    """Call when a sync attempt fails — last_success_at is left untouched."""
    status = _get_or_create()
    status.last_attempt_at = datetime.utcnow()
    status.last_error      = str(error_message)[:2000]
    db.session.commit()


def get_status() -> SyncStatus | None:
    """Returns the current status row, or None if a sync has never been attempted."""
    return SyncStatus.query.first()
