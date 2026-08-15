"""
Scheduler — APScheduler embedded jobs.
"""

import os
import logging

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

logger = logging.getLogger(__name__)

# BackgroundScheduler(timezone=...) does NOT propagate to a job's own
# CronTrigger unless that trigger is also given an explicit timezone — a
# CronTrigger constructed without one silently falls back to the container's
# OS clock instead. (Confirmed directly against apscheduler 3.11.3: a job
# added via CronTrigger(hour=3, minute=0) to a BackgroundScheduler(timezone=
# "America/Toronto") resolves to UTC, not Toronto, unless the timezone is
# also passed to CronTrigger itself.) Every trigger below passes this
# explicitly so the nightly schedule is correct regardless of what timezone
# the container's OS happens to be on.
SCHEDULER_TZ = os.environ.get("TZ", "America/Toronto")


def nightly_sync():
    """Nightly C2 API sync — runs at 03:00, see SCHEDULER_TZ."""
    from flask import current_app
    from c2_api import C2ApiClient
    import sync_status
    from notify import notify_job_failure

    app = current_app._get_current_object()

    client = C2ApiClient(
        client_id     = app.config.get("C2_CLIENT_ID", ""),
        client_secret = app.config.get("C2_CLIENT_SECRET", ""),
        refresh_token = app.config.get("C2_REFRESH_TOKEN", ""),
    )

    if not client.is_configured():
        logger.warning("Nightly sync skipped — C2 credentials not configured.")
        return

    with app.app_context():
        from notify import lifetime_meters, check_and_notify_milestone
        from blueprints.gamification import check_journey_completions

        try:
            before_m = lifetime_meters()
            result = client.sync_workouts()
            logger.info(f"Nightly sync result: {result}")
        except Exception as e:
            # sync_workouts() catches its own API/DB errors and reports them
            # via result["errors"] below rather than raising — this is a
            # backstop for anything genuinely unexpected.
            logger.error(f"Nightly sync failed: {e}")
            sync_status.record_failure(str(e))
            notify_job_failure("Nightly C2 sync", e)
            return

        if result.get("errors", 0) > 0:
            message = result.get("message", "Sync reported errors — see logs.")
            logger.error(f"Nightly sync reported errors: {message}")
            sync_status.record_failure(message)
            notify_job_failure("Nightly C2 sync", message)
            return

        sync_status.record_success(result.get("message", "Sync complete."))

        if result.get("inserted", 0) > 0:
            recalculate_pbs()
            evaluate_badges()
            check_and_notify_milestone(before_m, lifetime_meters())
            check_journey_completions()


def recalculate_pbs():
    """Recalculate personal bests after sync."""
    from pb_engine import recalculate_all_pbs
    from notify import notify_job_failure
    try:
        recalculate_all_pbs()
        logger.info("Personal bests recalculated.")
    except Exception as e:
        logger.error(f"PB recalculation failed: {e}")
        notify_job_failure("Recalculate personal bests", e)


def evaluate_badges():
    """Badge evaluation after sync."""
    from badge_engine import evaluate_badges as _evaluate
    from notify import notify_badges, notify_job_failure
    try:
        newly_awarded = _evaluate()
        if newly_awarded:
            logger.info(f"Badges awarded this sync: {newly_awarded}")
            notify_badges(newly_awarded)
        else:
            logger.info("Badge evaluation complete — no new badges.")
    except Exception as e:
        logger.error(f"Badge evaluation failed: {e}")
        notify_job_failure("Evaluate badges", e)


def run_backup():
    """Nightly database snapshot with retention pruning."""
    from flask import current_app
    from backup import backup_database
    from notify import notify_job_failure
    try:
        backup_database(current_app._get_current_object())
    except Exception as e:
        logger.error(f"Database backup failed: {e}")
        notify_job_failure("Nightly database backup", e)


def init_scheduler(app):
    """
    Initialise and start the background scheduler.
    Call from the app factory after all blueprints are registered.

    APScheduler runs jobs on its own background thread, so none of them
    have a Flask application context by default — every job function here
    reaches for `current_app` or the `db` session, both of which need one.
    Each job is wrapped to push app.app_context() before running.
    """
    scheduler = BackgroundScheduler(timezone=SCHEDULER_TZ)

    def with_app_context(func):
        def wrapper():
            with app.app_context():
                func()
        return wrapper

    scheduler.add_job(
        func             = with_app_context(nightly_sync),
        trigger          = CronTrigger(hour=3, minute=0, timezone=SCHEDULER_TZ),
        id               = "nightly_sync",
        name             = "Nightly C2 sync",
        replace_existing = True,
    )

    scheduler.add_job(
        func             = with_app_context(recalculate_pbs),
        trigger          = CronTrigger(hour=3, minute=15, timezone=SCHEDULER_TZ),
        id               = "recalculate_pbs",
        name             = "Recalculate personal bests",
        replace_existing = True,
    )

    scheduler.add_job(
        func             = with_app_context(evaluate_badges),
        trigger          = CronTrigger(hour=3, minute=20, timezone=SCHEDULER_TZ),
        id               = "evaluate_badges",
        name             = "Evaluate badges",
        replace_existing = True,
    )

    scheduler.add_job(
        func             = with_app_context(run_backup),
        trigger          = CronTrigger(hour=3, minute=30, timezone=SCHEDULER_TZ),
        id               = "run_backup",
        name             = "Nightly database backup",
        replace_existing = True,
    )

    scheduler.start()
    logger.info(f"Scheduler started (timezone={SCHEDULER_TZ}).")
    return scheduler
