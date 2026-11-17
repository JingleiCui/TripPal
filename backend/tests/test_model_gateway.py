"""可插拔模型网关单测：切换、凭证隔离、能力校验、缓存复用与状态脱敏。

全部离线；不发起任何真实模型请求。
"""

import pytest

from travel_agent.config import apply_model_profile, settings
from travel_agent.models import gateway, specs
from travel_agent.models.registry import ConfigurationError, chat_ready, resolve, status
from travel_agent.providers.base import ProviderError


@pytest.fixture(autouse=True)
def _clear_gateway():
    """每个用例前后清空实例缓存，避免测试间互相污染。"""
    gateway.clear_caches()
    yield
    gateway.clear_caches()


def test_openrouter_preset_uses_a_concrete_free_model():
    # openrouter/free 是自动路由器，每次请求可能落到不同模型，不能作为默认。
    spec = specs.provider_spec("openrouter")
    assert spec.protocol == specs.PROTOCOL_OPENAI
    assert spec.base_url == "https://openrouter.ai/api/v1"
    assert spec.default_model == "inclusionai/ling-3.2-flash:free"
    assert spec.structured_method == "json_schema"
    assert "vision" in spec.capabilities
    assert "openrouter" in specs.known_names()


def test_structured_slot_uses_its_own_model_instance(monkeypatch):
    """按用途分配必须真的生效：structured 槽位不能悄悄复用 chat 的 LLM 实例。"""
    monkeypatch.setattr(settings, "model_provider", "openrouter")
    monkeypatch.setattr(settings, "model_name", "inclusionai/ling-3.2-flash:free")
    monkeypatch.setattr(settings, "model_api_key", "sk-or-test")
    monkeypatch.setattr(settings, "model_enabled", True)
    monkeypatch.setattr(settings, "structured_output_method", "auto")
    monkeypatch.setattr(
        settings,
        "model_slots",
        {"structured": {"provider": "openrouter", "model": "baidu/ernie-5.5-flash-preview:free"}},
    )
    chat = resolve("chat")
    structured = resolve("structured")
    assert chat.model != structured.model
    assert structured.model == "baidu/ernie-5.5-flash-preview:free"
    assert gateway.chat_model(slot="structured") is not gateway.chat_model()
    assert gateway.chat_model(slot="structured") is gateway.chat_model(slot="structured")
    assert gateway.cache_stats()["chat_models"] == 2


def test_extra_body_reaches_chat_model_and_affects_cache(monkeypatch):
    """厂商请求体参数（如关闭 reasoning）必须真的进入 SDK 构造，且参与实例缓存键。"""
    captured = {}

    class FakeDriver:
        def __init__(self, **kwargs):
            captured.update(kwargs)

    monkeypatch.setattr(settings, "model_provider", "openrouter")
    monkeypatch.setattr(settings, "model_name", "inclusionai/ling-3.2-flash:free")
    monkeypatch.setattr(settings, "model_api_key", "sk-or-test")
    monkeypatch.setattr(settings, "model_enabled", True)
    monkeypatch.setattr(
        settings,
        "model_slots",
        {"chat": {"extra_body": {"reasoning": {"enabled": False}}}},
    )
    assert resolve("chat").extra_body == {"reasoning": {"enabled": False}}
    gateway.chat_model(drivers={"openai": FakeDriver})
    assert captured["extra_body"] == {"reasoning": {"enabled": False}}
    assert resolve("chat").public()["extra_body_keys"] == ["reasoning"]

    monkeypatch.setattr(settings, "model_slots", {"chat": {}})
    gateway.chat_model(drivers={"openai": FakeDriver})
    assert gateway.cache_stats()["chat_models"] == 2


def test_extra_body_merged_into_http_slots(monkeypatch):
    """vision / asr 走裸 HTTP，extra_body 必须合并进请求体。"""
    class FakeResponse:
        status_code = 200

        def json(self):
            return {"choices": [{"message": {"content": "{}"}}]}

    class FakeClient:
        def __init__(self):
            self.sent = None

        def post(self, url, headers=None, json=None, timeout=None):
            self.sent = json
            return FakeResponse()

    fake = FakeClient()
    monkeypatch.setattr(gateway, "client_for", lambda spec: fake)
    monkeypatch.setattr(settings, "model_provider", "openrouter")
    monkeypatch.setattr(settings, "model_api_key", "sk-or-test")
    monkeypatch.setattr(settings, "model_enabled", True)
    monkeypatch.setattr(
        settings,
        "model_slots",
        {
            "vision": {
                "provider": "openrouter",
                "model": "nvidia/nemotron-3.5-super-vl:free",
                "use_main_key": True,
                "enabled": True,
                "extra_body": {"reasoning": {"enabled": False}},
            }
        },
    )
    content = gateway.post_chat(
        "vision", {"model": "x", "messages": []},
        label="视觉识别", failure_code="vision_failed", unavailable_code="vision_unavailable",
    )
    assert content == "{}"
    assert fake.sent["reasoning"] == {"enabled": False}
    assert fake.sent["model"] == "x"


