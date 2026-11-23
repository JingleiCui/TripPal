"""常用配置直接在这里修改；私密配置写入根目录 config.local.json。"""

from pathlib import Path
import json
import os
from threading import RLock
from pydantic import BaseModel, Field
from .models.specs import known_names

ROOT = Path(__file__).resolve().parents[2]


MODEL_PROFILE_FIELDS = {
    "model_provider",
    "model_name",
    "model_base_url",
    "gemini_base_url",
    "model_api_key",
    "model_enabled",
    "model_timeout",
    "model_reasoning_effort",
    "model_context_tokens",
    "model_output_tokens",
    "structured_output_method",
    # profile 可自带按能力槽位的模型分配；切换 profile 时随 profile 一起生效/失效，
    # 避免顶层 model_slots 污染其它 profile（例如本地 Ollama）。
    "model_slots",
    "vision_provider", "vision_enabled", "vision_model", "vision_api_key",
    "vision_api_base_url", "vision_timeout",
    "voice_provider", "voice_enabled", "voice_api_key", "voice_api_base_url",
    "asr_model", "tts_model",
}


class Settings(BaseModel):
    model_auto_reload: bool = True  # 下一次模型解析检查配置文件；仅热更新模型相关字段
    active_model_profile: str = ""  # 空值兼容原配置；填写 model_profiles 中的配置名即可切换
    model_profiles: dict[str, dict] = Field(default_factory=dict)
    structured_output_method: str = "auto"  # auto / json_schema / function_calling

    # —— 可插拔模型网关 ——
    # model_providers：自定义供应商，或覆盖内置预设的 base_url / model / headers。
    # model_slots：按能力槽位（chat/structured/vision/asr/tts）单独指定供应商、模型与凭证。
    # 两者都为空时完全保持旧行为（model_provider / model_base_url / model_api_key）。
    model_providers: dict[str, dict] = Field(default_factory=dict)
    model_slots: dict[str, dict] = Field(default_factory=dict)
    vision_provider: str = ""  # 可选：视觉槽位供应商；留空时跟随对话供应商
    voice_provider: str = ""  # 可选：语音槽位供应商；默认 dashscope_native

    host: str = "127.0.0.1"
    port: int = 8808
    database_url: str = (
        "mysql+pymysql://travel:travel_local_only@127.0.0.1:13316/travel_agent?charset=utf8mb4"
    )
    checkpoint_url: str = "mysql://travel:travel_local_only@127.0.0.1:13316/travel_agent"
    redis_url: str = "redis://127.0.0.1:16389/0"
    broker_url: str = "redis://127.0.0.1:16389/1"
    elastic_url: str = "http://127.0.0.1:19220"
    elastic_index: str = "travel-agent-chunks-v1"
    model_name: str = "qwen-plus"
    model_provider: str = "openai"  # openai: 百炼/Ollama/兼容网关；gemini: Google 官方 Gemini
    gemini_base_url: str = ""  # 官方地址不必填写；原生 Gemini 网关可选
    model_base_url: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    model_api_key: str = ""
    model_enabled: bool = False
    model_timeout: int = 60
    model_context_tokens: int = 8192
    model_output_tokens: int = 4096
    model_reasoning_effort: str | None = None  # Ollama 可设 none 关闭思考，避免耗尽输出预算
    model_context_chars: int = 16000
    model_call_limit: int = 12
    tool_call_limit: int = 24
    task_budget_seconds: int = 600
    amap_key: str = ""
    amap_js_key: str = ""
    amap_security_code: str = ""
    meituan_enabled: bool = False
    meituan_cli: str = str(ROOT / "integrations/node_modules/.bin/mttravel")
    meituan_timeout: int = 180
    embedding_model: str = "BAAI/bge-small-zh-v1.5"
    embedding_local_only: bool = True
    reranker_enabled: bool = False
    reranker_model: str = "BAAI/bge-reranker-base"
    voice_enabled: bool = False
    voice_api_base_url: str = "https://dashscope.aliyuncs.com"
    voice_api_key: str = ""  # Gemini 对话 Key 不会自动发送到百炼语音服务
    asr_model: str = "qwen3-asr-flash"
    tts_model: str = "qwen3-tts-flash"
    # 截图识别：独立于对话模型的视觉通道，避免把对话 Key 发往未授权服务。
    vision_enabled: bool = False
    vision_api_base_url: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    vision_api_key: str = ""
    vision_model: str = "qwen-vl-max-latest"
    vision_timeout: int = 60
    vision_fixture_enabled: bool = False  # 仅合成流程演示，结果必须显式标注 synthetic
    cookie_secure: bool = False
    session_days: int = 7
    share_days: int = 7
    max_upload_bytes: int = 5 * 1024 * 1024
    data_dir: str = str(ROOT / "data")
    fixture_enabled: bool = True
    semantic_cache_enabled: bool = True
    semantic_cache_index: str = "travel-agent-research-cache-v1"
    semantic_cache_similarity: float = 0.94
    semantic_cache_seconds: int = 3600
    jwt_secret: str = ""  # 本机空值时生成 data/jwt.key；服务器应独立配置
    email_required: bool = False  # 本机兼容已有无邮箱账户；公网部署设 true
    smtp_host: str = "127.0.0.1"
    smtp_port: int = 11026
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_starttls: bool = False
    smtp_allow_external: bool = False
    mail_from: str = "travel_agent <no-reply@travel.local>"
    public_base_url: str = "http://127.0.0.1:8808"
    posthog_key: str = ""
    posthog_host: str = "https://us.i.posthog.com"
    # 能力门控：会话可见工具按启用的能力收敛。空列表表示放开全部（向后兼容）。
    capabilities: list[str] = Field(default_factory=list)
    # 受治理 MCP server
    mcp_enabled: bool = False
    mcp_transport: str = "stdio"  # stdio / http
    mcp_scopes: list[str] = Field(default_factory=lambda: ["travel_agent:read", "travel_agent:tools"])
    mcp_bind: str = "127.0.0.1"
    mcp_port: int = 8811
    # 逐变更卡片确认 + 撤销窗口
    pending_change_ttl_minutes: int = 15
    # 附件驱动工具触发
    note_public_dns_fallback: bool = True  # Resolve proxy synthetic DNS via verified public DoH, still pin public IPs
    # 本人小红书会话：默认关闭；显式开启后只读取用户主动提交的、本人有权查看的笔记。
    note_login_enabled: bool = False
    note_cookie_file: str = ""
    note_cookie_hosts: list[str] = Field(
        default_factory=lambda: [
            "xiaohongshu.com", "www.xiaohongshu.com", "xhslink.com", "www.xhslink.com"
        ]
    )
    # 登录弹层可关闭时，用浏览器兜底读取；Cookie 仍是可选加速项，不是必需。
    note_browser_fallback: bool = True
    note_browser_reader: str = str(ROOT / "frontend" / "xhs-note-reader.mjs")
    note_browser_timeout: int = 45
    # 实测无头 Chrome 会触发小红书风控；有头浏览器能关闭弹层并读取正文，故默认关闭无头模式。
    note_browser_headless: bool = False
    # 首次登录后持久化浏览器 profile；后续解析直接复用，不要求每次重新登录。
    note_browser_user_data_dir: str = str(Path.home() / ".config/tripal/xhs-browser-profile")
    attachment_parsers_enabled: bool = True
    allowed_attachment_extensions: list[str] = Field(
        default_factory=lambda: [
            ".txt", ".md", ".pdf", ".docx", ".gpx", ".json",
            ".png", ".jpg", ".jpeg", ".webp",
        ]
    )


