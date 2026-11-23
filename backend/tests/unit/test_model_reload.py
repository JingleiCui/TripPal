"""Exercise actual config file edits and rollback without any network requests."""

import json

import pytest
from travel_agent import config
from travel_agent.models import gateway
from travel_agent.models.registry import resolve, status


@pytest.fixture
def model_file(tmp_path, monkeypatch):
    original = config.settings.__dict__.copy()
    monkeypatch.setattr(config, "ROOT", tmp_path)
    monkeypatch.setattr(config, "_model_file_seen", config._model_file_signature())
    monkeypatch.setattr(config, "_model_generation", 0)
    monkeypatch.setattr(config, "_model_reload_error", None)
    monkeypatch.setattr(config, "_restart_required", [])
    monkeypatch.setattr(config.settings, "model_auto_reload", True)
    # Respect test environment DB/index settings; do not touch any real config or services.
    raw = config.settings.model_dump()
    raw.update(active_model_profile="", model_profiles={}, model_slots={}, model_providers={})
    path = tmp_path / "config.local.json"

    def write(**updates):
        raw.update(updates)
        path.write_text(json.dumps(raw), encoding="utf-8")
        return path

    yield write
    config.settings.__dict__ = original
    gateway.clear_caches()


def test_file_switch_local_cloud_local_reuses_existing_entry(model_file):
    captured = []

    class Driver:
        def __init__(self, **kwargs):
            captured.append(kwargs)

    model_file(model_provider="ollama", model_name="local-one", model_base_url="http://localhost:11434")
    first = gateway.chat_model(drivers={"ollama": Driver})
    model_file(model_provider="deepseek", model_name="cloud-two", model_api_key="cloud-secret")
    second = gateway.chat_model(drivers={"openai": Driver})
    assert first is not second
    assert captured[-1]["base_url"] == "https://api.deepseek.com/v1"
    model_file(model_provider="ollama", model_name="local-three", model_api_key="")
    gateway.chat_model(drivers={"ollama": Driver})
    assert captured[-1]["model"] == "local-three"
    assert resolve("chat").ready
    assert config.model_reload_status()["generation"] == 3


def test_invalid_file_keeps_last_good_settings_and_redacts_error(model_file):
    path = model_file(model_provider="ollama", model_name="good")
    assert resolve("chat").model == "good"
    path.write_text('{"model_api_key": "secret-in-broken-json",', encoding="utf-8")
    assert resolve("chat").model == "good"
    assert status()["reload"]["error"]
    assert "secret-in-broken-json" not in str(status())
    generation = config.model_reload_status()["generation"]
    resolve("chat")  # Do not repeatedly parse the same bad file.
    assert config.model_reload_status()["generation"] == generation
    model_file(model_name="fixed")
    assert resolve("chat").model == "fixed"
    assert status()["reload"]["error"] is None


@pytest.mark.parametrize(
    "updates",
    [
        {"model_provider": "missing-provider"},
        {"model_slots": {"typo": {}}},
        {"model_slots": {"structured": {"timeout": -1}}},
        {"model_slots": {"structured": {"structured_method": "invalid"}}},
        {"model_slots": {"embedding": {"model": "cannot-silently-ignore"}}},
        {"model_output_tokens": 0},
        {"embedding_model": "different-vector-space"},
    ],
)
def test_invalid_switch_is_atomic(model_file, updates):
    before = config.settings.model_dump()
    model_file(**updates)
    with pytest.raises(ValueError, match="保留原配置"):
        config.reload_model_settings()
    assert config.settings.model_dump() == before


def test_non_model_fields_are_not_applied_live(model_file):
    original_port = config.settings.port
    model_file(port=original_port + 1, model_name="new-live-model")
    config.reload_model_settings()
    assert config.settings.port == original_port
    assert config.settings.model_name == "new-live-model"
    assert "port" in config.model_reload_status()["restart_required"]


def test_auto_reload_can_be_disabled_and_explicit_reload_still_works(model_file):
    config.settings.model_auto_reload = False
    before = config.settings.model_name
    model_file(model_auto_reload=False, model_name="manual-switch")
    assert resolve("chat").model == before
    config.reload_model_settings()
    assert resolve("chat").model == "manual-switch"


def test_environment_wins_over_file(model_file, monkeypatch):
    monkeypatch.setenv("TRAVEL_MODEL_NAME", "env-model")
    model_file(model_name="file-model")
    assert resolve("chat").model == "env-model"


