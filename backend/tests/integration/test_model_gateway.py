"""可插拔模型网关单测：切换、凭证隔离、能力校验、缓存复用与状态脱敏。

全部离线；不发起任何真实模型请求。
"""

import pytest
from travel_agent.config import settings
from travel_agent.models import gateway


@pytest.fixture(autouse=True)
def _clear_gateway():
    """每个用例前后清空实例缓存，避免测试间互相污染。"""
    gateway.clear_caches()
    yield
    gateway.clear_caches()


def test_models_endpoint_reports_slots_without_secrets(client, monkeypatch):
    monkeypatch.setattr(settings, "model_api_key", "endpoint-secret")
    body = client.get("/api/v1/models").json()
    assert "slots" in body and "chat" in body["slots"]
    assert "endpoint-secret" not in str(body)
    assert "cache" in body
