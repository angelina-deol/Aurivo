"""
Tests for backend/services/llm_explanation.py.

Covers the template fallback (no API key), a mocked real API call, and the
mocked-API-failure fallback path.
"""
from unittest.mock import MagicMock, patch

from backend.services.llm_explanation import ExplanationInput, generate_explanation


def _make_input(**overrides) -> ExplanationInput:
    defaults = dict(
        prediction="ai_generated",
        confidence=0.94,
        fraud_score=94.0,
        duration_seconds=3.2,
        sample_rate=16000,
        channels=1,
    )
    defaults.update(overrides)
    return ExplanationInput(**defaults)


def test_template_fallback_used_when_no_api_key(monkeypatch):
    monkeypatch.setattr("backend.services.llm_explanation.settings.ANTHROPIC_API_KEY", None)
    data = _make_input()

    result = generate_explanation(data)

    assert "AI-generated" in result
    assert "94%" in result
    assert "Template-based summary" in result


def test_template_fallback_includes_top_attention_region(monkeypatch):
    monkeypatch.setattr("backend.services.llm_explanation.settings.ANTHROPIC_API_KEY", None)
    data = _make_input(
        attention_regions=[
            {"start": 0.5, "end": 1.2, "salience": 0.8},
            {"start": 2.0, "end": 2.8, "salience": 0.3},
        ]
    )

    result = generate_explanation(data)

    assert "0.5s-1.2s" in result  # the higher-salience region, not the lower one


def test_real_api_call_path_is_used_when_key_configured(monkeypatch):
    monkeypatch.setattr("backend.services.llm_explanation.settings.ANTHROPIC_API_KEY", "fake-key")
    data = _make_input()

    fake_text_block = MagicMock()
    fake_text_block.type = "text"
    fake_text_block.text = "This recording shows strong signs of AI generation."
    fake_response = MagicMock()
    fake_response.content = [fake_text_block]

    with patch("anthropic.Anthropic") as MockAnthropic:
        MockAnthropic.return_value.messages.create.return_value = fake_response
        result = generate_explanation(data)

    assert result == "This recording shows strong signs of AI generation."


def test_api_failure_falls_back_to_template(monkeypatch):
    monkeypatch.setattr("backend.services.llm_explanation.settings.ANTHROPIC_API_KEY", "fake-key")
    data = _make_input()

    with patch("anthropic.Anthropic") as MockAnthropic:
        MockAnthropic.return_value.messages.create.side_effect = RuntimeError("API down")
        result = generate_explanation(data)

    assert "Template-based summary" in result


def test_prompt_forbids_fabricating_technical_detail(monkeypatch):
    """The prompt sent to the model must explicitly forbid inventing
    specifics beyond the given data — this is the actual honesty
    safeguard, so it's worth a direct regression test rather than trusting
    it stays in place by convention."""
    from backend.services.llm_explanation import _build_prompt

    prompt = _build_prompt(_make_input())
    assert "do not invent" in prompt.lower() or "not invent" in prompt.lower()
