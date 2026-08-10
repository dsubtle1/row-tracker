"""
insights_ai.py — Optional AI "coach's read" for the Insights page.

Feature-flagged via USE_AI_INSIGHTS. When enabled and ANTHROPIC_API_KEY is
set, takes the *already-computed* deterministic insights and writes a short,
warm first-person paragraph that ties them together — the synthesis a set of
independent rule cards can't do on its own.

Hard rule: the model only ever rephrases and connects the facts it's handed.
Every number in the briefing comes from insights_engine; the model is told, in
the system prompt, never to invent or recompute one. This mirrors ai_coach.py:
the structured data stays rule-based, only the narrative is AI-generated.

Best-effort only: any failure (flag off, missing package, API error, empty
response) returns None and the page simply shows its cards without a coach's
read. This module never raises.
"""

from __future__ import annotations

import logging
from typing import Optional

from flask import current_app

logger = logging.getLogger(__name__)

MODEL = "claude-haiku-4-5"

SYSTEM_PROMPT = (
    "You are the athlete's personal indoor-rowing (Concept2 erg) coach, writing a "
    "short 'here's what I'm noticing' note for the top of their stats page. You are "
    "given a briefing of patterns already found in their data, each with exact "
    "numbers.\n\n"
    "Rules:\n"
    "- Use ONLY the numbers in the briefing. Never invent, round differently, or "
    "compute a new figure. If a number isn't in the briefing, don't state it.\n"
    "- Write 2 short paragraphs, first person, warm and direct — a coach who rows "
    "themselves, not a report.\n"
    "- Tie the patterns together into one story rather than listing them. Lead with "
    "what's going well; if there's a watch-out (e.g. a long current streak), land it "
    "gently at the end.\n"
    "- No headers, no markdown, no bullet points — just the two paragraphs."
)


def is_available() -> bool:
    return bool(current_app.config.get("USE_AI_INSIGHTS")) and bool(
        current_app.config.get("ANTHROPIC_API_KEY")
    )


def _build_briefing(insights, overview) -> str:
    """Turn the structured insights into a compact, numbers-only briefing.
    Deliberately feeds facts (not the pre-written prose) so the model does the
    phrasing itself off the same ground truth."""
    lines = []
    if overview:
        lines.append(
            f"Athlete history: {overview.get('sessions')} sessions, "
            f"{round((overview.get('meters') or 0) / 1_000_000, 2)}M meters total."
        )
    lines.append("Patterns found (with exact figures — use these verbatim):")
    for ins in insights:
        strength = "strong" if ins.is_strong else "tentative"
        lines.append(f"- ({strength}) {ins.headline}. {ins.detail} Facts: {ins.facts}")
    return "\n".join(lines)


def generate_coach_read(insights, overview=None) -> Optional[str]:
    """
    Ask Claude for a short first-person synthesis of the insights.

    `insights` is the list[Insight] from insights_engine.generate_insights();
    `overview` is the optional dataset_overview() dict. Returns the narrative
    string, or None if AI mode is off, unavailable, there's nothing to
    synthesize, or the request fails for any reason.
    """
    if not is_available():
        return None
    if not insights:
        return None

    try:
        import anthropic
    except ImportError:
        logger.warning("USE_AI_INSIGHTS is enabled but the 'anthropic' package is not installed.")
        return None

    try:
        client = anthropic.Anthropic(api_key=current_app.config["ANTHROPIC_API_KEY"])
        response = client.messages.create(
            model=MODEL,
            max_tokens=350,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": _build_briefing(insights, overview)}],
        )
        text = next((b.text for b in response.content if b.type == "text"), "").strip()
        return text or None
    except Exception as e:
        logger.error(f"AI coach's read generation failed: {e}")
        return None
