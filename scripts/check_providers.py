"""模型网关自检：逐槽位检查配置，并可选做一次真实最小调用。

用法（在仓库根目录，使用 .venv/bin/python）：
    python scripts/check_providers.py                      # 只查配置，不联网
    python scripts/check_providers.py --probe              # 对当前 profile 做真实调用
    python scripts/check_providers.py --profile openrouter_free --probe
    python scripts/check_providers.py --json               # 机器可读输出

--profile 通过 TRAVEL_ACTIVE_MODEL_PROFILE 临时切换，不修改 config.local.json，
正好演示「环境变量 > 配置文件」的切换机制。脚本绝不打印 API key 明文。
"""

from __future__ import annotations

import argparse
import json
import os
import struct
import sys
import zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))


def probe_png():
    """一张有效的 160x60 RGB PNG。

    不能用 1x1 占位图：视觉 provider 会以 "media could not be screened" 拒绝，
    导致 --probe-vision 出现与模型能力无关的假失败。
    """
    width, height = 160, 60
    rows = b"".join(b"\x00" + bytes([40, 120, 200]) * width for _ in range(height))

    def chunk(tag, data):
        return (
            struct.pack(">I", len(data))
            + tag
            + data
            + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)
        )

    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(rows))
        + chunk(b"IEND", b"")
    )


def parse_args():
    parser = argparse.ArgumentParser(description="travel_agent 模型网关自检")
    parser.add_argument("--probe", action="store_true", help="对已就绪槽位做真实最小调用（会产生少量额度消耗）")
    parser.add_argument("--probe-vision", action="store_true", help="额外探测视觉槽位（需独立开通）")
    parser.add_argument("--profile", default="", help="临时切换到 model_profiles 中的某个配置")
    parser.add_argument("--all-profiles", action="store_true", help="逐个检查所有 profile 的配置解析")
    parser.add_argument("--json", action="store_true", help="输出 JSON")
    return parser.parse_args()


def collect():
    from travel_agent.models import gateway
    from travel_agent.models.registry import status

    return {**status(), "cache": gateway.cache_stats()}


def probe_chat():
    from langchain_core.messages import HumanMessage
    from travel_agent.agent.harness import model

    reply = model().invoke([HumanMessage(content="只回复两个字：就绪")])
    return {"ok": True, "sample": str(getattr(reply, "content", ""))[:60]}


def probe_structured():
    from langchain_core.messages import HumanMessage
    from pydantic import BaseModel, Field
    from travel_agent.agent.structured import generate, structured_method

    class Probe(BaseModel):
        ready: bool = Field(description="是否理解指令，请填 true")

    result = generate(
        Probe,
        [HumanMessage(content="这是一个连通性探测。请返回 ready=true。")],
        "provider-probe",
    )
    return {"ok": bool(result.ready), "method": structured_method()}


def probe_tools():
    """LangGraph 的领域 Agent 依赖 bind_tools；免费模型对 tool calling 支持不一致。"""
    from langchain_core.messages import HumanMessage
    from langchain_core.tools import tool
    from travel_agent.agent.harness import model

    @tool
    def probe_echo(text: str) -> str:
        """回显传入文本，仅用于连通性探测。"""
        return text

    reply = model().bind_tools([probe_echo]).invoke(
        [HumanMessage(content="请调用 probe_echo 工具，text 参数填 连通。")]
    )
    calls = getattr(reply, "tool_calls", []) or []
    return {
        "ok": True if calls else None,  # None = 警告，不算硬失败
        "tool_calls": len(calls),
        "note": "" if calls else "模型未发起工具调用；该供应商可能不适合承担领域 Agent",
    }


def probe_vision():
    from travel_agent import vision

    fields, unknowns = vision.recognize(probe_png(), "image/png")
    return {"ok": True, "cities": fields.get("cities", []), "unknowns": len(unknowns)}