def test_model_profile_can_carry_slot_assignment():
    """profile 自带 model_slots，切到别的 profile 时不污染顶层配置。"""
    raw = {
        "active_model_profile": "openrouter_free",
        "model_profiles": {
            "openrouter_free": {
                "model_provider": "openrouter",
                "model_name": "inclusionai/ling-3.2-flash:free",
                "model_api_key": "sk-or-test",
                "model_slots": {"vision": {"model": "nvidia/nemotron-3.5-super-vl:free"}},
            },
            "local": {"model_provider": "ollama", "model_name": "qwen3.5:9b"},
        },
    }
    applied = apply_model_profile(raw)
    assert applied["model_slots"]["vision"]["model"] == "nvidia/nemotron-3.5-super-vl:free"
    local = apply_model_profile({**raw, "active_model_profile": "local"})
    assert local.get("model_slots", {}) == {}


def test_custom_provider_registers_without_code_changes(monkeypatch):
    monkeypatch.setattr(
        settings,
        "model_providers",
        {"my_gateway": {"protocol": "openai", "base_url": "https://llm.internal/v1",
                        "default_model": "internal-chat", "structured_method": "function_calling"}},
    )
    assert "my_gateway" in specs.known_names(settings.model_providers)
    spec = specs.provider_spec("my_gateway", settings.model_providers)
    assert spec.base_url == "https://llm.internal/v1"
    monkeypatch.setattr(settings, "model_provider", "my_gateway")
    monkeypatch.setattr(settings, "model_api_key", "secret")
    resolved = resolve("chat")
    assert resolved.provider == "my_gateway"
    assert resolved.base_url == "https://llm.internal/v1"
    assert resolved.structured_method == "function_calling"


def test_unknown_provider_fails_loudly(monkeypatch):
    monkeypatch.setattr(settings, "model_provider", "not-registered")
    with pytest.raises(ConfigurationError, match="未注册"):
        resolve("chat")
    assert chat_ready() is False


def test_bad_custom_provider_fields_are_rejected():
    with pytest.raises(ValueError, match="不支持的字段"):
        specs.build_spec("broken", {"protocol": "openai", "timeout": 10})


def test_legacy_flat_config_still_behaves_the_same(monkeypatch):
    """旧配置（model_provider=openai + 自定义 base_url）必须原样可用。"""
    monkeypatch.setattr(settings, "model_provider", "openai")
    monkeypatch.setattr(settings, "model_base_url", "https://example.com/v1")
    monkeypatch.setattr(settings, "model_api_key", "legacy-key")
    monkeypatch.setattr(settings, "model_name", "legacy-model")
    monkeypatch.setattr(settings, "structured_output_method", "auto")
    resolved = resolve("chat")
    assert resolved.base_url == "https://example.com/v1"
    assert resolved.protocol == specs.PROTOCOL_OPENAI
    assert resolved.structured_method == "function_calling"
    assert resolved.ready is True


def test_profile_switch_to_openrouter_resolves_everything(monkeypatch):
    """切换机制：apply_model_profile 覆盖后 registry 自动指向 OpenRouter。"""
    raw = {
        "model_api_key": "old-dashscope-key",
        "active_model_profile": "free",
        "model_profiles": {
            "free": {
                "model_provider": "openrouter",
                "model_name": "google/gemma-4-31b-it:free",
                "model_api_key": "sk-or-test",
                "model_enabled": True,
                "structured_output_method": "json_schema",
            }
        },
    }
    applied = apply_model_profile(raw)
    assert applied["model_provider"] == "openrouter"
    monkeypatch.setattr(settings, "model_provider", applied["model_provider"])
    monkeypatch.setattr(settings, "model_name", applied["model_name"])
    monkeypatch.setattr(settings, "model_api_key", applied["model_api_key"])
    monkeypatch.setattr(settings, "structured_output_method", applied["structured_output_method"])
    monkeypatch.setattr(settings, "model_enabled", True)
    resolved = resolve("chat")
    assert resolved.provider == "openrouter"
    assert resolved.base_url == "https://openrouter.ai/api/v1"  # 不再错误沿用 dashscope
    assert resolved.model == "google/gemma-4-31b-it:free"
    assert resolve("structured").structured_method == "json_schema"


def test_structured_output_method_global_override_wins(monkeypatch):
    monkeypatch.setattr(settings, "model_provider", "openrouter")
    monkeypatch.setattr(settings, "structured_output_method", "function_calling")
    assert resolve("structured").structured_method == "function_calling"


def test_local_ollama_keeps_json_schema_and_no_key_required(monkeypatch):
    monkeypatch.setattr(settings, "model_provider", "openai")
    monkeypatch.setattr(settings, "model_base_url", "http://127.0.0.1:11434/v1")
    monkeypatch.setattr(settings, "model_api_key", "")
    monkeypatch.setattr(settings, "model_enabled", True)
    monkeypatch.setattr(settings, "structured_output_method", "auto")
    resolved = resolve("chat")
    assert resolved.protocol == specs.PROTOCOL_OLLAMA
    assert resolved.base_url == "http://127.0.0.1:11434"
    assert resolve("structured").structured_method == "json_schema"
    assert resolved.ready is True  # 本地模型不需要 API key


