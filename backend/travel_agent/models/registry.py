"""按「能力槽位」解析模型供应商、凭证与连接参数。

配置优先级（从低到高）：
  内置 ProviderSpec < config.local.json 平铺字段 < model_profiles（active_model_profile）
  < model_slots[slot] 覆盖 < TRAVEL_* 环境变量（由 config.load_settings 完成）

切换只需改 ``active_model_profile`` 或 ``model_slots``，调用点无需改动。
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from urllib.parse import urlparse

from . import specs

SLOTS = ("chat", "structured", "vision", "asr", "tts", "embedding", "rerank")
API_SLOTS = ("chat", "structured", "vision", "asr", "tts")
LEGACY_PROVIDERS = frozenset({"openai", "ollama", "gemini"})
SLOT_FIELDS = frozenset(
    {
        "provider",
        "model",
        "api_key",
        "base_url",
        "enabled",
        "use_main_key",
        "extra_headers",
        "extra_body",
        "structured_method",
        "timeout",
    }
)


@dataclass(frozen=True)
class ResolvedSpec:
    """某槽位最终生效的全部连接信息；凭证只在此对象内传递，不写日志。"""

    slot: str
    provider: str
    protocol: str
    base_url: str
    api_key: str
    model: str
    timeout: int
    enabled: bool
    structured_method: str
    extra_headers: dict
    extra_body: dict = field(default_factory=dict)
    chat_path: str = ""
    requires_key: bool = True
    source: str = ""

    @property
    def key_present(self):
        return bool(self.api_key)

    @property
    def ready(self):
        return bool(self.enabled and (self.api_key or not self.requires_key))

    @property
    def fingerprint(self):
        """用于缓存实例；包含凭证哈希而非明文，key 变化时自动失效。"""
        return (
            self.slot,
            self.provider,
            self.protocol,
            self.base_url,
            self.model,
            self.timeout,
            hash(self.api_key),
            self.structured_method,
            tuple(sorted(self.extra_headers.items())),
            repr(sorted(self.extra_body.items())),
        )

    def public(self):
        """可安全写入 /health 与日志的视图：不含任何凭证。"""
        return {
            "slot": self.slot,
            "provider": self.provider,
            "protocol": self.protocol,
            "model": self.model,
            "base_url": self.base_url,
            "enabled": self.enabled,
            "key_present": self.key_present,
            "extra_body_keys": sorted(self.extra_body),
            "status": (
                "ready" if self.ready else "disabled" if not self.enabled else "needs_key"
            ),
            "source": self.source,
        }


class ConfigurationError(ValueError):
    """配置写错时显式失败，而不是静默回落到别的供应商。"""


def _slot_override(slot, settings):
    raw = (settings.model_slots or {}).get(slot, {})
    unknown = set(raw) - SLOT_FIELDS
    if unknown:
        raise ConfigurationError(f"model_slots.{slot} 含不支持的字段：{', '.join(sorted(unknown))}")
    for name in {"enabled", "use_main_key"} & raw.keys():
        if not isinstance(raw[name], bool):
            raise ConfigurationError(f"model_slots.{slot}.{name} 必须为布尔值")
    for name in {"provider", "model", "base_url", "api_key", "structured_method"} & raw.keys():
        if not isinstance(raw[name], str):
            raise ConfigurationError(f"model_slots.{slot}.{name} 必须为字符串")
    for name in {"extra_headers", "extra_body"} & raw.keys():
        if not isinstance(raw[name], dict):
            raise ConfigurationError(f"model_slots.{slot}.{name} 必须为对象")
    return dict(raw)


def _is_local_ollama(provider, base_url):
    if provider == "ollama":
        return True
    if provider != "openai":
        return False
    parsed = urlparse(base_url)
    return parsed.hostname in {"127.0.0.1", "localhost", "::1"} and parsed.port == 11434


def _same_host(left, right):
    try:
        return urlparse(left).hostname and urlparse(left).hostname == urlparse(right).hostname
    except ValueError:
        return False


def _chat_base_url(settings):
    """轻量取当前对话槽位的 base_url（不递归调用 resolve），供同源凭证复用判定。"""
    override = (settings.model_slots or {}).get("chat", {})
    if override.get("base_url"):
        return override["base_url"]
    name = override.get("provider") or settings.model_provider
    if name in LEGACY_PROVIDERS and name == settings.model_provider:
        return settings.model_base_url or specs.provider_spec(name, settings.model_providers).base_url
    return specs.provider_spec(name, settings.model_providers).base_url


def _provider_name(slot, override, default, settings, setting_field=None):
    field = setting_field or f"{slot}_provider"
    name = override.get("provider") or getattr(settings, field, "") or default
    if name not in specs.known_names(settings.model_providers):
        raise ConfigurationError(
            f"模型供应商 {name!r} 未注册；可用：{', '.join(sorted(specs.known_names(settings.model_providers)))}"
        )
    return name


def _key(slot, override, spec, settings, *, explicit="", use_main=False, same_host_required=False):
    """凭证解析：显式 key > 槽位 key > 主对话 key（仅同源/显式授权）> 供应商环境变量。"""
    if override.get("api_key"):
        return override["api_key"], f"model_slots.{slot}.api_key"
    if explicit:
        return explicit, f"{slot}_api_key"
    if use_main or override.get("use_main_key"):
        if same_host_required and not _same_host(_chat_base_url(settings), override.get("base_url") or spec.base_url):
            # 避免把 OpenRouter / Gemini 的对话 Key 误发到百炼语音等第三方域名。
            return "", "main_key_rejected_cross_host"
        if settings.model_api_key:
            return settings.model_api_key, "model_api_key(shared)"
    if spec.key_env and os.getenv(spec.key_env):
        return os.environ[spec.key_env], f"env:{spec.key_env}"
    return "", "missing"


def _structured_method(spec, override, settings, protocol):
    if protocol == specs.PROTOCOL_OLLAMA:
        return "json_schema"  # 保持既有本地 Ollama 行为
    # 槽位级覆盖优先于全局：按用途给 structured 换模型/协议时，方法必须跟着槽位走。
    if override.get("structured_method"):
        return override["structured_method"]
    if settings.structured_output_method != "auto":
        return settings.structured_output_method
    if spec.structured_method != "auto":
        return spec.structured_method
    return "json_schema" if spec.protocol == specs.PROTOCOL_GEMINI else "function_calling"


def _validate_capability(slot, spec):
    if slot in {"embedding", "rerank"}:
        return
    if slot not in spec.capabilities:
        raise ConfigurationError(
            f"供应商 {spec.name!r} 不支持 {slot} 能力；请改用 model_slots.{slot}.provider 指定其他供应商"
        )


def resolve(slot, configuration=None) -> ResolvedSpec:
    """返回指定槽位最终生效的配置。不发起任何网络请求。"""
    from ..config import model_settings_snapshot

    settings = configuration if configuration is not None else model_settings_snapshot()
    if slot not in SLOTS:
        raise ConfigurationError(f"未知能力槽位：{slot}")
    override = _slot_override(slot, settings)
    if "timeout" in override and (not isinstance(override["timeout"], (int, float)) or override["timeout"] <= 0):
        raise ConfigurationError("模型超时必须为正数")
    if override.get("structured_method", "auto") not in {"auto", "json_schema", "function_calling"}:
        raise ConfigurationError("不支持的结构化输出模式")

    if slot in {"embedding", "rerank"}:
        if override:
            raise ConfigurationError("embedding/rerank 暂不支持槽位覆盖；请修改本地模型配置并重启")
        spec = specs.provider_spec("local", settings.model_providers)
        return ResolvedSpec(
            slot=slot,
            provider="local",
            protocol=specs.PROTOCOL_LOCAL,
            base_url="",
            api_key="",
            model=(settings.embedding_model if slot == "embedding" else settings.reranker_model),
            timeout=0,
            enabled=True if slot == "embedding" else settings.reranker_enabled,
            structured_method="auto",
            extra_headers={},
            extra_body={},
            chat_path="",
            requires_key=False,
            source="local sentence-transformers",
        )

    if slot in {"chat", "structured"}:
        name = _provider_name(slot, override, settings.model_provider, settings)
        spec = specs.provider_spec(name, settings.model_providers)
        _validate_capability(slot, spec)
        legacy = name in LEGACY_PROVIDERS
        base_url = override.get("base_url") or (
            (settings.model_base_url or spec.base_url) if legacy and name == settings.model_provider else spec.base_url
        )
        protocol = spec.protocol
        if protocol not in specs.LANGCHAIN_PROTOCOLS:
            raise ConfigurationError(f"对话槽位不支持协议 {protocol}")
        if _is_local_ollama(name, base_url):
            protocol = specs.PROTOCOL_OLLAMA
            base_url = base_url.rstrip("/").removesuffix("/v1")
        if protocol == specs.PROTOCOL_GEMINI:
            base_url = override.get("base_url") or settings.gemini_base_url
        key, source = _key(slot, {**override, "base_url": base_url}, spec, settings, use_main=name == settings.model_provider, same_host_required=protocol != specs.PROTOCOL_GEMINI)
        model = override.get("model") or (settings.model_name if name == settings.model_provider else spec.default_model)
        enabled = bool(override.get("enabled", settings.model_enabled))
        return ResolvedSpec(
            slot=slot,
            provider=name,
            protocol=protocol,
            base_url=base_url,
            api_key=key,
            model=model,
            timeout=int(override.get("timeout", settings.model_timeout)),
            enabled=enabled,
            structured_method=_structured_method(spec, override, settings, protocol),
            extra_headers={**spec.extra_headers, **override.get("extra_headers", {})},
            extra_body={**spec.extra_body, **override.get("extra_body", {})},
            chat_path=spec.chat_path,
            requires_key=False if protocol == specs.PROTOCOL_OLLAMA else spec.requires_key,
            source=source or f"preset:{name}",
        )

    if slot == "vision":
        default = settings.model_provider if settings.model_provider not in LEGACY_PROVIDERS else "dashscope"
        if "vision" not in specs.provider_spec(default, settings.model_providers).capabilities:
            default = "dashscope"
        name = _provider_name(slot, override, default, settings)
        spec = specs.provider_spec(name, settings.model_providers)
        _validate_capability(slot, spec)
        if spec.protocol not in specs.HTTP_PROTOCOLS | {specs.PROTOCOL_OLLAMA}:
            raise ConfigurationError(f"视觉槽位需要 OpenAI-compatible HTTP 供应商，{name!r} 是 {spec.protocol}")
        key, source = _key(
            slot,
            override,
            spec,
            settings,
            explicit=settings.vision_api_key,
            same_host_required=True,
        )
        base_url = override.get("base_url") or (
            settings.vision_api_base_url if name == "dashscope" else spec.base_url
        )
        if spec.protocol == specs.PROTOCOL_OLLAMA:
            base_url = base_url.rstrip("/").removesuffix("/v1") + "/v1"
        return ResolvedSpec(
            slot=slot,
            provider=name,
            protocol=specs.PROTOCOL_OPENAI,
            base_url=base_url,
            api_key=key,
            model=override.get("model") or settings.vision_model,
            timeout=int(override.get("timeout", settings.vision_timeout)),
            enabled=bool(override.get("enabled", settings.vision_enabled)),
            structured_method="auto",
            extra_headers={**spec.extra_headers, **override.get("extra_headers", {})},
            extra_body={**spec.extra_body, **override.get("extra_body", {})},
            chat_path=spec.chat_path,
            requires_key=spec.requires_key,
            source=source,
        )

    # asr / tts：默认走百炼原生，凭证与对话 Key 严格隔离（同源才允许复用）。
    name = _provider_name(slot, override, "dashscope_native", settings, setting_field="voice_provider")
    spec = specs.provider_spec(name, settings.model_providers)
    _validate_capability(slot, spec)
    if spec.protocol not in specs.HTTP_PROTOCOLS | {specs.PROTOCOL_LOCAL}:
        raise ConfigurationError(f"语音槽位需要 HTTP 供应商，{name!r} 是 {spec.protocol}")
    key, source = _key(
        slot,
        override,
        spec,
        settings,
        explicit=settings.voice_api_key,
        use_main=settings.model_provider == "openai",  # 兼容既有 voice_key() 回退语义
        same_host_required=True,
    )
    return ResolvedSpec(
        slot=slot,
        provider=name,
        protocol=spec.protocol,
        base_url=override.get("base_url") or (
            settings.voice_api_base_url if name == "dashscope_native" else spec.base_url
        ),
        api_key=key,
        model=override.get("model") or (settings.asr_model if slot == "asr" else settings.tts_model),
        timeout=int(override.get("timeout", 60)),
        enabled=bool(override.get("enabled", settings.voice_enabled)),
        structured_method="auto",
        extra_headers={**spec.extra_headers, **override.get("extra_headers", {})},
        chat_path=spec.chat_path,
        requires_key=spec.requires_key,
        source=source,
    )


def chat_ready():
    """对话/结构化槽位是否具备真实调用条件（替代散落的 `model_enabled and model_api_key`）。"""
    try:
        return resolve("chat").ready
    except ConfigurationError:
        return False


def ready(slot):
    try:
        return resolve(slot).ready
    except ConfigurationError:
        return False


def status():
    """health 视图：逐槽位状态，绝不返回凭证明文。"""
    from ..config import model_settings_snapshot, model_reload_status

    snapshot = model_settings_snapshot()
    slots = {}
    for slot in SLOTS:
        try:
            slots[slot] = resolve(slot, snapshot).public()
        except ConfigurationError as exc:
            slots[slot] = {"slot": slot, "status": "misconfigured", "error": str(exc)}
    return {
        "active_model_profile": snapshot.active_model_profile,
        "reload": model_reload_status(),
        "available_providers": sorted(specs.known_names(snapshot.model_providers)),
        "slots": slots,
    }
