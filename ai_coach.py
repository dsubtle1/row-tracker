"""
ai_coach.py — Optional AI-generated coaching narrative for the Workout of the Day.

Feature-flagged via USE_AI_WOD. When enabled and ANTHROPIC_API_KEY is set,
replaces a WodSpec's static warm_up/cool_down/coaching_notes text with a
short narrative from Claude, tailored to the day's training context. The
structured workout itself (intervals, pace targets) stays rule-based —
only the coaching text is AI-generated.

Best-effort only: any failure (missing package, API error, malformed
response) falls back silently to the caller's existing static text. This
module never raises.
"""

from __future__ import annotations

import logging
from typing import Optional

from flask import current_app

logger = logging.getLogger(__name__)

MODEL = "claude-haiku-4-5"

SYSTEM_PROMPT = (
    "You are an experienced indoor rowing (Concept2 ergometer) coach writing "
    "the warm-up, cool-down, and coaching notes for a single workout. Use the "
    "session context you're given — training load, recent sessions, the "
    "athlete's own note if present — to make the notes specific to today, not "
    "generic. Keep the tone direct and practical, like a coach who rows "
    "themselves.\n\n"
    "Respond with exactly three sections separated by a line containing only "
    "---, in this order: warm-up, cool-down, coaching notes. Do not include "
    "headers, labels, or markdown — just the text for each section. Each "
    "section should be 1-3 sentences."
)


def is_available() -> bool:
    return bool(current_app.config.get("USE_AI_WOD")) and bool(
        current_app.config.get("ANTHROPIC_API_KEY")
    )


def _build_prompt(context: dict) -> str:
    lines = [
        f"Workout type: {context.get('wod_type')}",
        f"Title: {context.get('title')}",
        f"Target pace zone: {context.get('pace_zone')} ({context.get('target_pace_str')}/500m)",
        f"Total work: {context.get('total_work_meters')} meters",
    ]
    if context.get("intensity"):
        lines.append(f"Requested intensity: {context['intensity']}")
    if context.get("effort"):
        lines.append(f"Requested effort: {context['effort']}")
    if context.get("cawr") is not None:
        lines.append(f"Current training load (acute:chronic ratio): {context['cawr']}")
    if context.get("days_since_last_test") is not None:
        lines.append(f"Days since last test piece: {context['days_since_last_test']}")
    if context.get("recent_session_types"):
        lines.append(f"Session types completed in the last 7 days: {context['recent_session_types']}")
    if context.get("user_notes"):
        lines.append(f"Athlete's own note for today: {context['user_notes']}")
    return "\n".join(lines)


def generate_coaching_narrative(context: dict) -> Optional[dict]:
    """
    Ask Claude for a warm-up/cool-down/coaching-notes narrative for one WOD.

    `context` is a loosely-typed dict of whatever session info is available
    (wod_type, title, pace_zone, target_pace_str, total_work_meters, plus
    any optional keys handled in _build_prompt). Returns a dict with
    "warm_up", "cool_down", "coaching_notes" keys, or None if AI mode is
    off, unavailable, or the request fails for any reason.
    """
    if not is_available():
        return None

    try:
        import anthropic
    except ImportError:
        logger.warning("USE_AI_WOD is enabled but the 'anthropic' package is not installed.")
        return None

    try:
        client = anthropic.Anthropic(api_key=current_app.config["ANTHROPIC_API_KEY"])
        response = client.messages.create(
            model=MODEL,
            max_tokens=400,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": _build_prompt(context)}],
        )
        text = next((b.text for b in response.content if b.type == "text"), "")
        parts = [p.strip() for p in text.split("---")]
        if len(parts) != 3 or not all(parts):
            logger.warning("AI coaching narrative response was malformed: %r", text)
            return None
        return {"warm_up": parts[0], "cool_down": parts[1], "coaching_notes": parts[2]}
    except Exception as e:
        logger.error(f"AI coaching narrative generation failed: {e}")
        return None