def test_model_slots_mix_providers_per_capability(monkeypatch):
    """同一份配置里：对话用 OpenRouter，视觉用另一个供应商。"""
    monkeypatch.setattr(settings, "model_provider", "openrouter")
    monkeypatch.setattr(settings, "model_api_key", "sk-or-main")
    monkeypatch.setattr(settings, "model_enabled", True)
    monkeypatch.setattr(
        settings,
        "model_slots",
        {"vision": {"provider": "dashscope", "model": "qwen-vl-max-latest", "api_key": "ds-vision-key"}},
    )
    monkeypatch.setattr(settings, "vision_enabled", True)
    assert resolve("chat").base_url == "https://openrouter.ai/api/v1"
    vision = resolve("vision")
    assert vision.provider == "dashscope"
    assert vision.api_key == "ds-vision-key"
    assert vision.model == "qwen-vl-max-latest"


def test_credentials_never_cross_hosts(monkeypatch):
    """OpenRouter 的对话 Key 不能被悄悄发到百炼语音域名。"""
    monkeypatch.setattr(settings, "model_provider", "openrouter")
    monkeypatch.setattr(settings, "model_api_key", "sk-or-main")
    monkeypatch.setattr(settings, "voice_api_key", "")
    monkeypatch.setattr(settings, "voice_enabled", True)
    monkeypatch.delenv("DASHSCOPE_API_KEY", raising=False)
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    assert resolve("asr").api_key == ""
    assert resolve("asr").ready is False


def test_use_main_key_requires_same_host(monkeypatch):
    monkeypatch.setattr(settings, "model_provider", "openrouter")
    monkeypatch.setattr(settings, "model_api_key", "sk-or-main")
    monkeypatch.setattr(settings, "vision_api_key", "")
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.setattr(
        settings,
        "model_slots",
        {"vision": {"provider": "openrouter", "model": "nvidia/nemotron-3.5-super-vl:free",
                    "use_main_key": True}},
    )
    assert resolve("vision").api_key == "sk-or-main"


def test_unsupported_capability_is_rejected(monkeypatch):
    monkeypatch.setattr(settings, "model_slots", {"vision": {"provider": "deepseek"}})
    with pytest.raises(ConfigurationError, match="不支持"):
        resolve("vision")


def test_status_never_exposes_credentials(monkeypatch):
    monkeypatch.setattr(settings, "model_api_key", "highly-secret-value")
    monkeypatch.setattr(settings, "vision_api_key", "another-secret-value")
    payload = str(status())
    assert "highly-secret-value" not in payload
    assert "another-secret-value" not in payload
    assert "key_present" in payload
    assert "chat" in status()["slots"]


def test_chat_model_is_cached_and_invalidates_on_config_change(monkeypatch):
    monkeypatch.setattr(settings, "model_provider", "openai")
    monkeypatch.setattr(settings, "model_base_url", "https://example.com/v1")
    monkeypatch.setattr(settings, "model_api_key", "test-key")
    monkeypatch.setattr(settings, "model_name", "test-model")
    first = gateway.chat_model()
    assert gateway.chat_model() is first
    monkeypatch.setattr(settings, "model_name", "another-model")
    assert gateway.chat_model() is not first
    assert gateway.cache_stats()["chat_models"] == 2


def test_http_client_pool_is_reused_and_monkeypatch_safe(monkeypatch):
    monkeypatch.setattr(settings, "vision_enabled", True)
    spec = resolve("vision")
    first = gateway.client_for(spec)
    assert gateway.client_for(spec) is first

    class FakeClient:
        def __init__(self, *args, **kwargs):
            pass

    monkeypatch.setattr(gateway.httpx, "Client", FakeClient)
    assert isinstance(gateway.client_for(spec), FakeClient)


def test_chat_content_shared_parser():
    class Response:
        @staticmethod
        def json():
            return {"choices": [{"message": {"content": "就绪"}}]}

    assert gateway.chat_content(Response()) == "就绪"

    class Broken:
        @staticmethod
        def json():
            return {"unexpected": []}

    with pytest.raises(ProviderError) as exc:
        gateway.chat_content(Broken())
    assert exc.value.code == "schema"


def test_http_error_mapping_and_messages():
    error = gateway._http_error(429, "视觉识别", "vision_failed")
    assert error.code == "vision_failed"
    assert "拒绝" in str(error) and "429" in str(error) and "额度" in str(error)


def test_models_endpoint_reports_slots_without_secrets(client, monkeypatch):
    monkeypatch.setattr(settings, "model_api_key", "endpoint-secret")
    body = client.get("/api/v1/models").json()
    assert "slots" in body and "chat" in body["slots"]
    assert "endpoint-secret" not in str(body)
    assert "cache" in body


def test_local_slots_need_no_credentials():
    assert resolve("embedding").protocol == specs.PROTOCOL_LOCAL
    assert resolve("embedding").ready is True
    assert resolve("rerank").api_key == ""
