from travel_agent.capabilities import resolve_enabled_tools, ALL_CAPABILITIES, capability_scope


def test_empty_means_all():
    assert resolve_enabled_tools([]) == resolve_enabled_tools(None)
    # 全开应包含地图与美团类工具
    all_tools = resolve_enabled_tools([])
    assert "search_places" in all_tools
    assert "meituan_food" in all_tools
    assert "query_lodging" in all_tools


def test_gating_converges_tools():
    allowed = resolve_enabled_tools(["maps"])
    assert "search_places" in allowed
    assert "query_lodging" not in allowed
    assert "meituan_food" not in allowed
    assert "poi_detail" in allowed


def test_partial_capabilities():
    allowed = resolve_enabled_tools(["dining", "meituan"], tool_names={"meituan_food", "query_lodging", "search_places"})
    # meituan_food 属于 dining+meituan；query_lodging 也属于 meituan 能力，因此同批暴露。
    assert allowed == {"meituan_food", "query_lodging"}


def test_capability_scope_mapping():
    assert capability_scope("maps") == "travel_agent:maps"
    assert capability_scope("meituan") == "travel_agent:meituan"
    assert set(ALL_CAPABILITIES)
