"""
Scheduler — APScheduler embedded jobs.
Phase 1C: nightly C2 sync fully implemented.
"""

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
import logging

logger = logging.getLogger(__name__)


def nightly_sync():
    """Nightly C2 API sync — runs at 03:00 America/Toronto."""
    from flask import current_app
    from c2_api import C2ApiClient

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
        result = client.sync_workouts()
        logger.info(f"Nightly sync result: {result}")

        if result.get("inserted", 0) > 0:
            recalculate_pbs()
            evaluate_badges()


def recalculate_pbs():
    """Recalculate personal bests after sync."""
    from pb_engine import recalculate_all_pbs
    try:
        recalculate_all_pbs()
        logger.info("Personal bests recalculated.")
    except Exception as e:
        logger.error(f"PB recalculation failed: {e}")


def evaluate_badges():
    """Badge evaluation after sync."""
    from badge_engine import evaluate_badges as _evaluate
    try:
        newly_awarded = _evaluate()
        if newly_awarded:
            logger.info(f"Badges awarded this sync: {newly_awarded}")
        else:
            logger.info("Badge evaluation complete — no new badges.")
    except Exception as e:
        logger.error(f"Badge evaluation failed: {e}")


def run_backup():
    """Nightly database snapshot with retention pruning."""
    from flask import current_app
    from backup import backup_database
    try:
        backup_database(current_app._get_current_object())
    except Exception as e:
        logger.error(f"Database backup failed: {e}")


def init_scheduler(app):
    """
    Initialise and start the background scheduler.
    Call from the app factory after all blueprints are registered.

    APScheduler runs jobs on its own background thread, so none of them
    have a Flask application context by default — every job function here
    reaches for `current_app` or the `db` session, both of which need one.
    Each job is wrapped to push app.app_context() before running.
    """
    scheduler = BackgroundScheduler(timezone="America/Toronto")

    def with_app_context(func):
        def wrapper():
            with app.app_context():
                func()
        return wrapper

    scheduler.add_job(
        func             = with_app_context(nightly_sync),
        trigger          = CronTrigger(hour=3, minute=0),
        id               = "nightly_sync",
        name             = "Nightly C2 sync",
        replace_existing = True,
    )

    scheduler.add_job(
        func             = with_app_context(recalculate_pbs),
        trigger          = CronTrigger(hour=3, minute=15),
        id               = "recalculate_pbs",
        name             = "Recalculate personal bests",
        replace_existing = True,
    )

    scheduler.add_job(
        func             = with_app_context(evaluate_badges),
        trigger          = CronTrigger(hour=3, minute=20),
        id               = "evaluate_badges",
        name             = "Evaluate badges",
        replace_existing = True,
    )

    scheduler.add_job(
        func             = with_app_context(run_backup),
        trigger          = CronTrigger(hour=3, minute=30),
        id               = "run_backup",
        name             = "Nightly database backup",
        replace_existing = True,
    )

    scheduler.start()
    logger.info("Scheduler started.")
    return scheduler
