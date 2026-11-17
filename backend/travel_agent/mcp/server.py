"""受治理的 MCP server（自实现 JSON-RPC over stdio，无需外部依赖）。

为什么自己实现而非引入 fastmcp：项目要求的可治理信号是「scope 授权 + 审计日志 +
工具收敛」，这些都能在标准 MCP 协议之上自行表达；自实现避免引入未经验证的外部
依赖，且让我们对 scope 校验与审计有完全控制权。

协议覆盖：initialize / ping / tools/list / tools/call。每个工具声明 required_scope，
调用前按授予的 scopes 校验；每次调用写一条 AuditLog（actor=mcp），使 Agent 的对外
工具调用可追溯。同一 server 实例也可被 HTTP 端点复用（见 mcp_api.py）。
"""

from __future__ import annotations

import json
import sys

from ..config import settings
from ..capabilities import capability_scope
from ..providers import amap, meituan, booking
from .. import knowledge
from ..providers.base import ProviderError
from ..db import Session, AuditLog, ensure_tables


def _place(lon, lat, name="地点", pid="pt"):
    return {"id": pid, "name": name, "lon": float(lon), "lat": float(lat), "city": ""}


# 每个工具：name / description / input_schema / scope(能力) / handler
TOOL_SPECS: list[dict] = [
    {
        "name": "amap_search_places",
        "description": "按关键词检索城市的地点 POI（景点、餐厅、酒店等），返回名称、坐标、地址与来源。",
        "scope": capability_scope("maps"),
        "input_schema": {
            "type": "object",
            "properties": {
                "city": {"type": "string", "description": "城市名"},
                "query": {"type": "string", "description": "关键词，如 餐厅 美食"},
                "types": {"type": "string", "description": "可选 POI 大类码，如 050000"},
            },
            "required": ["city"],
        },
        "handler": lambda **a: amap.search_places(a["city"], a.get("query", ""), types=a.get("types")),
    },
    {
        "name": "amap_poi_detail",
        "description": "查询地点详情：开放时间、电话、评分、照片。poi_id 取自已检索地点（amap: 前缀）。",
        "scope": capability_scope("maps"),
        "input_schema": {
            "type": "object",
            "properties": {
                "poi_id": {"type": "string"},
                "city": {"type": "string"},
            },
            "required": ["poi_id"],
        },
        "handler": lambda **a: amap.poi_detail(a["poi_id"], a.get("city", "")),
    },
    {
        "name": "amap_route",
        "description": "两点间路线（步行/公交/驾车），返回耗时、距离、费用与导航链接。",
        "scope": capability_scope("maps"),
        "input_schema": {
            "type": "object",
            "properties": {
                "a_lon": {"type": "number"}, "a_lat": {"type": "number"},
                "b_lon": {"type": "number"}, "b_lat": {"type": "number"},
                "mode": {"type": "string", "enum": ["walk", "public_transit", "drive"]},
                "a_name": {"type": "string"}, "b_name": {"type": "string"},
            },
            "required": ["a_lon", "a_lat", "b_lon", "b_lat"],
        },
        "handler": lambda **a: amap.route_between(
            _place(a["a_lon"], a["a_lat"], a.get("a_name", "起点")),
            _place(a["b_lon"], a["b_lat"], a.get("b_name", "终点")),
            a.get("mode", "public_transit"),
            "",
        ),
    },
    {
        "name": "amap_distance_matrix",
        "description": "多点到多点的距离矩阵。origins/destinations 为 'lon,lat' 字符串列表。",
        "scope": capability_scope("maps"),
        "input_schema": {
            "type": "object",
            "properties": {
                "origins": {"type": "array", "items": {"type": "string"}},
                "destinations": {"type": "array", "items": {"type": "string"}},
                "mode": {"type": "string", "enum": ["driving", "straight"]},
            },
            "required": ["origins", "destinations"],
        },
        "handler": lambda **a: amap.distance_matrix(a["origins"], a["destinations"], a.get("mode", "driving")),
    },
    {
        "name": "amap_traffic_route",
        "description": "实时路况路线：驾车路线并给出拥堵摘要。",
        "scope": capability_scope("maps"),
        "input_schema": {
            "type": "object",
            "properties": {
                "a_lon": {"type": "number"}, "a_lat": {"type": "number"},
                "b_lon": {"type": "number"}, "b_lat": {"type": "number"},
            },
            "required": ["a_lon", "a_lat", "b_lon", "b_lat"],
        },
        "handler": lambda **a: amap.traffic_route(
            _place(a["a_lon"], a["a_lat"], "起点"), _place(a["b_lon"], a["b_lat"], "终点")
        ),
    },
    {
        "name": "amap_weather",
        "description": "查询城市近期天气。",
        "scope": capability_scope("weather"),
        "input_schema": {
            "type": "object",
            "properties": {"city": {"type": "string"}},
            "required": ["city"],
        },
        "handler": lambda **a: amap.weather(a["city"]),
    },
    {
        "name": "meituan_query",
        "description": "通过官方美团酒旅接口查询酒店、门票或交通商品，返回原文价格与链接。",
        "scope": capability_scope("meituan"),
        "input_schema": {
            "type": "object",
            "properties": {"city": {"type": "string"}, "question": {"type": "string"}},
            "required": ["city"],
        },
        "handler": lambda **a: meituan.query(a["city"], a.get("question", "")),
    },
    {
        "name": "meituan_food",
        "description": "通过美团查询城市餐厅、特色美食与团购，返回原文价格与链接。",
        "scope": capability_scope("dining"),
        "input_schema": {
            "type": "object",
            "properties": {"city": {"type": "string"}, "query": {"type": "string"}},
            "required": ["city"],
        },
        "handler": lambda **a: meituan.food_recommend(a["city"], a.get("query", "")),
    },
    {
        "name": "knowledge_search",
        "description": "检索当前用户导入的私人攻略与说明（owner 为空时返回提示）。",
        "scope": capability_scope("knowledge"),
        "input_schema": {
            "type": "object",
            "properties": {"owner": {"type": "string"}, "query": {"type": "string"}},
            "required": ["query"],
        },
        "handler": lambda **a: knowledge.search(a.get("owner") or "", a["query"], limit=5),
    },
    {
        "name": "booking_intent",
        "description": "记录一项预订意图（酒店/门票/交通/餐饮），仅结构化意图，不执行支付或下单。",
        "scope": capability_scope("lodging"),
        "input_schema": {
            "type": "object",
            "properties": {
                "kind": {"type": "string", "enum": ["hotel", "ticket", "transport", "dining", "other"]},
                "name": {"type": "string"},
                "city": {"type": "string"},
                "date": {"type": "string"},
                "party": {"type": "integer"},
                "budget": {"type": "string"},
            },
            "required": ["kind", "name", "city"],
        },
        "handler": lambda **a: booking.build_intent(
            a["kind"], a["name"], a["city"], a.get("date", ""), a.get("party", 1), a.get("budget", "")
        ),
    },
]