def run(args):
    payload = collect()
    probes = {}
    if args.probe:
        from travel_agent.models.registry import ready

        # tools 不是独立槽位，复用 chat 的就绪状态。
        for name, slot, fn in (
            ("chat", "chat", probe_chat),
            ("structured", "structured", probe_structured),
            ("tools", "chat", probe_tools),
        ):
            if not ready(slot):
                probes[name] = {"ok": False, "skipped": "未配置凭证"}
                continue
            try:
                probes[name] = fn()
            except Exception as exc:  # 自检必须把任何失败如实报出，不吞异常
                probes[name] = {"ok": False, "error_type": type(exc).__name__, "error": str(exc)[:200]}
        if args.probe_vision:
            if not ready("vision"):
                probes["vision"] = {"ok": False, "skipped": "未配置凭证或未启用"}
            else:
                try:
                    probes["vision"] = probe_vision()
                except Exception as exc:
                    probes["vision"] = {"ok": False, "error_type": type(exc).__name__, "error": str(exc)[:200]}
        for slot in ("asr", "tts", "embedding", "rerank"):
            note = (
                "本地进程内模型，无 API 可探测" if slot in {"embedding", "rerank"}
                else "需要真实音频与 FFmpeg，脚本不做自动探测"
            )
            probes[slot] = {"ok": None, "skipped": note}
    payload["probes"] = probes

    if args.all_profiles:
        from travel_agent.config import apply_model_profile, settings

        path = ROOT / "config.local.json"
        raw = json.loads(path.read_text()) if path.exists() else {}
        profiles = {}
        for name in settings.model_profiles:
            candidate = {**raw, "active_model_profile": name}
            try:
                resolved = apply_model_profile(candidate)
                profiles[name] = {
                    "ok": True,
                    "provider": resolved.get("model_provider"),
                    "model": resolved.get("model_name"),
                    "key_present": bool(resolved.get("model_api_key")),
                }
            except Exception as exc:
                profiles[name] = {"ok": False, "error": str(exc)[:200]}
        payload["profiles"] = profiles
    return payload


def render(payload):
    print(f"当前 profile : {payload['active_model_profile'] or '(未指定，使用平铺字段)'}")
    print(f"已注册供应商: {', '.join(payload['available_providers'])}")
    print("-" * 96)
    print(f"{'槽位':<12}{'状态':<16}{'供应商':<20}{'协议':<20}{'模型':<28}")
    print("-" * 96)
    for slot, info in payload["slots"].items():
        print(
            f"{slot:<12}{info.get('status', ''):<16}{info.get('provider', '-'):<20}"
            f"{info.get('protocol', '-'):<20}{str(info.get('model', '-'))[:26]:<28}"
        )
        if info.get("error"):
            print(f"    └─ {info['error']}")
    print("-" * 96)
    print(f"实例缓存: {payload['cache']}")
    if payload.get("probes"):
        print("\n真实调用探测：")
        for name, result in payload["probes"].items():
            if result.get("skipped"):
                print(f"  {name:<12} SKIP  {result['skipped']}")
            elif result.get("ok") is True:
                print(f"  {name:<12} OK    {json.dumps({k: v for k, v in result.items() if k != 'ok'}, ensure_ascii=False)}")
            elif result.get("ok") is None:
                print(f"  {name:<12} WARN  {result.get('note', '')}")
            else:
                print(f"  {name:<12} FAIL  {result.get('error_type', '')}: {result.get('error', '')}")
        if any(r.get("ok") is False for r in payload["probes"].values()):
            print("\n结论：探测未完成（缺少凭证或调用失败），进程退出码为 1。")
    if payload.get("profiles"):
        print("\nProfile 切换检查：")
        for name, result in payload["profiles"].items():
            print(f"  {name:<20} {'OK' if result['ok'] else 'FAIL'}  {result.get('provider', '')} / {result.get('model', '')} / key={result.get('key_present')}")


def main():
    args = parse_args()
    if args.profile:
        os.environ["TRAVEL_ACTIVE_MODEL_PROFILE"] = args.profile
    payload = run(args)
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        render(payload)
    if args.probe:
        failed = [name for name, r in payload["probes"].items() if r.get("ok") is False]
        return 1 if failed else 0
    misconfigured = [name for name, info in payload["slots"].items() if info.get("status") == "misconfigured"]
    return 1 if misconfigured else 0


if __name__ == "__main__":
    sys.exit(main())
