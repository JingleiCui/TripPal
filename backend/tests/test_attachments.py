from travel_agent.config import settings
from travel_agent.parsers import analyze
from travel_agent.parsers.gpx import parse_gpx
from travel_agent.parsers.order import parse_order

GPX = b"""<?xml version="1.0"?>
<gpx version="1.1" creator="test">
<trk><trkseg>
<trkpt lat="31.230" lon="121.470"><ele>10</ele></trkpt>
<trkpt lat="31.240" lon="121.480"></trkpt>
</trkseg></trk></gpx>"""


def test_parse_gpx():
    result = parse_gpx(GPX)
    assert result["point_count"] == 2
    assert result["distance_meters"] > 0
    assert "start" in result and "end" in result


def test_analyze_gpx():
    kind, parsed, suggestion = analyze("route.gpx", GPX)
    assert kind == "gpx"
    assert parsed["point_count"] == 2
    assert "公里" in suggestion


def test_analyze_order_text():
    kind, parsed, suggestion = analyze(
        "order.txt", "上海 2026-05-01 如家酒店 ¥299 订单号 ABC123".encode("utf-8")
    )
    assert kind == "order"
    assert "上海" in parsed["cities"]
    assert "2026-05-01" in parsed["dates"]
    assert "299" in parsed["amounts"]


PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 64


def test_analyze_image_without_vision_reports_explicit_gap(monkeypatch):
    monkeypatch.setattr(settings, "vision_enabled", False)
    monkeypatch.setattr(settings, "vision_fixture_enabled", False)
    kind, parsed, suggestion = analyze("receipt.png", PNG)
    assert kind == "screenshot"
    assert parsed["status"] == "unavailable"
    assert parsed["requires_confirmation"] is True
    assert "未能识别" in suggestion and "没有被读取" in suggestion


def test_analyze_image_with_injected_vision_reader():
    def reader(raw, mime):
        assert mime == "image/png"
        return {
            "status": "ok",
            "fields": {"cities": ["杭州"], "dates": [], "places": ["西湖"], "days": None,
                       "budget_text": None, "notes": [], "raw_text": "杭州 西湖"},
            "unknowns": ["日期", "游玩天数"],
            "requires_confirmation": True,
            "synthetic": False,
            "source": {"provider": "vision_model"},
        }

    kind, parsed, suggestion = analyze("trip.png", PNG, vision_reader=reader)
    assert kind == "screenshot"
    assert parsed["status"] == "ok"
    assert "杭州" in suggestion and "西湖" in suggestion
    assert "尚未核实" in suggestion
    assert "未识别到" in suggestion


def test_parse_order_no_match():
    parsed = parse_order("这是一段无关文本")
    assert parsed["cities"] == []
    assert parsed["venues"] == []
