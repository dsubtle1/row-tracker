"""
Notifications for badges, lifetime-metres milestones, and virtual journey
completions — fanned out to whichever channels are configured: email
(Flask-Mail, sent to NOTIFY_EMAIL, defaulting to MAIL_USERNAME), ntfy.sh,
a Discord webhook, and/or a generic JSON webhook.

Every channel is independently best-effort: a failure on one (a flaky SMTP
server, an unreachable webhook) is logged and swallowed, never raised, so
it can't break a sync and can't stop the other configured channels from
still delivering the same notification.
"""

import logging
import requests
from flask import current_app
from flask_mail import Message
from sqlalchemy import func

from models import db, Workout, Badge

logger = logging.getLogger(__name__)
WEBHOOK_TIMEOUT_SECONDS = 5

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


def _send_email(subject, body, recipient):
    from app import mail

    try:
        msg = Message(subject=subject, recipients=[recipient], body=body)
        mail.send(msg)
        logger.info(f"Notification sent via email: {subject!r}")
    except Exception as e:
        logger.error(f"Notification email failed ({subject!r}): {e}")


def _send_ntfy(subject, body, topic):
    try:
        requests.post(
            f"https://ntfy.sh/{topic}",
            data=body.encode("utf-8"),
            headers={"Title": subject},
            timeout=WEBHOOK_TIMEOUT_SECONDS,
        ).raise_for_status()
        logger.info(f"Notification sent via ntfy: {subject!r}")
    except Exception as e:
        logger.error(f"Notification via ntfy failed ({subject!r}): {e}")


def _send_discord(subject, body, webhook_url):
    try:
        requests.post(
            webhook_url,
            json={"content": f"**{subject}**\n{body}"},
            timeout=WEBHOOK_TIMEOUT_SECONDS,
        ).raise_for_status()
        logger.info(f"Notification sent via Discord: {subject!r}")
    except Exception as e:
        logger.error(f"Notification via Discord failed ({subject!r}): {e}")


def _send_webhook(subject, body, webhook_url):
    try:
        requests.post(
            webhook_url,
            json={"subject": subject, "body": body},
            timeout=WEBHOOK_TIMEOUT_SECONDS,
        ).raise_for_status()
        logger.info(f"Notification sent via webhook: {subject!r}")
    except Exception as e:
        logger.error(f"Notification via webhook failed ({subject!r}): {e}")


def _send(subject, body):
    """
    Fan out to every configured channel. Each channel is independently
    best-effort (see module docstring) — one failing or unconfigured
    channel never prevents another from firing.
    """
    sent_any = False

    recipient = current_app.config.get("NOTIFY_EMAIL", "")
    if recipient:
        _send_email(subject, body, recipient)
        sent_any = True

    ntfy_topic = current_app.config.get("NOTIFY_NTFY_TOPIC", "")
    if ntfy_topic:
        _send_ntfy(subject, body, ntfy_topic)
        sent_any = True

    discord_url = current_app.config.get("NOTIFY_DISCORD_WEBHOOK_URL", "")
    if discord_url:
        _send_discord(subject, body, discord_url)
        sent_any = True

    webhook_url = current_app.config.get("NOTIFY_WEBHOOK_URL", "")
    if webhook_url:
        _send_webhook(subject, body, webhook_url)
        sent_any = True

    if not sent_any:
        logger.warning(f"Notification skipped (no channel configured): {subject!r}")


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


def notify_weekly_digest():
    """
    Sunday-evening summary: metres and sessions in the last 7 days, any PB
    achieved, and the soonest-projected still-locked lifetime badge.

    Distinct from every other notify_* function here — those fire only on
    an achievement (a badge, a milestone, a journey finish); this one fires
    every week on schedule regardless of whether anything happened, so a
    quiet week is visible too, not just a loud one.
    """
    from datetime import date, timedelta
    from models import PersonalBest

    today = date.today()
    week_start = today - timedelta(days=6)

    workouts = Workout.query.filter(
        Workout.workout_date >= week_start,
        Workout.workout_date <= today,
        Workout.workout_type == "rower",
    ).all()
    metres = sum(w.total_distance_meters for w in workouts)
    count = len(workouts)

    pbs = PersonalBest.query.filter(
        PersonalBest.achieved_date >= week_start,
        PersonalBest.achieved_date <= today,
    ).all()

    lines = [f"This week: {metres:,}m across {count} session{'s' if count != 1 else ''}."]

    if pbs:
        lines.append("")
        lines.append("New PBs this week:")
        lines.extend(f"  🏆 {pb.category} — {pb.value_formatted}" for pb in pbs)

    from badge_engine import get_badge_progress
    next_badge = None   # (eta_iso, badge_name) — soonest of any still-locked lifetime badge
    for badge in Badge.query.filter(Badge.earned_date.is_(None)).all():
        progress = get_badge_progress(badge.badge_key)
        if progress and progress.get("eta"):
            if next_badge is None or progress["eta"] < next_badge[0]:
                next_badge = (progress["eta"], badge.badge_name)
    if next_badge:
        lines.append("")
        lines.append(f"Next badge: {next_badge[1]} — projected {next_badge[0]}")

    subject = f"[Row Tracker] Weekly digest — {metres:,}m this week"
    body = "\n".join(lines) + "\n"
    _send(subject, body)
