"""模型供应商注册表（纯数据层）。

本模块刻意不 import ``config``，因此 ``config.py`` 可以安全地引用
``KNOWN_PROVIDER_NAMES`` 而不会产生循环导入。新增供应商只需在这里加一条
``ProviderSpec``，或在 ``config.local.json`` 的 ``model_providers`` 里声明，
不需要改动任何调用点。
"""

from __future__ import annotations

from dataclasses import dataclass, field

CHAT_PATH = "/chat/completions"

# 供应商协议。所有走 HTTP 的槽位统一收敛为这两种，避免每个调用点各拼一套 URL。
PROTOCOL_OPENAI = "openai"  # OpenAI-compatible chat/completions
PROTOCOL_NATIVE = "dashscope_native"  # 百炼原生多模态生成（TTS）
PROTOCOL_OLLAMA = "ollama"  # 本机 Ollama，走 LangChain 原生驱动
PROTOCOL_GEMINI = "gemini"  # Google 官方 SDK
PROTOCOL_LOCAL = "local"  # 进程内模型，无需 API

HTTP_PROTOCOLS = {PROTOCOL_OPENAI, PROTOCOL_NATIVE}
LANGCHAIN_PROTOCOLS = {PROTOCOL_OPENAI, PROTOCOL_OLLAMA, PROTOCOL_GEMINI}


@dataclass(frozen=True)
class ProviderSpec:
    """一个供应商的静态连接信息；凭证与模型名由 registry 按槽位注入。"""

    name: str
    label: str
    protocol: str
    base_url: str = ""
    default_model: str = ""
    chat_path: str = CHAT_PATH
    key_env: str = ""  # 仅用于提示与可选的环境变量兜底
    structured_method: str = "auto"  # auto / json_schema / function_calling
    capabilities: frozenset[str] = frozenset({"chat", "structured"})
    extra_headers: dict = field(default_factory=dict)
    # 请求体级厂商参数，例如 OpenRouter 的 {"reasoning": {"enabled": False}}。
    extra_body: dict = field(default_factory=dict)
    requires_key: bool = True
    notes: str = ""

    @property
    def fingerprint(self):
        return (
            self.name,
            self.protocol,
            self.base_url,
            self.chat_path,
            self.structured_method,
            tuple(sorted(self.extra_headers.items())),
            repr(sorted(self.extra_body.items())),
        )


BUILTIN_PROVIDERS: dict[str, ProviderSpec] = {
    "openrouter": ProviderSpec(
        name="openrouter",
        label="OpenRouter（OpenAI-compatible 聚合网关，含 :free 免费模型）",
        protocol=PROTOCOL_OPENAI,
        base_url="https://openrouter.ai/api/v1",
        default_model="inclusionai/ling-3.2-flash:free",
        key_env="OPENROUTER_API_KEY",
        structured_method="json_schema",
        capabilities=frozenset({"chat", "structured", "vision"}),
        notes=(
            "必须填具体的 :free 模型 ID，按用途选：文本/结构化 ling-3.2-flash 或 ernie-5.5-flash-preview，"
            "视觉 nemotron-3.5-super-vl。'openrouter/free' 是真实存在的自动路由器，"
            "但每次请求可能落到不同模型，json_schema / tool calling 行为不稳定，不建议作默认。"
            "免费额度约 20 RPM / 50~200 RPD，用 scripts/check_providers.py --probe 实测。"
        ),
    ),
    "dashscope": ProviderSpec(
        name="dashscope",
        label="阿里云百炼 Qwen（OpenAI 兼容模式）",
        protocol=PROTOCOL_OPENAI,
        base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
        default_model="qwen-plus",
        key_env="DASHSCOPE_API_KEY",
        structured_method="function_calling",
        capabilities=frozenset({"chat", "structured", "vision"}),
    ),
    "openai": ProviderSpec(
        name="openai",
        label="OpenAI 官方 / 任意 OpenAI-compatible 网关",
        protocol=PROTOCOL_OPENAI,
        base_url="https://api.openai.com/v1",
        default_model="gpt-4o-mini",
        key_env="OPENAI_API_KEY",
        structured_method="function_calling",
        capabilities=frozenset({"chat", "structured", "vision"}),
        notes="项目里 model_provider=openai 是历史语义：表示 OpenAI-compatible，不特指 OpenAI 官方。",
    ),
    "siliconflow": ProviderSpec(
        name="siliconflow",
        label="硅基流动 SiliconFlow",
        protocol=PROTOCOL_OPENAI,
        base_url="https://api.siliconflow.cn/v1",
        default_model="Qwen/Qwen2.5-7B-Instruct",
        key_env="SILICONFLOW_API_KEY",
        structured_method="json_schema",
        capabilities=frozenset({"chat", "structured", "vision"}),
    ),
    "deepseek": ProviderSpec(
        name="deepseek",
        label="DeepSeek 官方",
        protocol=PROTOCOL_OPENAI,
        base_url="https://api.deepseek.com/v1",
        default_model="deepseek-chat",
        key_env="DEEPSEEK_API_KEY",
        structured_method="json_schema",
        capabilities=frozenset({"chat", "structured"}),
    ),
    "gemini": ProviderSpec(
        name="gemini",
        label="Google Gemini 官方 SDK",
        protocol=PROTOCOL_GEMINI,
        key_env="GOOGLE_API_KEY",
        structured_method="json_schema",
        capabilities=frozenset({"chat", "structured"}),
        requires_key=True,
        notes="地区限制时 model_errors.classify 会给出明确的 model_region 错误。",
    ),
    "ollama": ProviderSpec(
        name="ollama",
        label="本机 Ollama（无外发请求、无需 API key）",
        protocol=PROTOCOL_OLLAMA,
        base_url="http://127.0.0.1:11434",
        default_model="qwen3.5:9b",
        structured_method="json_schema",
        capabilities=frozenset({"chat", "structured", "vision"}),
        requires_key=False,
    ),
    "dashscope_native": ProviderSpec(
        name="dashscope_native",
        label="百炼原生多模态（ASR / TTS 专用）",
        protocol=PROTOCOL_NATIVE,
        base_url="https://dashscope.aliyuncs.com",
        default_model="qwen3-asr-flash",
        chat_path="/compatible-mode/v1/chat/completions",
        key_env="DASHSCOPE_API_KEY",
        capabilities=frozenset({"asr", "tts"}),
        notes="ASR 走 /compatible-mode/v1/chat/completions；TTS 走原生 generation 端点，两者协议不同但共用凭证。",
    ),
    "local": ProviderSpec(
        name="local",
        label="进程内本地模型（BGE embedding / reranker）",
        protocol=PROTOCOL_LOCAL,
        default_model="BAAI/bge-small-zh-v1.5",
        capabilities=frozenset({"embedding", "rerank"}),
        requires_key=False,
    ),
}

