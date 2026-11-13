"""Integration tests use a separate MySQL database; never reset the application DB."""

import os
import pytest

os.environ["TRAVEL_DATABASE_URL"] = (
    "mysql+pymysql://travel:travel_local_only@127.0.0.1:13316/travel_agent_test?charset=utf8mb4"
)
os.environ["TRAVEL_CHECKPOINT_URL"] = "mysql://travel:travel_local_only@127.0.0.1:13316/travel_agent_test"
os.environ["TRAVEL_ELASTIC_INDEX"] = "travel-agent-test-chunks"
os.environ["TRAVEL_SEMANTIC_CACHE_INDEX"] = "travel-agent-test-research-cache"
os.environ["TRAVEL_DATA_DIR"] = "/tmp/travel-agent-test-uploads"
os.environ["TRAVEL_REDIS_URL"] = "redis://127.0.0.1:16389/10"
os.environ["TRAVEL_BROKER_URL"] = "redis://127.0.0.1:16389/11"


@pytest.fixture
def client():
    from fastapi.testclient import TestClient
    from travel_agent.api import app

    return TestClient(app)


@pytest.fixture
def account(client):
    import uuid
    import redis
    from travel_agent.config import settings

    redis.Redis.from_url(settings.redis_url).flushdb()

    result = client.post(
        "/api/v1/auth/register",
        json={"name": "test-" + uuid.uuid4().hex[:12], "password": "test-password-123"},
    )
    assert result.status_code == 200, result.text
    client.headers["X-CSRF-Token"] = result.json()["csrf"]
    return client
