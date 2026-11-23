from travel_agent.providers import amap, booking


def test_poi_detail(monkeypatch):
    monkeypatch.setattr(
        amap,
        "request",
        lambda *a, **k: {
            "data": {"poi": {"id": "B0", "name": "外滩", "type": "风景名胜", "tel": "123"}},
            "retrieved_at": "t",
        },
    )
    detail = amap.poi_detail("amap:B0", "上海")
    assert detail["name"] == "外滩"
    assert detail["phone"] == "123"


def test_distance_matrix(monkeypatch):
    monkeypatch.setattr(
        amap,
        "request",
        lambda *a, **k: {"data": {"results": [{"distance": [1000]}]}, "retrieved_at": "t"},
    )
    result = amap.distance_matrix(["1,2"], ["3,4"])
    assert result["rows"]


def test_traffic_route_congestion_summary(monkeypatch):
    monkeypatch.setattr(
        amap,
        "request",
        lambda *a, **k: {
            "data": {
                "route": {
                    "paths": [
                        {
                            "distance": 1000,
                            "duration": 600,
                            "steps": [{"traffic_status": "缓行"}, {"traffic_status": "畅通"}],
                        }
                    ]
                }
            },
            "retrieved_at": "t",
        },
    )
    plan = amap.traffic_route(
        {"id": "a", "name": "A", "lon": 1, "lat": 1}, {"id": "b", "name": "B", "lon": 2, "lat": 2}
    )
    assert "traffic" in plan
    assert plan["traffic"]["has_congestion"] is True
    assert "拥堵" in plan["traffic_note"]


def test_booking_intent_valid():
    intent = booking.build_intent("hotel", "如家", "上海")
    assert intent["status"].startswith("意图")
    assert intent["party"] == 1


def test_booking_intent_invalid_kind():
    try:
        booking.build_intent("invalid", "x", "y")
    except ValueError:
        return
    raise AssertionError("expected ValueError for invalid kind")


def test_booking_intent_party_clamped():
    intent = booking.build_intent("hotel", "如家", "上海", party=99)
    assert intent["party"] == 12
