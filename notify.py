"""
Email notifications for badges, lifetime-metres milestones, and virtual
journey completions.

Reuses the same Flask-Mail setup the feedback form already has, but sends
to NOTIFY_EMAIL (defaults to MAIL_USERNAME) rather than the feedback
inbox — these are personal achievement pings for the one person running
this app, not incoming support mail.

Every send is best-effort: a failed SMTP connection is logged and
swallowed, never raised, so a flaky mail server can't break a sync.
"""

import logging
from flask import current_app
from flask_mail import Message
from sqlalchemy import func

from models import db, Workout, Badge

logger = logging.getLogger(__name__)

MILESTONES = [
    (100_000, "100k"), (250_000, "250k"), (500_000, "500k"),
    (1_000_000, "1M"), (2_000_000, "2M"), (5_000_000, "5M"),
    (10_000_000, "10M"), (25_000_000, "25M"), (50_000_000, "50M"),
    (100_000_000, "100M"),
]

JOURNEY_NAMES = {
    "rhine":    "Rhine River",
    "holland":  "Holland Tour",
    "transcan": "Trans-Canada Highway",
    "route66":  "Route 66",
}


def _send(subject, body):
    from app import mail

    recipient = current_app.config.get("NOTIFY_EMAIL", "")
    if not recipient:
        logger.warning(f"Notification skipped (no NOTIFY_EMAIL/MAIL_USERNAME configured): {subject!r}")
        return

    try:
        msg = Message(subject=subject, recipients=[recipient], body=body)
        mail.send(msg)
        logger.info(f"Notification sent: {subject!r}")
    except Exception as e:
        logger.error(f"Notification email failed ({subject!r}): {e}")


def lifetime_meters():
    """Current lifetime rower metres (work + rest) — used to snapshot before/after a sync."""
    return db.session.query(func.sum(Workout.total_distance_meters)).filter_by(workout_type="rower").scalar() or 0


def notify_badges(badge_keys):
    """Email a summary of newly earned badges. No-op if the list is empty."""
    if not badge_keys:
        return
    badges = Badge.query.filter(Badge.badge_key.in_(badge_keys)).all()
    if not badges:
        return

    lines = [f"🏅 {b.badge_name} — {b.badge_desc}" for b in badges]
    plural = "s" if len(badges) != 1 else ""
    subject = f"[Row Tracker] {len(badges)} badge{plural} earned!"
    body = f"New badge{plural}:\n\n" + "\n".join(lines) + "\n"
    _send(subject, body)


def check_and_notify_milestone(before_m, after_m):
    """Email if lifetime metres crossed one or more milestones since before_m."""
    crossed = [(m, label) for m, label in MILESTONES if before_m < m <= after_m]
    if not crossed:
        return

    highest_label = crossed[-1][1]
    subject = f"[Row Tracker] Milestone reached: {highest_label} metres!"
    if len(crossed) == 1:
        body = f"You've now rowed {after_m:,} lifetime metres, past the {highest_label} mark. 🚣\n"
    else:
        labels = ", ".join(label for _, label in crossed)
        body = f"You've now rowed {after_m:,} lifetime metres, passing {labels} in one go. 🚣\n"
    _send(subject, body)


def notify_job_failure(job_name, error):
    """
    Email that a nightly scheduled job failed and needs attention.

    Distinct from every other notify_* function here — those are happy-path
    achievement pings; this is the one that exists so a broken sync doesn't
    go unnoticed for weeks. Sent every time the job fails (no dedup/backoff)
    since this app runs one job of each kind per night, so worst case is one
    email a night until it's fixed.
    """
    subject = f"[Row Tracker] Scheduled job failed: {job_name}"
    body = (
        f"The nightly \"{job_name}\" job failed and needs attention.\n\n"
        f"Error: {error}\n\n"
        f"Check the container logs (docker logs row-tracker) for the full traceback.\n"
    )
    _send(subject, body)


def notify_journey_complete(route_key, journey):
    """Email that a virtual journey has been completed."""
    name = JOURNEY_NAMES.get(route_key, route_key)
    subject = f"[Row Tracker] Journey complete: {name}!"
    body = (
        f"You've finished the {name} virtual journey.\n\n"
        f"Started:   {journey.start_date}\n"
        f"Completed: {journey.completed_date}\n\n"
        f"🏆\n"
    )
    _send(subject, body)
