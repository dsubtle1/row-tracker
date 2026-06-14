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


def init_scheduler(app):
    """
    Initialise and start the background scheduler.
    Call from the app factory after all blueprints are registered.
    """
    scheduler = BackgroundScheduler(timezone="America/Toronto")

    scheduler.add_job(
        func             = nightly_sync,
        trigger          = CronTrigger(hour=3, minute=0),
        id               = "nightly_sync",
        name             = "Nightly C2 sync",
        replace_existing = True,
    )

    scheduler.add_job(
        func             = recalculate_pbs,
        trigger          = CronTrigger(hour=3, minute=15),
        id               = "recalculate_pbs",
        name             = "Recalculate personal bests",
        replace_existing = True,
    )

    scheduler.add_job(
        func             = evaluate_badges,
        trigger          = CronTrigger(hour=3, minute=20),
        id               = "evaluate_badges",
        name             = "Evaluate badges",
        replace_existing = True,
    )

    scheduler.start()
    logger.info("Scheduler started.")
    return scheduler
