import json
import time
from langchain_openai import ChatOpenAI
from sqlalchemy import select
from ..db import Session, Task, Trip, Event, event, now
from ..access import role_for
from ..roles import role_can_edit
from ..config import settings
from ..providers.base import ProviderError
from ..model_errors import classify
from ..models import gateway
from ..models.registry import chat_ready


class Cancelled(RuntimeError):
    pass


class Harness:
    def __init__(self, task_id, lease, capabilities=None):
        self.task_id, self.lease, self.started = task_id, lease, time.monotonic()
        # 能力门控：空列表 = 放开全部（向后兼容）。
        self.capabilities = list(capabilities or [])
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

    def filter_tools(self, tools):
        """按启用能力收敛暴露给 LLM 的工具集合（与工具预算/租约互补）。"""
        from ..capabilities import resolve_enabled_tools

        if not self.capabilities:
            return tools
        allowed = resolve_enabled_tools(self.capabilities, tool_names={t.name for t in tools})
        return [t for t in tools if t.name in allowed]

    def invoke(self, model, messages, label, allow_unparsed=False):
        self.check()
        if self.model_calls >= settings.model_call_limit:
            raise ProviderError("budget", "本任务模型调用次数已达上限")
        if not chat_ready():
            raise ProviderError("credentials", "尚未配置并启用模型；请填写 config.local.json 的 API key")
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
        if not chat_ready():
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


def model(slot="chat"):
    """唯一的 LLM 构造入口。

    具体实现（协议分派、实例缓存、额外 headers）统一收在 models.gateway；
    这里只注入 ChatOpenAI 驱动，保持对既有测试与调用方的接口不变。
    ``slot=\"structured\"`` 时返回独立的结构化输出模型实例。
    """
    return gateway.chat_model(drivers={"openai": ChatOpenAI}, slot=slot)
