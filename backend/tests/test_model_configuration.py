"""Model routing must keep local requests local and preserve explicit reasoning settings."""

from unittest.mock import patch

from travel_agent.agent.harness import model
from travel_agent.config import settings


def test_local_model_uses_ollama_endpoint_and_explicit_reasoning(monkeypatch):
    monkeypatch.setattr(settings, "model_provider", "openai")
    monkeypatch.setattr(settings, "model_name", "qwen3.5:9b")
    monkeypatch.setattr(settings, "model_api_key", "ollama")
    monkeypatch.setattr(settings, "model_base_url", "http://127.0.0.1:11434/v1")
    monkeypatch.setattr(settings, "model_reasoning_effort", "none")
    with patch("langchain_ollama.ChatOllama") as client:
        model()
    assert client.call_args.kwargs["base_url"] == "http://127.0.0.1:11434"
    assert client.call_args.kwargs["model"] == "qwen3.5:9b"
    assert client.call_args.kwargs["reasoning"] is False


def test_default_reasoning_is_not_forced_on_other_providers(monkeypatch):
    monkeypatch.setattr(settings, "model_provider", "openai")
    monkeypatch.setattr(settings, "model_reasoning_effort", None)
    monkeypatch.setattr(settings, "model_base_url", "https://example.com/v1")
    with patch("travel_agent.agent.harness.ChatOpenAI") as client:
        model()
    assert "reasoning_effort" not in client.call_args.kwargs


def test_profile_switch_cannot_reuse_previous_key():
    from travel_agent.config import apply_model_profile

    result = apply_model_profile(
        {
            "model_api_key": "old-secret",
            "gemini_base_url": "https://old.invalid",
            "active_model_profile": "new",
            "model_profiles": {"new": {"model_provider": "gemini", "model_name": "test-model"}},
        }
    )
    assert result["model_api_key"] == "" and result["gemini_base_url"] == ""
    assert result["model_provider"] == "gemini"


def test_named_profile_and_legacy_compatibility():
    from travel_agent.config import apply_model_profile

    legacy = {"model_name": "existing", "model_api_key": "private"}
    assert apply_model_profile(legacy) == legacy
    assert (
        apply_model_profile(
            {
                "active_model_profile": "local",
                "model_profiles": {"local": {"model_provider": "ollama", "model_name": "local-model"}},
            }
        )["model_name"]
        == "local-model"
    )


def test_unknown_profile_fails_instead_of_switching_silently():
    import pytest
    from travel_agent.config import apply_model_profile

    with pytest.raises(ValueError):
        apply_model_profile({"active_model_profile": "missing"})
