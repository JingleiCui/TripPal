"""能力门控：把一组「能力」映射到 Agent 可见/可调用的工具集合。

设计目的（对标 TREK 的 addon 能力门控，但更轻、与工具预算/租约互补）：
- LLM 在一个会话里只看到启用能力对应的工具，减少误用与提示噪声；
- 外部 MCP server 用 scope 表达同样的收敛，使「能力」同时约束内部 Agent 与
  外部调用方。

约定：``capabilities`` 为空列表 = 放开全部（向后兼容旧配置）。
"""

from __future__ import annotations

# 规范工具名（与 agent/graph.py 中 @tool 名以及 mcp/server.py 的 tool 名对齐）。
TOOL_CAPABILITIES: dict[str, set[str]] = {
    # 地图与空间事实
    "search_places": {"maps"},
    "resolve_origin": {"maps"},
    "poi_detail": {"maps"},
    "distance_matrix": {"maps"},
    "traffic_route": {"maps"},
    "query_weather": {"maps", "weather"},
    # 美食（来源：高德 POI + 美团美食）
    "meituan_food": {"dining", "meituan"},
    # 住宿与酒旅商品（来源：美团）
    "query_lodging": {"lodging", "meituan"},
    "meituan_deals": {"lodging", "meituan"},
    "booking_intent": {"lodging"},
    # 私人资料检索
    "search_private_guides": {"knowledge"},
}

# 反向：能力 -> 工具集合
CAPABILITY_TOOLS: dict[str, set[str]] = {}
for _tool, _caps in TOOL_CAPABILITIES.items():
    for _cap in _caps:
        CAPABILITY_TOOLS.setdefault(_cap, set()).add(_tool)

ALL_CAPABILITIES: list[str] = sorted(CAPABILITY_TOOLS.keys())
DEFAULT_CAPABILITIES: list[str] = list(ALL_CAPABILITIES)


def _normalize(enabled: list[str] | None) -> list[str]:
    if not enabled:
        return []
    return [c for c in enabled if c in CAPABILITY_TOOLS]


def resolve_enabled_tools(enabled: list[str] | None, *, tool_names: set[str] | None = None) -> set[str]:
    """返回在给定能力下允许暴露的工具名集合。

    - ``enabled`` 为空/None → 放开 TOOL_CAPABILITIES 中的全部工具；
    - 否则取这些能力并集覆盖的工具。
    - ``tool_names`` 限定只在该批工具中筛选（用于仅门控 LLM 工具子集）。
    """
    caps = _normalize(enabled)
    if not caps:
        allowed = set(TOOL_CAPABILITIES)
    else:
        allowed = set().union(*(CAPABILITY_TOOLS[c] for c in caps))
    if tool_names is not None:
        allowed &= tool_names
    return allowed


def capability_scope(capability: str) -> str:
    """能力到 MCP scope 的映射，外部调用方凭 scope 获得对应工具授权。"""
    return "travel_agent:" + capability