SERVER_INFO = {
    "name": "travel-agent-mcp",
    "version": "0.1.0",
    "vendor": "travel_agent",
    "description": "受治理的旅行规划工具服务：scope 授权 + 审计日志 + 工具收敛。",
}


class TravelMCPServer:
    def __init__(self, granted_scopes: list[str] | None = None):
        self.granted_scopes = list(granted_scopes if granted_scopes is not None else settings.mcp_scopes)
        self.tools = {spec["name"]: spec for spec in TOOL_SPECS}

    def _permitted(self, required_scope: str) -> bool:
        if "*" in self.granted_scopes or required_scope in self.granted_scopes:
            return True
        # "travel_agent:tools" 作为通配，放行所有 travel_agent:* 工具。
        if "travel_agent:tools" in self.granted_scopes and required_scope.startswith("travel_agent:"):
            return True
        return False

    def _audit(self, scope, name, arguments, success, error, detail):
        try:
            with Session() as db:
                db.add(
                    AuditLog(
                        actor="mcp",
                        scope=scope,
                        tool=name,
                        arguments=arguments,
                        success=1 if success else 0,
                        error=error,
                        detail=detail,
                    )
                )
        except Exception:
            # 审计失败不应阻断工具执行。
            pass

    def handle_request(self, obj: dict) -> dict | None:
        method = obj.get("method")
        msg_id = obj.get("id")
        if method == "initialize":
            return {
                "jsonrpc": "2.0",
                "id": msg_id,
                "result": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {"tools": {"listChanged": False}},
                    "serverInfo": SERVER_INFO,
                },
            }
        if method == "ping":
            return {"jsonrpc": "2.0", "id": msg_id, "result": {}}
        if method == "tools/list":
            return {
                "jsonrpc": "2.0",
                "id": msg_id,
                "result": {
                    "tools": [
                        {
                            "name": spec["name"],
                            "description": spec["description"],
                            "inputSchema": spec["input_schema"],
                            "annotations": {"scope": spec["scope"]},
                        }
                        for spec in TOOL_SPECS
                    ]
                },
            }
        if method == "tools/call":
            _argument = (obj.get("params") or {}).get("name")
            arguments = (obj.get("params") or {}).get("arguments") or {}
            spec = self.tools.get(_argument)
            if not spec:
                return self._error(msg_id, -32601, f"未知工具：{_argument}")
            if not self._permitted(spec["scope"]):
                self._audit(spec["scope"], spec["name"], arguments, False, "scope_denied", {})
                return self._error(
                    msg_id, -32001, f"缺少授权范围 {spec['scope']}；已授予：{self.granted_scopes}"
                )
            try:
                result = spec["handler"](**arguments)
                text = json.dumps(result, ensure_ascii=False, default=str)
                self._audit(spec["scope"], spec["name"], arguments, True, "", {"bytes": len(text)})
                return {
                    "jsonrpc": "2.0",
                    "id": msg_id,
                    "result": {"content": [{"type": "text", "text": text}], "isError": False},
                }
            except ProviderError as exc:
                self._audit(spec["scope"], spec["name"], arguments, False, exc.code, {})
                return self._error(msg_id, -32000, f"{exc.code}: {exc.args[0]}")
            except Exception as exc:  # noqa: BLE001
                self._audit(spec["scope"], spec["name"], arguments, False, type(exc).__name__, {})
                return self._error(msg_id, -32603, f"工具执行失败：{type(exc).__name__} {exc}")
        # 通知类（initialized 等）无需回复。
        return None

    @staticmethod
    def _error(msg_id, code, message):
        return {"jsonrpc": "2.0", "id": msg_id, "error": {"code": code, "message": message}}

    def serve_stdio(self):
        ensure_tables()
        for raw in sys.stdin:
            raw = raw.strip()
            if not raw:
                continue
            try:
                obj = json.loads(raw)
            except json.JSONDecodeError:
                continue
            response = self.handle_request(obj)
            if response is not None:
                sys.stdout.write(json.dumps(response, ensure_ascii=False) + "\n")
                sys.stdout.flush()


server = TravelMCPServer()


def main():
    TravelMCPServer().serve_stdio()


if __name__ == "__main__":
    main()
