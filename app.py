"""
Row Tracker — Flask application factory.
Single container, single port (7376), three Blueprint modules.
"""

import os
from flask import Flask
from models import db


def create_app():
    app = Flask(__name__)

    # ------------------------------------------------------------------ config
    app.config["SQLALCHEMY_DATABASE_URI"] = (
        f"sqlite:///{os.path.join(app.root_path, 'data', 'row_tracker.db')}"
    )
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "dev-secret-change-in-prod")

    # Feature flags (read from .env via Docker)
    app.config["USE_AI_WOD"] = os.environ.get("USE_AI_WOD", "false").lower() == "true"

    # C2 API credentials (populated once API key is approved)
    app.config["C2_CLIENT_ID"]     = os.environ.get("C2_CLIENT_ID", "")
    app.config["C2_CLIENT_SECRET"] = os.environ.get("C2_CLIENT_SECRET", "")
    app.config["C2_REFRESH_TOKEN"] = os.environ.get("C2_REFRESH_TOKEN", "")

    # ---------------------------------------------------------- init extensions
    db.init_app(app)

    with app.app_context():
        db.create_all()

    # --------------------------------------------------------------- blueprints
    from blueprints.tracker import tracker_bp
    from blueprints.wod import wod_bp
    from blueprints.gamification import gamification_bp

    app.register_blueprint(tracker_bp)
    app.register_blueprint(wod_bp)
    app.register_blueprint(gamification_bp)

    return app


if __name__ == "__main__":
    application = create_app()
    application.run(host="0.0.0.0", port=7376, debug=False)
