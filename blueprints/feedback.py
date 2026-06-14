"""
Row Tracker — Feedback blueprint.
Handles the feedback modal form submission and sends email via Flask-Mail.
"""

from flask import Blueprint, request, jsonify, current_app
from flask_mail import Message
from app import mail

feedback_bp = Blueprint("feedback", __name__, url_prefix="/feedback")

FEEDBACK_RECIPIENT = "rowtracker@pm.me"


@feedback_bp.route("/submit", methods=["POST"])
def submit():
    category = request.form.get("category", "General").strip()
    name     = request.form.get("name", "").strip() or "Anonymous"
    message  = request.form.get("message", "").strip()
    page     = request.form.get("page", "Unknown").strip()

    if not message:
        return jsonify({"ok": False, "error": "Message is required."}), 400

    subject = f"[Row Tracker Feedback] {category} — from: {name}"

    body = f"""Row Tracker Alpha Feedback
==========================
Category : {category}
From     : {name}
Page     : {page}

Message
-------
{message}
"""

    try:
        msg = Message(
            subject=subject,
            recipients=[FEEDBACK_RECIPIENT],
            body=body,
        )
        mail.send(msg)
        return jsonify({"ok": True})
    except Exception as e:
        current_app.logger.error(f"Feedback email failed: {e}")
        return jsonify({"ok": False, "error": "Failed to send. Please try again."}), 500
