"""
Tests for scheduler.py's send_weekly_digest() gating — the only piece of
scheduler.py with real conditional logic worth a dedicated test; the rest
is thin cron-trigger wiring around already-tested engine functions.
"""

from scheduler import send_weekly_digest


def test_weekly_digest_skipped_when_not_enabled(full_app_ctx, sent_messages):
    full_app_ctx.config["NOTIFY_WEEKLY_DIGEST"] = False
    send_weekly_digest()
    assert sent_messages == []


def test_weekly_digest_sends_when_enabled(full_app_ctx, sent_messages):
    full_app_ctx.config["NOTIFY_WEEKLY_DIGEST"] = True
    send_weekly_digest()
    assert len(sent_messages) == 1
