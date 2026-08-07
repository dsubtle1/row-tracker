"""
Tests for notify.py — email notifications for badges, lifetime-metres
milestones, and virtual journey completions, plus the
check_journey_completions() integration point in blueprints/gamification.py.

Uses the sent_messages fixture (conftest.py) to inspect composed emails
via Flask-Mail's email_dispatched signal, without opening an SMTP
connection.
"""

from datetime import date, timedelta

from models import db, Badge, Journey
import notify


# --------------------------------------------------------------------------- #
#  lifetime_meters()                                                          #
# --------------------------------------------------------------------------- #

def test_lifetime_meters_empty(full_app_ctx):
    assert notify.lifetime_meters() == 0


def test_lifetime_meters_sums_rower_workouts(full_app_ctx, full_make_workout):
    full_make_workout(id=1, distance_meters=2000, time_seconds=480)
    full_make_workout(id=2, distance_meters=5000, time_seconds=1200)
    assert notify.lifetime_meters() == 7000


def test_lifetime_meters_excludes_non_rower(full_app_ctx, full_make_workout):
    full_make_workout(id=1, distance_meters=2000, time_seconds=480)
    full_make_workout(id=2, distance_meters=9000, time_seconds=1200, workout_type="bikeerg")
    assert notify.lifetime_meters() == 2000


# --------------------------------------------------------------------------- #
#  notify_badges()                                                            #
# --------------------------------------------------------------------------- #

def test_notify_badges_empty_list_is_noop(sent_messages):
    notify.notify_badges([])
    assert sent_messages == []


def test_notify_badges_unknown_key_is_noop(full_app_ctx, sent_messages):
    notify.notify_badges(["not-a-real-badge-key"])
    assert sent_messages == []


def test_notify_badges_sends_summary(full_app_ctx, sent_messages):
    # seed_badges() already populated the table at app creation.
    badge = Badge.query.filter_by(badge_key="first_100k").first()
    assert badge is not None

    notify.notify_badges(["first_100k"])

    assert len(sent_messages) == 1
    msg = sent_messages[0]
    assert "1 badge earned" in msg.subject
    assert badge.badge_name in msg.body
    assert badge.badge_desc in msg.body


def test_notify_badges_plural_subject_for_multiple(full_app_ctx, sent_messages):
    notify.notify_badges(["first_100k", "week_warrior"])

    assert len(sent_messages) == 1
    assert "2 badges earned" in sent_messages[0].subject


def test_notify_skips_when_no_recipient_configured(full_app, sent_messages):
    full_app.config["NOTIFY_EMAIL"] = ""
    with full_app.app_context():
        notify.notify_badges(["first_100k"])
    assert sent_messages == []


# --------------------------------------------------------------------------- #
#  check_and_notify_milestone()                                               #
# --------------------------------------------------------------------------- #

def test_milestone_not_crossed_is_noop(full_app_ctx, sent_messages):
    notify.check_and_notify_milestone(50_000, 99_000)
    assert sent_messages == []


def test_milestone_crossed_single(full_app_ctx, sent_messages):
    notify.check_and_notify_milestone(90_000, 120_000)

    assert len(sent_messages) == 1
    msg = sent_messages[0]
    assert "100k" in msg.subject
    assert "120,000" in msg.body


def test_milestone_boundary_counts_as_crossed(full_app_ctx, sent_messages):
    """before < m <= after — landing exactly on the threshold still counts."""
    notify.check_and_notify_milestone(99_999, 100_000)
    assert len(sent_messages) == 1


def test_milestone_crossing_from_exactly_on_threshold_does_not_recount(full_app_ctx, sent_messages):
    """Starting exactly at a milestone must not re-fire for that same one."""
    notify.check_and_notify_milestone(100_000, 100_500)
    assert sent_messages == []


def test_milestone_multiple_crossed_in_one_email(full_app_ctx, sent_messages):
    notify.check_and_notify_milestone(50_000, 600_000)

    assert len(sent_messages) == 1
    msg = sent_messages[0]
    assert "500k" in msg.subject  # headline is the highest one crossed
    assert "100k" in msg.body
    assert "250k" in msg.body
    assert "500k" in msg.body


# --------------------------------------------------------------------------- #
#  notify_journey_complete()                                                  #
# --------------------------------------------------------------------------- #

def test_notify_journey_complete(full_app_ctx, sent_messages):
    journey = Journey(
        route_key="rhine",
        start_date=date.today() - timedelta(days=60),
        completed=True,
        completed_date=date.today(),
    )
    db.session.add(journey)
    db.session.commit()

    notify.notify_journey_complete("rhine", journey)

    assert len(sent_messages) == 1
    msg = sent_messages[0]
    assert "Rhine River" in msg.subject
    assert str(journey.start_date) in msg.body
    assert str(journey.completed_date) in msg.body


def test_notify_journey_complete_unknown_route_key_uses_key_itself(full_app_ctx, sent_messages):
    journey = Journey(route_key="nile", start_date=date.today(), completed=True, completed_date=date.today())
    db.session.add(journey)
    db.session.commit()

    notify.notify_journey_complete("nile", journey)

    assert "nile" in sent_messages[0].subject


# --------------------------------------------------------------------------- #
#  check_journey_completions() — blueprints/gamification.py integration       #
# --------------------------------------------------------------------------- #

def test_check_journey_completions_fires_on_completion(full_app_ctx, full_make_workout, sent_messages):
    from blueprints.gamification import check_journey_completions, RHINE_TOTAL_M

    journey = Journey(route_key="rhine", start_date=date.today(), completed=False)
    db.session.add(journey)
    db.session.commit()

    full_make_workout(id=1, distance_meters=RHINE_TOTAL_M, time_seconds=200_000)

    check_journey_completions()

    assert len(sent_messages) == 1
    assert "Rhine River" in sent_messages[0].subject
    assert db.session.get(Journey, journey.id).completed is True


def test_check_journey_completions_no_email_when_not_yet_complete(full_app_ctx, full_make_workout, sent_messages):
    from blueprints.gamification import check_journey_completions

    journey = Journey(route_key="rhine", start_date=date.today(), completed=False)
    db.session.add(journey)
    db.session.commit()

    full_make_workout(id=1, distance_meters=1000, time_seconds=300)

    check_journey_completions()

    assert sent_messages == []
    assert db.session.get(Journey, journey.id).completed is False


def test_check_journey_completions_skips_already_completed(full_app_ctx, sent_messages):
    from blueprints.gamification import check_journey_completions

    journey = Journey(
        route_key="rhine",
        start_date=date.today() - timedelta(days=1),
        completed=True,
        completed_date=date.today(),
    )
    db.session.add(journey)
    db.session.commit()

    check_journey_completions()

    assert sent_messages == []


def test_check_journey_completions_no_active_journeys_is_noop(full_app_ctx, sent_messages):
    from blueprints.gamification import check_journey_completions
    check_journey_completions()
    assert sent_messages == []
