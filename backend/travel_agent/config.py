"""常用配置直接在这里修改；私密配置写入根目录 config.local.json。"""

from pathlib import Path
import json
import os
from pydantic import BaseModel, Field

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
}


class Settings(BaseModel):
    active_model_profile: str = ""  # 空值兼容原配置；填写 model_profiles 中的配置名即可切换
    model_profiles: dict[str, dict] = Field(default_factory=dict)
    structured_output_method: str = "auto"  # auto / json_schema / function_calling

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
    if not values.get("model_name") or values["model_provider"] not in {"openai", "ollama", "gemini"}:
        raise ValueError("请填写模型名称和有效接口类型 openai / ollama / gemini")
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
