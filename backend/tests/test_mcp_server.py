import json
from travel_agent.mcp.server import TravelMCPServer
from travel_agent.providers import amap, booking


def test_initialize_and_list_tools():
    srv = TravelMCPServer(granted_scopes=["travel_agent:tools"])
    init = srv.handle_request({"jsonrpc": "2.0", "id": 1, "method": "initialize"})
    assert init["result"]["serverInfo"]["name"] == "travel-agent-mcp"
    lst = srv.handle_request({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
    names = [t["name"] for t in lst["result"]["tools"]]
    assert "amap_search_places" in names
    assert "meituan_food" in names
    assert "booking_intent" in names


def test_scope_denied_without_grant():
    srv = TravelMCPServer(granted_scopes=[])  # 无授权
    resp = srv.handle_request(
        {
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {"name": "booking_intent", "arguments": {"kind": "hotel", "name": "X", "city": "Y"}},
        }
    )
    assert resp["error"]["code"] == -32001


def test_scope_permitted_and_call(monkeypatch):
    srv = TravelMCPServer(granted_scopes=["travel_agent:tools"])
    monkeypatch.setattr(amap, "search_places", lambda *a, **k: [{"id": "amap:1", "name": "测试地点"}])
    resp = srv.handle_request(
        {
            "jsonrpc": "2.0",
            "id": 4,
            "method": "tools/call",
            "params": {"name": "amap_search_places", "arguments": {"city": "北京", "query": "餐厅"}},
        }
    )
    assert resp["result"]["isError"] is False
    data = json.loads(resp["result"]["content"][0]["text"])
    assert data[0]["name"] == "测试地点"


def test_tool_error_returned_as_jsonrpc_error(monkeypatch):
    srv = TravelMCPServer(granted_scopes=["travel_agent:tools"])

    def boom(*a, **k):
        raise ValueError("boom")

    monkeypatch.setattr(booking, "build_intent", boom)
    resp = srv.handle_request(
        {
            "jsonrpc": "2.0",
            "id": 5,
            "method": "tools/call",
            "params": {"name": "booking_intent", "arguments": {"kind": "hotel", "name": "X", "city": "Y"}},
        }
    )
    assert resp["error"]["code"] == -32603


def test_booking_intent_tool(monkeypatch):
    srv = TravelMCPServer(granted_scopes=["travel_agent:tools"])
    resp = srv.handle_request(
        {
            "jsonrpc": "2.0",
            "id": 6,
            "method": "tools/call",
            "params": {"name": "booking_intent", "arguments": {"kind": "hotel", "name": "如家", "city": "上海"}},
        }
    )
    assert resp["result"]["isError"] is False
    data = json.loads(resp["result"]["content"][0]["text"])
    assert data["status"].startswith("意图")