def apply_model_profile(values):
    values = dict(values)
    active = values.get("active_model_profile", "")
    if not active:
        return values
    profile = values.get("model_profiles", {}).get(active)
    if profile is None:
        raise ValueError(f"模型配置不存在：{active}")
    if set(profile) - MODEL_PROFILE_FIELDS:
        raise ValueError("模型配置包含不支持的字段；不能修改非模型业务配置")
    # Secrets belong to a provider profile; never inherit the previous provider's credentials.
    values.update(
        model_api_key="",
        gemini_base_url="",
        model_reasoning_effort=None,
        model_provider="openai",
        model_base_url="",
        model_enabled=True,
        structured_output_method="auto",
    )
    values.update(profile)
    allowed = known_names(values.get("model_providers"))
    if not values.get("model_name") or values["model_provider"] not in allowed:
        raise ValueError(
            "请填写模型名称和已注册的接口类型（" + " / ".join(sorted(allowed)) + "）"
        )
    if values.get("structured_output_method") not in {"auto", "json_schema", "function_calling"}:
        raise ValueError("不支持该结构化输出模式")
    return values


def load_settings() -> Settings:
    path = ROOT / "config.local.json"
    values = json.loads(path.read_text()) if path.exists() else {}
    active = os.getenv("TRAVEL_ACTIVE_MODEL_PROFILE")
    if active is not None:
        values["active_model_profile"] = active
    values = apply_model_profile(values)
    # 优先级：默认值 < 本机配置 < 选中模型配置 < 环境覆盖。
    for name in Settings.model_fields:
        value = os.getenv("TRAVEL_" + name.upper())
        if value is not None:
            try:
                values[name] = json.loads(value)
            except json.JSONDecodeError:
                values[name] = value
    return Settings(**values)


