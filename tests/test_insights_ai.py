"""
Tests for insights_ai.py — the optional AI "coach's read" on the Insights page.

The Anthropic client is mocked throughout; no real API calls are made (so this
runs with no API key). Covers the availability gate, the happy path — including
that the briefing we send is grounded in the engine's real facts and that we
call the right model — and every failure mode (empty response, API error)
falling back to None rather than raising. generate_coach_read() must never raise.
"""

from unittest.mock import MagicMock

import insights_ai
from insights_engine import Insight


class _FakeTextBlock:
    def __init__(self, text):
        self.type = "text"
        self.text = text


class _FakeResponse:
    def __init__(self, text):
        self.content = [_FakeTextBlock(text)]


def _enable(app_ctx, key="sk-test-key"):
    app_ctx.config["USE_AI_INSIGHTS"] = True
    app_ctx.config["ANTHROPIC_API_KEY"] = key


def _sample_insights():
    return [
        Insight(
            key="year_over_year_volume", category="progress", confidence="strong",
            headline="You're ahead of last year's pace",
            detail="By this point in 2026 you've rowed 1,996 km, up 172% on the 733 km you'd logged by the same date in 2025.",
            facts={"this_year_meters": 1996000, "last_year_meters": 733000, "pct_change": 172.0, "ahead": True},
        ),
        Insight(
            key="consistency", category="habits", confidence="strong",
            headline="You keep a steady rhythm going",
            detail="94% of your rows follow within 48h of the last.",
            facts={"within_2_days_pct": 94.1},
        ),
    ]


# ---------------------------------------------------------------------------
# is_available()
# ---------------------------------------------------------------------------

def test_is_available_false_by_default(app_ctx):
    assert insights_ai.is_available() is False


def test_is_available_false_when_flag_off(app_ctx):
    app_ctx.config["USE_AI_INSIGHTS"] = False
    app_ctx.config["ANTHROPIC_API_KEY"] = "sk-test-key"
    assert insights_ai.is_available() is False


def test_is_available_false_when_key_missing(app_ctx):
    app_ctx.config["USE_AI_INSIGHTS"] = True
    app_ctx.config["ANTHROPIC_API_KEY"] = ""
    assert insights_ai.is_available() is False


def test_is_available_true_when_flag_on_and_key_set(app_ctx):
    _enable(app_ctx)
    assert insights_ai.is_available() is True


# ---------------------------------------------------------------------------
# generate_coach_read()
# ---------------------------------------------------------------------------

def test_none_when_unavailable(app_ctx):
    assert insights_ai.generate_coach_read(_sample_insights()) is None


def test_none_when_no_insights(app_ctx):
    _enable(app_ctx)
    assert insights_ai.generate_coach_read([]) is None


def test_success_grounds_in_real_facts(app_ctx, monkeypatch):
    _enable(app_ctx)
    narrative = "You're quietly in the best form of your year. Keep it going."

    fake_client = MagicMock()
    fake_client.messages.create.return_value = _FakeResponse(narrative)
    fake_anthropic_cls = MagicMock(return_value=fake_client)

    import anthropic
    monkeypatch.setattr(anthropic, "Anthropic", fake_anthropic_cls)

    result = insights_ai.generate_coach_read(
        _sample_insights(), {"sessions": 312, "meters": 2_710_000}
    )

    assert result == narrative
    fake_anthropic_cls.assert_called_once_with(api_key="sk-test-key")
    fake_client.messages.create.assert_called_once()

    _, kwargs = fake_client.messages.create.call_args
    assert kwargs["model"] == "claude-haiku-4-5"           # cheap Haiku, as documented
    # The system prompt must forbid inventing numbers.
    assert "Never invent" in kwargs["system"]
    # The briefing must carry the engine's real headlines AND raw facts, so the
    # model rephrases ground truth rather than making figures up.
    briefing = kwargs["messages"][0]["content"]
    assert "You're ahead of last year's pace" in briefing
    assert "1996000" in briefing                            # fact embedded verbatim
    assert "312 sessions" in briefing                       # overview embedded


def test_empty_response_returns_none(app_ctx, monkeypatch):
    _enable(app_ctx)
    fake_client = MagicMock()
    fake_client.messages.create.return_value = _FakeResponse("   ")

    import anthropic
    monkeypatch.setattr(anthropic, "Anthropic", MagicMock(return_value=fake_client))

    assert insights_ai.generate_coach_read(_sample_insights()) is None


def test_api_error_returns_none(app_ctx, monkeypatch):
    _enable(app_ctx)

    def _raise(*args, **kwargs):
        raise RuntimeError("network is down")

    import anthropic
    monkeypatch.setattr(anthropic, "Anthropic", _raise)

    assert insights_ai.generate_coach_read(_sample_insights()) is None
