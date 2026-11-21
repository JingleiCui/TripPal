"""Schema generation with a single bounded correction, never invented fallback data."""

import re
from pydantic import ValidationError
from langchain_core.messages import HumanMessage
from ..config import settings, model_settings_snapshot
from ..providers.base import ProviderError
from ..models import specs
from ..models.registry import ConfigurationError, resolve


def is_ollama():
    """是否走本机 Ollama。判定统一交给 registry，避免 URL 逻辑散落多处。"""
    try:
        return resolve("chat").protocol == specs.PROTOCOL_OLLAMA
    except ConfigurationError:
        return False


def structured_method(configuration=None):
    """结构化输出方式由供应商能力决定，仍允许 structured_output_method 全局覆盖。"""
    try:
        return resolve("structured", configuration).structured_method
    except ConfigurationError:
        return "json_schema" if is_ollama() or settings.model_provider == "gemini" else "function_calling"


def diagnostic(result, method):
    raw = result.get("raw")
    metadata = getattr(raw, "response_metadata", {}) or {}
    finish = metadata.get("finish_reason") or metadata.get("done_reason")
    error = result.get("parsing_error")
    errors = []
    for _ in range(4):
        if error is None or isinstance(error, ValidationError):
            break
        error = getattr(error, "__cause__", None)
    if isinstance(error, ValidationError):
        errors = [{"field": ".".join(map(str, e["loc"])), "type": e["type"]} for e in error.errors()][:8]
    content = getattr(raw, "content", "")
    # No raw prose or hidden reasoning is persisted: diagnostics retain shape and lengths only.
    kind = (
        "truncated"
        if finish in {"length", "max_tokens", "MAX_TOKENS"}
        else "empty_output"
        if not content and not getattr(raw, "tool_calls", [])
        else "missing_tool_call"
        if method == "function_calling" and not getattr(raw, "tool_calls", [])
        else "field_validation"
        if errors
        else "invalid_json"
    )
    return {
        "reason": kind,
        "finish_reason": finish,
        "fields": errors,
        "content_chars": len(str(content)),
        "tool_calls": len(getattr(raw, "tool_calls", []) or []),
        "invalid_tool_calls": len(getattr(raw, "invalid_tool_calls", []) or []),
    }


def generate(schema, messages, label, harness=None, validator=None):
    from .harness import model

    configuration = model_settings_snapshot()
    method = structured_method(configuration)
    prompts = list(messages)
    last = None
    for attempt in range(2):
        runnable = model("structured", configuration=configuration).with_structured_output(
            schema, method=method, include_raw=True
        )
        result = (
            harness.invoke(runnable, prompts, label, allow_unparsed=True)
            if harness
            else runnable.invoke(prompts)
        )
        parsed = result.get("parsed")
        info = diagnostic(result, method)
        try:
            if result.get("parsing_error") or parsed is None:
                raise ProviderError(
                    "schema",
                    f"模型未返回符合约定的结构（{label}："
                    + {
                        "truncated": "输出被截断",
                        "empty_output": "输出为空",
                        "missing_tool_call": "未返回工具调用",
                        "field_validation": "字段不符合要求",
                        "invalid_json": "JSON 无法解析",
                    }[info["reason"]]
                    + "）",
                )
            if not isinstance(parsed, schema):
                parsed = schema.model_validate(parsed)
            if validator:
                validator(parsed)
            return parsed
        except (ProviderError, ValueError, ValidationError) as exc:
            last = exc
            if isinstance(exc, ValidationError):
                info = {
                    "reason": "field_validation",
                    "fields": [
                        {"field": ".".join(map(str, e["loc"])), "type": e["type"]} for e in exc.errors()
                    ][:8],
                }
            elif not isinstance(exc, ProviderError):
                info = {"reason": "business_validation", "message": str(exc)[:160]}
            if harness:
                harness.emit(
                    "schema_validation",
                    label=label,
                    model=settings.model_name,
                    provider=settings.model_provider,
                    method=method,
                    correction=attempt,
                    success=False,
                    **info,
                )
            if attempt == 0:
                details = str(info)
                details = re.sub(r"https?://\S+", "[url]", details)
                prompts.append(
                    HumanMessage(
                        content="上次输出未通过校验："
                        + details
                        + ". 重新返回完整的指定结构；不能新增候选 ID，不能删除锁定条件。"
                    )
                )
    if isinstance(last, ProviderError):
        raise last
    raise ProviderError("schema", "模型输出未通过业务校验：" + str(last)[:160]) from last