settings = load_settings()

# Stable settings identity preserves all existing `from config import settings` users.
# Publish a complete dictionary in one assignment; readers in the gateway use a snapshot.
_model_reload_lock = RLock()
_MODEL_RUNTIME_FIELDS = MODEL_PROFILE_FIELDS | {
    "model_providers", "model_profiles", "active_model_profile", "model_auto_reload",
}
_model_generation = 0
_model_reload_error = None
_restart_required = []


def _model_file_signature():
    path = ROOT / "config.local.json"
    try:
        stat = path.stat()
        return (str(path), stat.st_mtime_ns, stat.st_size, stat.st_ino)
    except FileNotFoundError:
        return (str(path), None)


_model_file_seen = _model_file_signature()


def reload_model_settings():
    """Validate then atomically publish model settings in this process; never makes API calls.

    Existing invocations retain their client. A bad edit leaves the last working settings
    active. Environment overrides are re-read; changing another process's environment
    still requires a restart. Non-model settings are reported, never hot-applied.
    """
    global _model_file_seen, _model_generation, _model_reload_error, _restart_required
    from .models.registry import SLOTS, resolve
    from .models import specs

    with _model_reload_lock:
        signature = _model_file_signature()
        try:
            candidate = load_settings()
            unknown = set(candidate.model_slots) - set(SLOTS)
            if unknown:
                raise ValueError("未知模型槽位")
            for name in candidate.model_providers:
                provider = specs.provider_spec(name, candidate.model_providers)
                if provider.protocol not in specs.LANGCHAIN_PROTOCOLS | specs.HTTP_PROTOCOLS | {specs.PROTOCOL_LOCAL}:
                    raise ValueError("不支持的模型协议")
            for slot in SLOTS:
                resolved = resolve(slot, candidate)
                override = candidate.model_slots.get(slot, {})
                if slot in {"embedding", "rerank"} and override:
                    raise ValueError("embedding/rerank 暂不支持槽位覆盖；修改本地模型后需重建索引并重启")
                if resolved.timeout < 0 or (slot not in {"embedding", "rerank"} and resolved.timeout == 0):
                    raise ValueError("模型超时必须为正数")
                if resolved.structured_method not in {"auto", "json_schema", "function_calling"}:
                    raise ValueError("不支持的结构化输出模式")
                if slot in {"chat", "structured"} and resolved.protocol not in specs.LANGCHAIN_PROTOCOLS:
                    raise ValueError("对话槽位协议不支持")
                if resolved.protocol != specs.PROTOCOL_LOCAL and not resolved.model:
                    raise ValueError("缺少模型名称")
            if candidate.model_context_tokens <= 0 or candidate.model_output_tokens <= 0:
                raise ValueError("模型 token 预算必须为正数")
            changed = {name for name in Settings.model_fields
                       if getattr(candidate, name) != getattr(settings, name)}
            # Changing retrieval models without reindexing silently corrupts similarity scores,
            # even when the new model has the same dimension. Refuse the entire switch.
            if changed & {"embedding_model", "embedding_local_only", "reranker_model"}:
                raise ValueError("检索模型变更需要重建索引并重启")
            _restart_required = sorted(changed - _MODEL_RUNTIME_FIELDS)
            published = dict(settings.__dict__)
            for name in _MODEL_RUNTIME_FIELDS:
                published[name] = getattr(candidate, name)
            settings.__dict__ = published
            _model_generation += 1
            _model_reload_error = None
        except (ValueError, TypeError, OSError, KeyError):
            # Never expose validation inputs or JSON fragments: they may contain API keys.
            _model_reload_error = "模型配置重载失败，已保留原配置；请检查 JSON、供应商、槽位和检索模型重启要求"
            raise ValueError(_model_reload_error) from None
        finally:
            _model_file_seen = signature
        return model_reload_status()


def model_settings_snapshot():
    """Poll on model entry, not a background thread; each worker observes the shared file."""
    with _model_reload_lock:
        if settings.model_auto_reload and _model_file_signature() != _model_file_seen:
            try:
                reload_model_settings()
            except ValueError:
                pass  # Last good configuration remains available; status exposes rejection.
        return settings.model_copy()


def model_reload_status():
    with _model_reload_lock:
        return {"generation": _model_generation, "auto_reload": settings.model_auto_reload,
                "error": _model_reload_error, "restart_required": list(_restart_required)}
