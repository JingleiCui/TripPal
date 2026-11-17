"""输入通道端点集成测试：截图与语音在未配置时都不能伪造识别结果。"""

from travel_agent.config import settings

PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 64


def test_health_reports_input_channel_status(client):
    body = client.get("/api/v1/health").json()
    assert "voice_enabled" in body
    assert "voice_ready" in body
    assert body["vision_status"] in {
        "needs_key",
        "configured_not_verified",
        "synthetic_fixture",
    }


def test_upload_screenshot_without_vision_reports_gap(account, monkeypatch):
    monkeypatch.setattr(settings, "vision_enabled", False)
    monkeypatch.setattr(settings, "vision_fixture_enabled", False)
    result = account.post(
        "/api/v1/attachments",
        files={"file": ("trip.png", PNG, "image/png")},
    )
    assert result.status_code == 201, result.text
    body = result.json()
    assert body["kind"] == "screenshot"
    assert body["parsed"]["status"] == "unavailable"
    assert body["parsed"]["requires_confirmation"] is True
    assert "没有被读取" in body["suggestion"]


def test_upload_screenshot_with_fixture_is_marked_synthetic(account, monkeypatch):
    monkeypatch.setattr(settings, "vision_enabled", False)
    monkeypatch.setattr(settings, "vision_fixture_enabled", True)
    result = account.post(
        "/api/v1/attachments",
        files={"file": ("trip.png", PNG, "image/png")},
    )
    assert result.status_code == 201, result.text
    body = result.json()
    assert body["parsed"]["status"] == "synthetic"
    assert body["parsed"]["synthetic"] is True
    assert "合成演示数据" in body["suggestion"]


def test_upload_rejects_non_image_bytes(account):
    result = account.post(
        "/api/v1/attachments",
        files={"file": ("fake.png", b"<html>not an image</html>", "image/png")},
    )
    assert result.status_code == 201, result.text
    body = result.json()
    assert body["parsed"]["status"] == "error"
    assert "图片格式" in body["parsed"]["error"]


def test_voice_asr_without_key_is_explicit(account, monkeypatch):
    monkeypatch.setattr(settings, "voice_enabled", False)
    monkeypatch.setattr(settings, "voice_api_key", "")
    result = account.post(
        "/api/v1/voice/asr",
        files={"file": ("recording.webm", b"fake audio", "audio/webm")},
    )
    assert result.status_code == 422
    assert "语音尚未启用" in result.json()["detail"]
