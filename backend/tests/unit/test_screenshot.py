"""截图解析与视觉通道单测：不联网、不伪造识别结果。"""

import pytest
from travel_agent import vision
from travel_agent.config import settings
from travel_agent.parsers.screenshot import (
    detect_mime,
    parse_screenshot,
    screenshot_suggestion,
    validate_image,
)

PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 64

JPEG = b"\xff\xd8\xff\xe0" + b"0" * 64

WEBP = b"RIFF" + b"\x00" * 4 + b"WEBP" + b"0" * 64


def test_detect_mime_supports_common_screenshot_formats():
    assert detect_mime(PNG) == "image/png"
    assert detect_mime(JPEG) == "image/jpeg"
    assert detect_mime(WEBP) == "image/webp"
    assert detect_mime(b"not an image") is None


def test_validate_image_rejects_empty_non_image_and_oversize():
    with pytest.raises(ValueError):
        validate_image(b"")
    with pytest.raises(ValueError):
        validate_image(b"<html>pretend</html>")
    with pytest.raises(ValueError):
        validate_image(PNG + b"0" * (5 * 1024 * 1024))


def test_unavailable_vision_never_invents_facts(monkeypatch):
    monkeypatch.setattr(settings, "vision_enabled", False)
    monkeypatch.setattr(settings, "vision_fixture_enabled", False)
    mime, parsed = parse_screenshot(PNG)
    assert mime == "image/png"
    assert parsed["status"] == "unavailable"
    assert parsed["fields"] == {}
    assert parsed["unknowns"]
    text = screenshot_suggestion("trip.png", parsed)
    assert "手动录入" in text and "没有被读取" in text
    assert "识别到" not in text


def test_fixture_result_is_explicitly_synthetic(monkeypatch):
    monkeypatch.setattr(settings, "vision_enabled", False)
    monkeypatch.setattr(settings, "vision_fixture_enabled", True)
    _, parsed = parse_screenshot(PNG)
    assert parsed["status"] == "synthetic"
    assert parsed["synthetic"] is True
    assert "合成演示数据" in screenshot_suggestion("trip.png", parsed)


def test_reader_exception_becomes_explicit_gap():
    def broken(raw, mime):
        raise RuntimeError("provider exploded")

    _, parsed = parse_screenshot(PNG, reader=broken)
    assert parsed["status"] == "error"
    assert "异常" in parsed["error"]
    assert "识别失败" in screenshot_suggestion("trip.png", parsed)


def test_ok_result_marks_unverified_and_lists_unknowns():
    parsed = {
        "status": "ok",
        "fields": {
            "cities": ["成都"],
            "dates": ["2026-05-01"],
            "places": [],
            "days": None,
            "budget_text": None,
            "notes": [],
            "raw_text": "成都 3 日",
        },
        "unknowns": ["景点或场所", "游玩天数"],
        "requires_confirmation": True,
        "synthetic": False,
    }
    text = screenshot_suggestion("trip.png", parsed)
    assert "成都" in text and "2026-05-01" in text
    assert "尚未核实" in text and "不要替我假设" in text
    assert len(text) <= 1200


def test_normalize_fields_coerces_types_and_reports_unknowns():
    fields, unknowns = vision.normalize_fields(
        {
            "cities": "北京",
            "dates": ["2026-05-01", 20260502],
            "places": None,
            "days": None,
            "budget_text": "¥800",
            "notes": ["带娃"],
            "raw_text": "北京",
        }
    )
    assert fields["cities"] == ["北京"]
    assert fields["places"] == []
    assert fields["days"] is None
    assert "游玩天数" in unknowns and "景点或场所" in unknowns
    assert "目的地城市" not in unknowns


def test_extract_json_handles_code_fence_and_rejects_garbage():
    payload = vision._extract_json('```json\n{"cities": ["上海"]}\n```')
    assert payload == {"cities": ["上海"]}
    with pytest.raises(ValueError):
        vision._extract_json("这是一段没有 JSON 的说明")
    with pytest.raises(ValueError):
        vision._extract_json("{not json}")


def test_recognize_failure_is_captured_as_error(monkeypatch):
    class FakeResponse:
        status_code = 429

    class FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def post(self, *args, **kwargs):
            return FakeResponse()

    monkeypatch.setattr(settings, "vision_enabled", True)
    monkeypatch.setattr(settings, "vision_api_key", "test-key")
    monkeypatch.setattr(vision.httpx, "Client", FakeClient)
    parsed = vision.read_screenshot(PNG, "image/png")
    assert parsed["status"] == "error"
    assert parsed["fields"] == {}
    assert "拒绝" in parsed["error"]


def test_recognize_success_returns_normalized_fields(monkeypatch):
    import json

    class FakeResponse:
        status_code = 200

        @staticmethod
        def json():
            return {
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(
                                {
                                    "cities": ["杭州"],
                                    "dates": [],
                                    "places": ["西湖"],
                                    "days": "2 天",
                                    "budget_text": None,
                                    "notes": [],
                                    "raw_text": "杭州西湖",
                                },
                                ensure_ascii=False,
                            )
                        }
                    }
                ]
            }

    class FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def post(self, *args, **kwargs):
            return FakeResponse()

    monkeypatch.setattr(settings, "vision_enabled", True)
    monkeypatch.setattr(settings, "vision_api_key", "test-key")
    monkeypatch.setattr(vision.httpx, "Client", FakeClient)
    monkeypatch.setattr(settings, "model_slots", {"vision": {"model": "actual-vision-model"}})
    parsed = vision.read_screenshot(PNG, "image/png")
    assert parsed["status"] == "ok"
    assert parsed["source"]["model"] == "actual-vision-model"
    assert parsed["fields"]["cities"] == ["杭州"]
    assert parsed["fields"]["days"] == "2 天"
    assert parsed["requires_confirmation"] is True
    assert "预算或价格" in parsed["unknowns"]
