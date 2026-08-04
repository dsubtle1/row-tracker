"""
Row Tracker — Flask application factory.
Single container, single port (7376), three Blueprint modules.
"""

import os
from flask import Flask
from flask_mail import Mail
from flask_wtf.csrf import CSRFProtect
from models import db

mail = Mail()
csrf = CSRFProtect()


def create_app():
    app = Flask(__name__)

    # ------------------------------------------------------------------ config
    app.config["SQLALCHEMY_DATABASE_URI"] = (
        f"sqlite:///{os.path.join(app.root_path, 'data', 'row_tracker.db')}"
    )
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "dev-secret-change-in-prod")

    # -------------------------------------------------------------------- mail
    app.config["MAIL_SERVER"]         = "smtp.gmail.com"
    app.config["MAIL_PORT"]           = 587
    app.config["MAIL_USE_TLS"]        = True
    app.config["MAIL_USERNAME"]       = os.environ.get("MAIL_USERNAME", "")
    app.config["MAIL_PASSWORD"]       = os.environ.get("MAIL_PASSWORD", "")
    app.config["MAIL_DEFAULT_SENDER"] = os.environ.get("MAIL_USERNAME", "")

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

    return app


if __name__ == "__main__":
    application = create_app()
    application.run(host="0.0.0.0", port=7376, debug=False)
