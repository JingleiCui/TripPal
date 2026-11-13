import json
import time
from langchain_openai import ChatOpenAI
from sqlalchemy import select
from ..db import Session, Task, Trip, Event, event, now
from ..access import role_for
from ..vendor.atlas.authz import role_can_edit
from ..config import settings
from ..providers.base import ProviderError
from ..model_errors import classify


class Cancelled(RuntimeError):
    pass


class Harness:
    def __init__(self, task_id, lease):
        self.task_id, self.lease, self.started = task_id, lease, time.monotonic()
        with Session() as db:
            events = db.scalars(select(Event).where(Event.task_id == task_id)).all()
        self.model_calls = sum(e.kind == "model_start" for e in events)
        self.tool_calls = sum(e.kind == "tool_start" for e in events)
        self.previous_seconds = (
            sum(e.data.get("elapsed_ms", 0) for e in events if e.kind in {"model_end", "tool_end"}) / 1000
        )

    def check(self):
        with Session() as db:
            task = db.get(Task, self.task_id)
            if (
                not task
                or task.lease != self.lease
                or task.status != "running"
                or not task.lease_until
                or task.lease_until < now()
            ):
                raise Cancelled("任务已取消或由新的执行器接管")
            trip = db.get(Trip, task.trip_id)
            if not trip or not role_can_edit(role_for(db, trip, task.owner)):
                raise Cancelled("行程编辑权限已被撤销")
        if self.previous_seconds + time.monotonic() - self.started > settings.task_budget_seconds:
            raise ProviderError("budget", "已达到本次执行时间上限，已保存调查过程")

    def emit(self, kind, **data):
        self.check()
        event(self.task_id, kind, **data)

    def invoke(self, model, messages, label, allow_unparsed=False):
        self.check()
        if self.model_calls >= settings.model_call_limit:
            raise ProviderError("budget", "本任务模型调用次数已达上限")
        if not settings.model_enabled or not settings.model_api_key:
            raise ProviderError("credentials", "尚未配置并启用云端模型；请填写 config.local.json")
        self.model_calls += 1
        event(
            self.task_id,
            "model_start",
            label=label,
            number=self.model_calls,
            model=settings.model_name,
            provider=settings.model_provider,
        )
        started = time.monotonic()
        try:
            result = model.invoke(messages)
            raw = result.get("raw") if isinstance(result, dict) and "parsed" in result else result
            usage = getattr(raw, "usage_metadata", None)
            if isinstance(result, dict) and "parsed" in result and not allow_unparsed:
                if result.get("parsing_error") or result.get("parsed") is None:
                    raise ProviderError("schema", "模型未返回符合约定的结构")
                result = result["parsed"]
            event(
                self.task_id,
                "model_end",
                label=label,
                elapsed_ms=round((time.monotonic() - started) * 1000),
                usage=usage or {},
                success=not (
                    isinstance(result, dict)
                    and "parsed" in result
                    and (result.get("parsed") is None or result.get("parsing_error"))
                ),
            )
            self.check()
            return result
        except Exception as exc:
            event(
                self.task_id,
                "model_end",
                label=label,
                elapsed_ms=round((time.monotonic() - started) * 1000),
                success=False,
                error_type=type(exc).__name__,
            )
            failure = classify(exc)
            if failure:
                raise failure from exc
            raise

    def tool(self, name, fn, **arguments):
        self.check()
        if self.tool_calls >= settings.tool_call_limit:
            raise ProviderError("budget", "本任务工具调用次数已达上限")
        self.tool_calls += 1
        event(self.task_id, "tool_start", name=name, arguments=arguments, number=self.tool_calls)
        started = time.monotonic()
        try:
            result = fn(**arguments)
            json.dumps(result, ensure_ascii=False, allow_nan=False)
            event(
                self.task_id,
                "tool_end",
                name=name,
                success=True,
                elapsed_ms=round((time.monotonic() - started) * 1000),
                result=result,
            )
            self.check()
            return result
        except Cancelled:
            raise
        except Exception as exc:
            event(
                self.task_id,
                "tool_end",
                name=name,
                success=False,
                elapsed_ms=round((time.monotonic() - started) * 1000),
                error_type=type(exc).__name__,
                error=str(exc)[:200] if isinstance(exc, ProviderError) else "工具执行或结构校验失败",
            )
            raise

    def stream_reply(self, messages, variant=None):
        """Only real provider chunks become token events; templates are whole messages."""
        from .graph import text_content

        self.check()
        if self.model_calls >= settings.model_call_limit:
            raise ProviderError("budget", "模型调用次数已达上限")
        if not settings.model_enabled or not settings.model_api_key:
            raise ProviderError("credentials", "模型尚未配置")
        self.model_calls += 1
        event(self.task_id, "model_start", label="对话答复", number=self.model_calls)
        event(self.task_id, "assistant_reset", variant=variant)
        started = time.monotonic()
        result = ""
        usage = {}
        try:
            for chunk in model().stream(messages):
                self.check()
                delta = text_content(chunk)
                if delta:
                    result += delta
                    event(self.task_id, "assistant_token", delta=delta, variant=variant)
                if getattr(chunk, "usage_metadata", None):
                    usage = chunk.usage_metadata
            event(
                self.task_id,
                "model_end",
                label="对话答复",
                elapsed_ms=round((time.monotonic() - started) * 1000),
                usage=usage,
                success=True,
            )
            return result
        except Exception as exc:
            event(
                self.task_id,
                "model_end",
                label="对话答复",
                elapsed_ms=round((time.monotonic() - started) * 1000),
                success=False,
                error_type=type(exc).__name__,
            )
            failure = classify(exc)
            if failure:
                raise failure from exc
            raise


def model():
    from .structured import is_ollama

    if is_ollama():
        from langchain_ollama import ChatOllama

        return ChatOllama(
            model=settings.model_name,
            base_url=settings.model_base_url.rstrip("/").removesuffix("/v1"),
            temperature=0,
            reasoning=False,
            num_ctx=settings.model_context_tokens,
            num_predict=settings.model_output_tokens,
            client_kwargs={"timeout": settings.model_timeout},
        )
    if settings.model_provider == "gemini":
        from langchain_google_genai import ChatGoogleGenerativeAI

        kwargs = {"base_url": settings.gemini_base_url} if settings.gemini_base_url else {}
        return ChatGoogleGenerativeAI(
            model=settings.model_name,
            api_key=settings.model_api_key or "not-configured",
            vertexai=False,
            timeout=settings.model_timeout,
            max_retries=0,
            max_output_tokens=settings.model_output_tokens,
            **kwargs,
        )
    return ChatOpenAI(
        model=settings.model_name,
        api_key=settings.model_api_key or "not-configured",
        base_url=settings.model_base_url,
        temperature=0,
        timeout=settings.model_timeout,
        max_retries=0,
        max_tokens=settings.model_output_tokens,
        **({"reasoning_effort": settings.model_reasoning_effort} if settings.model_reasoning_effort else {}),
    )