def test_profiles_preserve_legacy_shared_slots_and_budgets():
    raw = {
        "active_model_profile": "local",
        "model_api_key": "old-secret",
        "model_output_tokens": 1,
        "model_slots": {"vision": {"enabled": False}},
        "model_profiles": {"local": {"model_provider": "ollama", "model_name": "new"}},
    }
    applied = config.apply_model_profile(raw)
    assert applied["model_slots"] == {"vision": {"enabled": False}}
    assert applied["model_api_key"] == ""
    assert applied["model_output_tokens"] == 1
    assert resolve("chat", config.Settings(**applied)).base_url == "http://127.0.0.1:11434"


def test_structured_provider_uses_own_endpoint_key_and_method():
    candidate = config.Settings(
        model_provider="openai",
        model_name="local-chat",
        model_base_url="http://localhost:11434/v1",
        model_api_key="private-local-key",
        model_slots={"structured": {"provider": "deepseek", "api_key": "cloud-key"}},
    )
    spec = resolve("structured", candidate)
    assert spec.model == "deepseek-chat"
    assert spec.base_url == "https://api.deepseek.com/v1"
    assert spec.api_key == "cloud-key"
    assert spec.structured_method == "json_schema"


def test_different_structured_host_cannot_implicitly_receive_chat_key(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    candidate = config.Settings(
        model_api_key="private-chat-key",
        model_base_url="https://chat.example/v1",
        model_slots={"structured": {"base_url": "https://other.example/v1"}},
    )
    assert resolve("structured", candidate).api_key == ""


def test_local_vision_uses_ollama_compatible_endpoint_without_key():
    candidate = config.Settings(
        model_slots={"vision": {"provider": "ollama", "model": "local-vl", "enabled": True}}
    )
    spec = resolve("vision", candidate)
    assert spec.base_url == "http://127.0.0.1:11434/v1"
    assert spec.protocol == "openai"
    assert spec.ready
    assert not spec.requires_key


def test_http_spec_stays_pinned_when_settings_change(monkeypatch):
    first = resolve(
        "vision",
        config.Settings(model_slots={"vision": {"provider": "ollama", "model": "local-vl", "enabled": True}}),
    )
    sent = []

    class Response:
        status_code = 200

        def json(self):
            return {"choices": [{"message": {"content": "ok"}}]}

    class Client:
        def post(self, url, headers, json, timeout):
            sent.append((url, headers, json))
            return Response()

    monkeypatch.setattr(gateway, "client_for", lambda spec: Client())
    monkeypatch.setattr(
        config.settings,
        "model_slots",
        {"vision": {"provider": "openrouter", "model": "other-model", "api_key": "other-key"}},
    )
    assert (
        gateway.post_chat(
            "vision",
            {"model": first.model},
            spec=first,
            label="vision",
            failure_code="failed",
            unavailable_code="unavailable",
        )
        == "ok"
    )
    assert sent[0][0] == "http://127.0.0.1:11434/v1/chat/completions"
    assert "Authorization" not in sent[0][1]
    assert sent[0][2]["model"] == "local-vl"


def test_structured_retry_pins_configuration(model_file, monkeypatch):
    from langchain_core.messages import AIMessage
    from travel_agent.agent import harness, structured
    from travel_agent.schemas import PlanSelection

    model_file(model_provider="ollama", model_name="first-model")
    captured = []

    class Runnable:
        def with_structured_output(self, schema, method, include_raw):
            return self

        def invoke(self, messages):
            if len(captured) == 1:
                model_file(model_name="next-model")
                return {"raw": AIMessage(content="bad"), "parsed": None}
            return {"raw": AIMessage(content="{}"), "parsed": PlanSelection(days=[["A"]], rationale="ok")}

    def model(slot, configuration):
        captured.append(configuration.model_name)
        return Runnable()

    monkeypatch.setattr(harness, "model", model)
    assert structured.generate(PlanSelection, [], "test").days == [["A"]]
    assert captured == ["first-model", "first-model"]
    assert resolve("chat").model == "next-model"


def test_local_retrieval_entry_points_use_gateway(monkeypatch):
    from travel_agent import knowledge

    calls = []
    sentinel = object()

    def loader(slot):
        calls.append(slot)
        return sentinel

    monkeypatch.setattr(gateway, "local_model", loader)
    assert knowledge.embedder() is sentinel
    assert knowledge.reranker() is sentinel
    assert calls == ["embedding", "rerank"]


def test_tts_can_be_enabled_independently(monkeypatch):
    from travel_agent import voice

    monkeypatch.setattr(voice, "slot_ready", lambda slot: slot == "tts")
    voice.enabled("tts")
    from travel_agent.providers.base import ProviderError

    with pytest.raises(ProviderError):
        voice.enabled("asr")
