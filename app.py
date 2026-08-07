"""
Row Tracker — Flask application factory.
Single container, single port (7376), three Blueprint modules.
"""

import os
import secrets
import logging
from flask import Flask, send_from_directory
from flask_mail import Mail
from flask_wtf.csrf import CSRFProtect
from models import db

# Without a handler, module-level loggers (scheduler.py, badge_engine.py,
# pb_engine.py, c2_api.py) fall back to Python's "last resort" handler,
# which only prints WARNING and above — so a nightly sync/backup success,
# or the specific error behind a failure, would never reach `docker compose
# logs`. This makes the scheduler's nightly jobs actually observable.
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)

mail = Mail()
csrf = CSRFProtect()


def create_app():
    app = Flask(__name__)

    # ------------------------------------------------------------------ config
    # TESTING must be set before mail.init_app() below — Flask-Mail defaults
    # MAIL_SUPPRESS_SEND to app.testing, which is how the test suite hits
    # /feedback/submit without opening a real SMTP connection.
    app.config["TESTING"] = os.environ.get("TESTING", "").lower() == "true"

    # DATABASE_PATH lets the test suite point this at a throwaway file
    # instead of the real database — unset in Docker/production, so the
    # default path there is unchanged.
    db_path = os.environ.get("DATABASE_PATH") or os.path.join(app.root_path, "data", "row_tracker.db")
    app.config["SQLALCHEMY_DATABASE_URI"] = f"sqlite:///{db_path}"
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

    # SECRET_KEY signs session cookies and (as of CSRFProtect, below) CSRF
    # tokens. A fixed fallback checked into a public repo would be a known
    # secret to anyone reading the source, defeating both. Fall back to a
    # random one-time key instead — the app still works if .env is
    # misconfigured, just with sessions/CSRF tokens that reset on restart.
    secret_key = os.environ.get("SECRET_KEY")
    if not secret_key:
        secret_key = secrets.token_hex(32)
        app.logger.warning(
            "SECRET_KEY not set — using a random one-time key for this run. "
            "Sessions and CSRF tokens will invalidate on every restart. "
            "Set SECRET_KEY in .env for a stable, secure deployment."
        )
    app.config["SECRET_KEY"] = secret_key

    # -------------------------------------------------------------------- mail
    app.config["MAIL_SERVER"]         = "smtp.gmail.com"
    app.config["MAIL_PORT"]           = 587
    app.config["MAIL_USE_TLS"]        = True
    app.config["MAIL_USERNAME"]       = os.environ.get("MAIL_USERNAME", "")
    app.config["MAIL_PASSWORD"]       = os.environ.get("MAIL_PASSWORD", "")
    app.config["MAIL_DEFAULT_SENDER"] = os.environ.get("MAIL_USERNAME", "")

    # Where badge/milestone/journey-completion notifications get sent —
    # defaults to MAIL_USERNAME (the athlete's own inbox) rather than the
    # feedback form's rowtracker@pm.me, which is for incoming support mail.
    app.config["NOTIFY_EMAIL"] = os.environ.get("NOTIFY_EMAIL") or os.environ.get("MAIL_USERNAME", "")

    # Feature flags (read from .env via Docker)
    app.config["USE_AI_WOD"] = os.environ.get("USE_AI_WOD", "false").lower() == "true"

    # C2 API credentials (populated once API key is approved)
    app.config["C2_CLIENT_ID"]     = os.environ.get("C2_CLIENT_ID", "")
    app.config["C2_CLIENT_SECRET"] = os.environ.get("C2_CLIENT_SECRET", "")
    app.config["C2_REFRESH_TOKEN"] = os.environ.get("C2_REFRESH_TOKEN", "")

    # ---------------------------------------------------------- init extensions
    db.init_app(app)
    mail.init_app(app)
    csrf.init_app(app)

    with app.app_context():
        db.create_all()

        # Badge rows must exist before evaluate_badges() has anything to
        # check against — seed_badges() never ran anywhere in the app
        # before, so the badges table was always empty. Both are
        # idempotent and cheap, safe to run on every startup.
        from badge_engine import seed_badges, evaluate_badges
        seed_badges()
        evaluate_badges()

    # --------------------------------------------------------------- blueprints
    from blueprints.tracker import tracker_bp, hr_zone_class, hr_zone_name
    from blueprints.wod import wod_bp
    from blueprints.gamification import gamification_bp
    from blueprints.feedback import feedback_bp

    app.register_blueprint(tracker_bp)

    # Jinja2 filters for heart rate zone display in workout_detail.html
    app.jinja_env.filters['hr_zone_class'] = hr_zone_class
    app.jinja_env.filters['hr_zone_name']  = hr_zone_name
    app.register_blueprint(wod_bp)
    app.register_blueprint(gamification_bp)
    app.register_blueprint(feedback_bp)

    # Served from the root path (not /static/js/sw.js) so its default scope
    # covers the whole app — a service worker can only control pages under
    # the path it's served from unless the server opts in via a response
    # header, which send_from_directory doesn't set.
    @app.route("/sw.js")
    def service_worker():
        response = send_from_directory(os.path.join(app.static_folder, "js"), "sw.js")
        response.headers["Service-Worker-Allowed"] = "/"
        response.headers["Cache-Control"] = "no-cache"
        return response

    # ---------------------------------------------------------------- scheduler
    # Skipped under TESTING — a real BackgroundScheduler thread has no
    # business running against a throwaway test database, and every test
    # that builds its own app via the factory would otherwise leak one.
    if not app.testing:
        from scheduler import init_scheduler
        init_scheduler(app)

    return app


if __name__ == "__main__":
    application = create_app()
    application.run(host="0.0.0.0", port=7376, debug=False)
