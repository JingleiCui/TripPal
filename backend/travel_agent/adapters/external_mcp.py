"""外部 MCP server 桥接骨架：通过 stdio 启动并调用任意兼容 MCP 的 server。

让 Agent 把「外部工具生态」（如高德官方 amap-maps-mcp、OpenTripMap、出行/餐饮类
MCP）纳入同一能力边界：调用外部工具前同样经过 scope 校验与审计（见 mcp/server.py
的治理模型）。本文件是接入范式，不绑定某个具体外部 server。

使用前提：目标 MCP server 已在本机以 stdio 方式可启动（例如 `npx -y @amap/amap-maps-mcp`）。
生产环境应在独立线程做异步读写以避免 stdio 死锁；此处用最简同步骨架演示协议。
"""

from __future__ import annotations

import json
import os
import subprocess
import threading


class ExternalMCPBridge:
    def __init__(self, command: str, args: list[str] | None = None, timeout: int = 30):
        self.timeout = timeout
        self.proc = subprocess.Popen(
            [command, *(args or [])],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            text=True,
            env=os.environ.copy(),
            bufsize=1,
        )
        self._id = 0
        self._lock = threading.Lock()
        self._handshake()

    def _request(self, method: str, params: dict | None = None) -> dict | None:
        with self._lock:
            self._id += 1
            request = {"jsonrpc": "2.0", "id": self._id, "method": method, "params": params}
            self.proc.stdin.write(json.dumps(request, ensure_ascii=False) + "\n")
            self.proc.stdin.flush()
            while True:
                line = self.proc.stdout.readline()
                if not line:
                    return None
                try:
                    response = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if response.get("id") == request["id"]:
                    return response

    def _handshake(self):
        self._request(
            "initialize",
            {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "travel-agent-bridge", "version": "0.1.0"},
            },
        )
        self.proc.stdin.write(json.dumps({"jsonrpc": "2.0", "method": "notifications/initialized"}) + "\n")
        self.proc.stdin.flush()

    def list_tools(self) -> list[dict]:
        response = self._request("tools/list")
        return (response or {}).get("result", {}).get("tools", [])

    def call_tool(self, name: str, arguments: dict | None = None) -> dict | None:
        return self._request("tools/call", {"name": name, "arguments": arguments or {}})

    def close(self):
        try:
            self.proc.terminate()
        except Exception:
            pass


# 已知可接入的第三方 MCP（在 config.local.json 配置命令即可桥接）：
# - 高德官方：@amap/amap-maps-mcp（地点/路线/天气，与本项目 amap provider 互补，可交叉验证）
# - OpenTripMap：POI 百科类数据
# - 各 OTA / 出行服务若提供 MCP，可按此范式纳入，统一走 scope + 审计。
KNOWN_EXTERNAL_MCPS: dict[str, dict] = {
    "amap-official": {"command": "npx", "args": ["-y", "@amap/amap-maps-mcp"], "note": "高德官方 MCP"},
}
