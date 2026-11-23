"""统一调用层：实例缓存、连接池复用、共享响应解析与错误分类。

效率要点：
- LangChain chat model 按配置指纹缓存，避免每次 ``model()`` 重建 SDK client 与连接池；
- ``httpx.Client`` 按 (base_url, timeout, client 类) 缓存，keep-alive 复用，不再每次请求新建；
- Bearer 拼接、URL 拼接、``choices[0].message.content`` 解析、HTTP 状态映射各只有一份实现；
- 缓存键包含凭证哈希与驱动类身份，配置变更或测试 monkeypatch 时自动失效。
"""

from __future__ import annotations

import httpx
from functools import lru_cache

from ..providers.base import ProviderError
from . import specs
from .registry import resolve

_chat_cache: dict = {}
_client_cache: dict = {}


def _driver(protocol, drivers):
    """延迟导入 SDK；drivers 允许调用方注入，便于测试替换而不改全局。"""
    if drivers and protocol in drivers:
        return drivers[protocol]
    if protocol == specs.PROTOCOL_OLLAMA:
        from langchain_ollama import ChatOllama

        return ChatOllama
    if protocol == specs.PROTOCOL_GEMINI:
        from langchain_google_genai import ChatGoogleGenerativeAI

        return ChatGoogleGenerativeAI
    from langchain_openai import ChatOpenAI

    return ChatOpenAI


def chat_model(drivers=None, slot="chat", configuration=None):
    """返回缓存的 LangChain BaseChatModel。凭证缺失不在此拦截（由 Harness 统一门控）。

    ``slot`` 允许 structured 槽位真正使用自己的模型，而不是复用 chat 实例；
    缓存键自带 slot，因此两种配置各自持有一个连接实例，互不覆盖。
    """
    from ..config import model_settings_snapshot

    settings = configuration if configuration is not None else model_settings_snapshot()
    spec = resolve(slot, settings)
    driver = _driver(spec.protocol, drivers)
    key = (spec.fingerprint, driver, getattr(settings, "model_output_tokens", 4096),
           getattr(settings, "model_context_tokens", 8192),
           getattr(settings, "model_reasoning_effort", None))
    cached = _chat_cache.get(key)
    if cached is not None:
        return cached

    if spec.protocol == specs.PROTOCOL_OLLAMA:
        instance = driver(
            model=spec.model,
            base_url=spec.base_url.rstrip("/").removesuffix("/v1"),
            temperature=0,
            reasoning=False,
            num_ctx=settings.model_context_tokens,
            num_predict=settings.model_output_tokens,
            client_kwargs={"timeout": spec.timeout},
        )
    elif spec.protocol == specs.PROTOCOL_GEMINI:
        kwargs = {"base_url": spec.base_url} if spec.base_url else {}
        instance = driver(
            model=spec.model,
            api_key=spec.api_key or "not-configured",
            vertexai=False,
            timeout=spec.timeout,
            max_retries=0,
            max_output_tokens=settings.model_output_tokens,
            **kwargs,
        )
    elif spec.protocol == specs.PROTOCOL_OPENAI:
        kwargs = {
            "model": spec.model,
            "api_key": spec.api_key or "not-configured",
            "base_url": spec.base_url,
            "temperature": 0,
            "timeout": spec.timeout,
            "max_retries": 0,
            "max_tokens": settings.model_output_tokens,
        }
        if spec.extra_headers:
            kwargs["default_headers"] = spec.extra_headers
        if spec.extra_body:
            # 例如关闭 reasoning：免费 reasoning 模型会把输出预算耗在隐藏思考上，
            # 导致 finish_reason=length 或数分钟超时。
            kwargs["extra_body"] = spec.extra_body
        if settings.model_reasoning_effort:
            kwargs["reasoning_effort"] = settings.model_reasoning_effort
        instance = driver(**kwargs)
    else:
        raise ProviderError("configuration", f"槽位 {slot} 不支持协议 {spec.protocol}")
    _chat_cache[key] = instance
    return instance


def client_for(spec):
    """共享连接池。键含 httpx.Client 类对象，monkeypatch 后自动换实例，测试隔离安全。"""
    client_class = httpx.Client
    key = (spec.base_url, spec.timeout, client_class)
    client = _client_cache.get(key)
    if client is None:
        client = client_class(
            timeout=spec.timeout,
            follow_redirects=False,  # SSRF 纪律：不跟随重定向
            trust_env=False,
        )
        _client_cache[key] = client
    return client


