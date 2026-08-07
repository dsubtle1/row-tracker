"""
Tests for ai_coach.py — the optional AI-generated WOD coaching narrative.

The Anthropic client is mocked throughout; no real API calls are made.
Covers the availability gate, the happy path, and every failure mode
(malformed response, API error) always falling back to None rather than
raising — generate_coaching_narrative() must never raise.
"""

from unittest.mock import MagicMock

import ai_coach


class _FakeTextBlock:
    def __init__(self, text):
        self.type = "text"
        self.text = text


class _FakeResponse:
    def __init__(self, text):
        self.content = [_FakeTextBlock(text)]


def _enable_ai(app_ctx, key="sk-test-key"):
    app_ctx.config["USE_AI_WOD"] = True
    app_ctx.config["ANTHROPIC_API_KEY"] = key


# ---------------------------------------------------------------------------
# is_available()
# ---------------------------------------------------------------------------

def test_is_available_false_by_default(app_ctx):
    assert ai_coach.is_available() is False


def test_is_available_false_when_flag_off(app_ctx):
    app_ctx.config["USE_AI_WOD"] = False
    app_ctx.config["ANTHROPIC_API_KEY"] = "sk-test-key"
    assert ai_coach.is_available() is False


def test_is_available_false_when_key_missing(app_ctx):
    app_ctx.config["USE_AI_WOD"] = True
    app_ctx.config["ANTHROPIC_API_KEY"] = ""
    assert ai_coach.is_available() is False


def test_is_available_true_when_flag_on_and_key_set(app_ctx):
    _enable_ai(app_ctx)
    assert ai_coach.is_available() is True


# ---------------------------------------------------------------------------
# generate_coaching_narrative()
# ---------------------------------------------------------------------------

def test_generate_coaching_narrative_none_when_unavailable(app_ctx):
    assert ai_coach.generate_coaching_narrative({}) is None


def test_generate_coaching_narrative_success(app_ctx, monkeypatch):
    _enable_ai(app_ctx)

    fake_response = _FakeResponse(
        "Warm up easy for ten minutes.\n---\nCool down gently.\n---\nStay smooth on the drive."
    )
    fake_client = MagicMock()
    fake_client.messages.create.return_value = fake_response
    fake_anthropic_cls = MagicMock(return_value=fake_client)

    import anthropic
    monkeypatch.setattr(anthropic, "Anthropic", fake_anthropic_cls)

    result = ai_coach.generate_coaching_narrative({
        "wod_type": "steady_state",
        "title": "50 Minute Steady State",
        "pace_zone": "UT2",
        "target_pace_str": "2:10",
        "total_work_meters": 10000,
        "cawr": 1.05,
        "recent_session_types": {"steady_state": 2, "interval": 1},
    })

    assert result == {
        "warm_up": "Warm up easy for ten minutes.",
        "cool_down": "Cool down gently.",
        "coaching_notes": "Stay smooth on the drive.",
    }
    fake_anthropic_cls.assert_called_once_with(api_key="sk-test-key")
    fake_client.messages.create.assert_called_once()
    _, kwargs = fake_client.messages.create.call_args
    assert kwargs["model"] == "claude-haiku-4-5"


def test_generate_coaching_narrative_malformed_response_returns_none(app_ctx, monkeypatch):
    _enable_ai(app_ctx)

    fake_client = MagicMock()
    fake_client.messages.create.return_value = _FakeResponse("no separators here at all")

    import anthropic
    monkeypatch.setattr(anthropic, "Anthropic", MagicMock(return_value=fake_client))

    assert ai_coach.generate_coaching_narrative({}) is None


def test_generate_coaching_narrative_empty_section_returns_none(app_ctx, monkeypatch):
    _enable_ai(app_ctx)

    fake_client = MagicMock()
    fake_client.messages.create.return_value = _FakeResponse("warm up\n---\n\n---\ncoaching")

    import anthropic
    monkeypatch.setattr(anthropic, "Anthropic", MagicMock(return_value=fake_client))

    assert ai_coach.generate_coaching_narrative({}) is None


def test_generate_coaching_narrative_api_error_returns_none(app_ctx, monkeypatch):
    _enable_ai(app_ctx)

    def _raise(*args, **kwargs):
        raise RuntimeError("network is down")

    import anthropic
    monkeypatch.setattr(anthropic, "Anthropic", _raise)

    assert ai_coach.generate_coaching_narrative({}) is None
