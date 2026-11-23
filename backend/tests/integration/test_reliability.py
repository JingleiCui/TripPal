import uuid
from datetime import timedelta
from unittest.mock import patch

import pytest
from travel_agent.agent.harness import Cancelled, Harness
from travel_agent.db import Session, Task, now
from travel_agent.knowledge import index_document, search
from travel_agent.worker import acquire


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