def chat_content(response):
    """唯一一份 OpenAI-compatible 响应解析。"""
    try:
        content = response.json()["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError, ValueError, AttributeError) as exc:
        raise ProviderError("schema", "模型返回结构不符合约定") from exc
    if not isinstance(content, str):
        raise ProviderError("schema", "模型返回结构不符合约定（content 不是文本）")
    return content


def _http_error(code, label, failure_code):
    hint = {
        400: "请求参数不被接受",
        401: "凭证无效",
        403: "权限不足或地域不支持",
        404: "模型不存在或不可用",
        408: "请求超时",
        429: "达到速率或额度限制",
    }.get(code, "服务返回异常")
    return ProviderError(
        failure_code,
        f"{label}服务拒绝或未完成请求（HTTP {code}：{hint}），请核对模型名、地域及额度",
    )


def _post(slot, path, body, *, label, failure_code, unavailable_code, spec=None):
    """所有 HTTP 模型调用的唯一出口：统一鉴权、URL、错误映射。"""
    spec = spec if spec is not None else resolve(slot)
    if not spec.ready:
        raise ProviderError("disabled", f"{label}尚未启用或缺少凭证")
    body = {**body, **spec.extra_body}
    url = spec.base_url.rstrip("/") + "/" + path.lstrip("/")
    headers = {
        **({"Authorization": "Bearer " + spec.api_key} if spec.api_key else {}),
        "Content-Type": "application/json",
        **{k: v for k, v in spec.extra_headers.items() if v},
    }
    client = client_for(spec)
    try:
        response = client.post(url, headers=headers, json=body, timeout=spec.timeout)
    except httpx.HTTPError as exc:
        raise ProviderError(unavailable_code, f"{label}服务连接失败，请求未完成") from exc
    if response.status_code != 200:
        raise _http_error(response.status_code, label, failure_code)
    return response


def post_chat(slot, body, *, label, failure_code, unavailable_code, path=None, spec=None):
    """走 chat/completions 的槽位（vision / asr / 自定义），直接返回文本 content。"""
    spec = spec if spec is not None else resolve(slot)
    response = _post(
        slot,
        path or spec.chat_path,
        body,
        label=label,
        failure_code=failure_code,
        unavailable_code=unavailable_code,
        spec=spec,
    )
    return chat_content(response)


def post_json(slot, path, body, *, label, failure_code, unavailable_code, spec=None):
    """非标准响应体（如百炼原生 TTS）用这个，返回完整 JSON dict。"""
    response = _post(
        slot,
        path,
        body,
        label=label,
        failure_code=failure_code,
        unavailable_code=unavailable_code,
        spec=spec,
    )
    try:
        payload = response.json()
    except (ValueError, TypeError, AttributeError) as exc:
        raise ProviderError("schema", f"{label}返回不是合法 JSON") from exc
    if not isinstance(payload, dict):
        raise ProviderError("schema", f"{label}返回结构不符合约定")
    return payload


def download(url, *, allowed_suffix, max_bytes, unavailable_code, label):
    """受 SSRF 约束的二进制下载（TTS 音频）。"""
    from urllib.parse import urlparse

    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname or not parsed.hostname.endswith(allowed_suffix):
        raise ProviderError("schema", f"{label}返回地址不在允许的服务域名内")
    https_url = "https://" + url.split("://", 1)[1]
    spec = resolve("tts")
    client = client_for(spec)
    audio = bytearray()
    try:
        with client.stream("GET", https_url) as stream:
            stream.raise_for_status()
            for piece in stream.iter_bytes():
                audio.extend(piece)
                if len(audio) > max_bytes:
                    raise ProviderError("size", f"{label}返回内容超过上限")
    except httpx.HTTPError as exc:
        raise ProviderError(unavailable_code, f"{label}结果下载失败") from exc
    return bytes(audio)


def clear_caches():
    """配置热切换或测试隔离时调用；不会关闭 httpx 连接池以外的资源。"""
    _chat_cache.clear()


def close_all():
    clear_caches()
    for client in _client_cache.values():
        close = getattr(client, "close", None)
        if callable(close):
            close()
    _client_cache.clear()


def reset():
    """完全重建：先关连接池，再清空 chat 实例缓存。"""
    close_all()
    clear_caches()


def cache_stats():
    return {"chat_models": len(_chat_cache), "http_clients": len(_client_cache)}


@lru_cache(maxsize=2)
def _local_model(slot, name, local_only):
    """Process-local retrieval adapters; model changes require a controlled restart."""
    if slot == "embedding":
        import torch
        from sentence_transformers import SentenceTransformer

        torch.set_num_threads(2)
        return SentenceTransformer(name, device="cpu", local_files_only=local_only)
    from sentence_transformers import CrossEncoder

    return CrossEncoder(name, device="cpu", local_files_only=local_only)


def local_model(slot):
    """Single loader for the existing local embedding and reranking entry points."""
    from ..config import model_settings_snapshot

    if slot not in {"embedding", "rerank"}:
        raise ValueError("local_model only supports embedding/rerank")
    configuration = model_settings_snapshot()
    spec = resolve(slot, configuration)
    return _local_model(slot, spec.model, configuration.embedding_local_only)


def transcribe_local(wav, spec):
    from .local_speech import transcribe
    return transcribe(wav, spec)


def synthesize_local(text, spec):
    from .local_speech import synthesize
    return synthesize(text, spec)