KNOWN_PROVIDER_NAMES = frozenset(BUILTIN_PROVIDERS)

SPEC_FIELDS = frozenset(
    {
        "protocol",
        "base_url",
        "default_model",
        "chat_path",
        "key_env",
        "structured_method",
        "capabilities",
        "extra_headers",
        "extra_body",
        "requires_key",
        "label",
        "notes",
    }
)


def build_spec(name, raw=None):
    """把内置预设 + 用户自定义覆盖合成 ProviderSpec。"""
    base = BUILTIN_PROVIDERS.get(name)
    raw = dict(raw or {})
    unknown = set(raw) - SPEC_FIELDS
    if unknown:
        raise ValueError(f"供应商 {name} 包含不支持的字段：{', '.join(sorted(unknown))}")
    if base is None and not raw.get("protocol"):
        raise ValueError(f"未知供应商 {name}；请在 model_providers 中声明 protocol，或使用内置名称")
    if base is None:
        return ProviderSpec(
            name=name,
            label=raw.pop("label", name),
            protocol=raw.pop("protocol"),
            base_url=raw.pop("base_url", ""),
            default_model=raw.pop("default_model", ""),
            chat_path=raw.pop("chat_path", CHAT_PATH),
            key_env=raw.pop("key_env", ""),
            structured_method=raw.pop("structured_method", "auto"),
            capabilities=frozenset(raw.pop("capabilities", ["chat", "structured"])),
            extra_headers=dict(raw.pop("extra_headers", {})),
            extra_body=dict(raw.pop("extra_body", {})),
            requires_key=bool(raw.pop("requires_key", True)),
            notes=raw.pop("notes", ""),
        )
    fields = {
        "name": name,
        "label": base.label,
        "protocol": base.protocol,
        "base_url": base.base_url,
        "default_model": base.default_model,
        "chat_path": base.chat_path,
        "key_env": base.key_env,
        "structured_method": base.structured_method,
        "capabilities": base.capabilities,
        "extra_headers": dict(base.extra_headers),
        "extra_body": dict(base.extra_body),
        "requires_key": base.requires_key,
        "notes": base.notes,
    }
    for key, value in raw.items():
        if key == "capabilities":
            value = frozenset(value)
        elif key in {"extra_headers", "extra_body"}:
            value = dict(value)
        fields[key] = value
    return ProviderSpec(**fields)


def provider_spec(name, custom=None):
    """按名称取供应商定义；自定义表可覆盖内置预设。"""
    override = (custom or {}).get(name)
    return build_spec(name, override)


def known_names(custom=None):
    return KNOWN_PROVIDER_NAMES | set(custom or {})
