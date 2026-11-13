from datetime import timedelta
from unittest.mock import patch
import uuid
import pytest
from travel_agent.db import Session, Task, now
from travel_agent.worker import acquire
from travel_agent.agent.harness import Harness, Cancelled
from travel_agent.config import settings
from travel_agent.providers.base import ProviderError, read_json, safe_url
from travel_agent.providers import amap
from travel_agent.knowledge import index_document, search


def test_expired_lease_is_fenced(account):
    result = account.post(
        "/api/v1/tasks", json={"request_key": uuid.uuid4().hex, "message": "test", "fixture": True}
    ).json()
    ident = result["id"]
    first, _ = acquire(ident)
    with Session.begin() as db:
        db.get(Task, ident).lease_until = now() - timedelta(seconds=1)
    second, _ = acquire(ident)
    assert first != second
    with pytest.raises(Cancelled):
        Harness(ident, first).check()


def test_readonly_retry_is_bounded():
    import httpx

    with (
        patch("travel_agent.providers.base.httpx.Client") as client,
        patch("travel_agent.providers.base.time.sleep"),
    ):
        client.return_value.__enter__.return_value.get.side_effect = httpx.ReadTimeout("timeout")
        with pytest.raises(ProviderError, match="超时"):
            read_json("https://test.invalid/retry", {"q": uuid.uuid4().hex})
        assert client.return_value.__enter__.return_value.get.call_count == 3


def test_business_error_not_cached():
    response = type(
        "R", (), {"status_code": 200, "json": lambda _: {"status": "0", "info": "INVALID_USER_KEY"}}
    )()
    with patch("travel_agent.providers.base.httpx.Client") as client:
        client.return_value.__enter__.return_value.get.return_value = response
        with pytest.raises(ProviderError, match="INVALID_USER_KEY"):
            read_json("https://test.invalid/schema", {"q": uuid.uuid4().hex})
        assert client.return_value.__enter__.return_value.get.call_count == 1


def test_no_unsafe_source_links():
    assert safe_url("javascript:alert(1)") is None
    assert safe_url("https://user:secret@example.com") is None


def test_provider_nonfinite_numbers_are_unknown():
    assert amap.number("NaN") is None
    assert amap.number("Infinity") is None
    assert amap.number("-4") is None


@pytest.mark.timeout(180)
def test_real_bge_es_owner_version_delete(account, client):
    from travel_agent.db import Document

    response = account.post(
        "/api/v1/documents",
        files={"file": ("source.txt", "合成资料：测试景区需要提前三天预约，携带预约凭证。".encode())},
    )
    ident = response.json()["id"]
    index_document(ident)
    with Session() as db:
        doc = db.get(Document, ident)
        assert doc.status == "ready", doc.info
        owner = doc.owner
    result = search(owner, "需要提前多久预约")
    assert any("三天" in h["text"] for h in result["hits"])
    assert search("unrelated-owner", "需要提前多久预约")["hits"] == []
    # Failed reindex must not remove the visible old generation.
    with patch("travel_agent.knowledge.embed", side_effect=RuntimeError("injected embedding failure")):
        index_document(ident)
    assert search(owner, "需要提前多久预约")["hits"]
    assert account.delete("/api/v1/documents/" + ident).status_code == 200
    assert not any(h["doc_id"] == ident for h in search(owner, "需要提前多久预约")["hits"])


def test_voice_disabled_does_not_call_cloud():
    from travel_agent.voice import transcribe

    with patch.object(settings, "voice_enabled", False), patch("travel_agent.voice.httpx.Client") as client:
        with pytest.raises(ProviderError):
            transcribe(b"fake")
        assert not client.called
