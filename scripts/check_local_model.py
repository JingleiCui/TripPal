"""Run directly: verify the configured local model, never send probes to a cloud endpoint."""

from pathlib import Path
import json
import sys
import time
import urllib.request
from urllib.parse import urlparse

TARGET_MODEL = "qwen3.5:9b"
EXPECTED_CONTEXT = 8192
REPORT_NAME = "qwen35-readiness.json"
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from langchain_core.messages import HumanMessage, SystemMessage, ToolMessage
from langchain_core.tools import tool
from pydantic import BaseModel
from travel_agent.config import settings
from travel_agent.agent.harness import model


class City(BaseModel):
    city: str
    days: int


@tool
def add_numbers(a: int, b: int) -> int:
    """Add two integers. Use this tool to compute an exact sum."""
    return a + b


def main():
    url = urlparse(settings.model_base_url)
    if (
        settings.model_provider != "openai"
        or url.hostname not in {"127.0.0.1", "localhost"}
        or url.port != 11434
        or settings.model_name != TARGET_MODEL
    ):
        raise SystemExit("当前不是指定的本地模型；未调用任何模型。请核对 config.local.json。")
    report = {"model": TARGET_MODEL, "endpoint": settings.model_base_url, "checks": {}}
    llm = model()

    def check(name, fn):
        started = time.monotonic()
        try:
            result = fn()
            report["checks"][name] = {
                "passed": True,
                "seconds": round(time.monotonic() - started, 3),
                "result": result,
            }
        except Exception as exc:
            report["checks"][name] = {
                "passed": False,
                "seconds": round(time.monotonic() - started, 3),
                "error_type": type(exc).__name__,
            }
        print(name, "passed" if report["checks"][name]["passed"] else "FAILED", flush=True)

    def chat():
        response = llm.invoke("只回答一个汉字：好")
        assert "好" in response.text
        return {"text": response.text, "usage": response.usage_metadata}

    def structured(method):
        result = llm.with_structured_output(City, method=method).invoke("从文字中提取：在北京游玩两天。")
        assert result.city == "北京" and result.days == 2
        return result.model_dump()

    def tool_roundtrip():
        bound = llm.bind_tools([add_numbers])
        messages = [
            SystemMessage("必须调用 add_numbers 工具计算，拿到工具结果后只输出答案。"),
            HumanMessage("请使用工具计算 17 + 25。"),
        ]
        response = bound.invoke(messages)
        assert len(response.tool_calls) == 1
        call = response.tool_calls[0]
        assert call["name"] == "add_numbers"
        assert call["args"] == {"a": 17, "b": 25}
        result = add_numbers.invoke(call["args"])
        messages.extend([response, ToolMessage(content=str(result), tool_call_id=call["id"])])
        final = bound.invoke(messages)
        assert not final.tool_calls and "42" in final.text
        return {"tool": call["name"], "arguments": call["args"], "result": result, "reply": final.text}

    def context():
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with opener.open("http://127.0.0.1:11434/api/ps", timeout=10) as response:
            models = json.load(response)["models"]
        active = next(item for item in models if item["name"] == TARGET_MODEL)
        assert active["context_length"] == EXPECTED_CONTEXT
        return {"context_length": active["context_length"], "size_vram": active.get("size_vram")}

    check("chat", chat)
    check("json_schema", lambda: structured("json_schema"))
    check("function_calling_schema", lambda: structured("function_calling"))
    check("tool_roundtrip", tool_roundtrip)
    check("runtime_context", context)
    report["passed"] = all(result["passed"] for result in report["checks"].values())
    report["scope"] = "Real local model probes; not complete itinerary quality or live travel provider acceptance."
    target = ROOT / "reports" / REPORT_NAME
    target.parent.mkdir(exist_ok=True)
    target.write_text(json.dumps(report, ensure_ascii=False, indent=2))
    print("Report:", target)
    raise SystemExit(0 if report["passed"] else 1)


if __name__ == "__main__":
    main()
