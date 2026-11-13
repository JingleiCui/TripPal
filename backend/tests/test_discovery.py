import io
import json
import zipfile
from travel_agent.db import Base, engine
from travel_agent.config import settings
from travel_agent.providers.base import ProviderError


def setup_module():
    Base.metadata.create_all(engine)


def search(account, **params):
    return account.get("/api/v1/explore", params={"city": "北京", "fixture": True, **params})


def test_discovery_requires_auth_and_valid_filters(client, account):
    from fastapi.testclient import TestClient
    from travel_agent.api import app

    other = TestClient(app)
    assert other.get("/api/v1/explore?city=北京").status_code == 401
    assert search(account, city=" ").status_code == 422
    assert search(account, category="unknown").status_code == 422
    assert search(account, category="stays").json()["items"][0]["name"].startswith("演示·北京酒店")


def test_saved_places_are_durable_idempotent_and_owner_scoped(account, client):
    result = search(account)
    assert result.status_code == 200
    place = result.json()["items"][0]
    assert place["source"]["synthetic"] is True
    saved = account.post("/api/v1/saved-places", json={"place_id": place["id"]})
    assert saved.status_code == 201, saved.text
    ident = saved.json()["id"]
    assert account.post("/api/v1/saved-places", json={"place_id": place["id"]}).json()["id"] == ident
    assert len(account.get("/api/v1/saved-places").json()) == 1
    update = account.patch(
        "/api/v1/saved-places/" + ident, json={"collection": "亲子北京", "note": "想带孩子去看看"}
    )
    assert update.status_code == 200
    assert account.get("/api/v1/saved-places").json()[0]["note"] == "想带孩子去看看"
    exported = account.get("/api/v1/privacy/export")
    with zipfile.ZipFile(io.BytesIO(exported.content)) as archive:
        data = json.loads(archive.read("personal-data.json"))
    assert data["saved_places"][0]["collection"] == "亲子北京"
    # Independent authenticated actor cannot read/change another owner's saved row.
    from fastapi.testclient import TestClient
    from travel_agent.api import app
    import uuid

    other = TestClient(app)
    auth = other.post(
        "/api/v1/auth/register",
        json={"name": "saved-" + uuid.uuid4().hex[:12], "password": "test-password-123"},
    ).json()
    other.headers["X-CSRF-Token"] = auth["csrf"]
    assert other.get("/api/v1/saved-places").json() == []
    assert other.patch("/api/v1/saved-places/" + ident, json={"collection": "偷看"}).status_code == 404
    assert other.delete("/api/v1/saved-places/" + ident).status_code == 404
    assert account.delete("/api/v1/saved-places/" + ident).status_code == 200
    assert account.get("/api/v1/saved-places").json() == []


def test_cannot_forge_or_reuse_other_users_search_candidates(account):
    assert account.post("/api/v1/saved-places", json={"place_id": "amap:invented"}).status_code == 409
    assert account.post("/api/v1/saved-places", json={"place_id": "x", "collection": " "}).status_code == 422
    token = account.headers.pop("X-CSRF-Token")
    assert account.post("/api/v1/saved-places", json={"place_id": "x"}).status_code == 403
    account.headers["X-CSRF-Token"] = token


def test_live_failure_never_falls_back_to_synthetic(account, monkeypatch):
    from travel_agent.providers import amap

    def unavailable(*args):
        raise ProviderError("credentials", "test")

    monkeypatch.setattr(amap, "search_places", unavailable)
    response = search(account, fixture=False)
    assert response.status_code == 503
    assert "items" not in response.json()
    monkeypatch.setattr(settings, "fixture_enabled", False)
    assert search(account).status_code == 403
