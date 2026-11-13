"""Failure-path contracts; simulated models here are not model-quality evaluations."""

import uuid
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch
from sqlalchemy import select
from langchain_core.messages import AIMessageChunk
from travel_agent.db import Session, Event, Task, PrivacyCleanup
from travel_agent.worker import acquire, execute
from travel_agent.agent.harness import Harness
from travel_agent.config import settings
from travel_agent.conversation import extract, gate, to_requirements


def task(account):
    return account.post(
        "/api/v1/tasks",
        json={
            "request_key": uuid.uuid4().hex,
            "fixture": True,
            "message": "合成流程验证",
            "requirements": {"city": "北京", "days": 2, "origin": "北京站", "start_date": "2027-05-01"},
        },
    ).json()


def test_provider_chunks_persist_in_order_not_template_tokens(account, monkeypatch):
    created = task(account)
    lease, _ = acquire(created["id"])
    monkeypatch.setattr(settings, "model_enabled", True)
    monkeypatch.setattr(settings, "model_api_key", "contract-test-only")

    class Model:
        def stream(self, messages):
            yield AIMessageChunk(content="方案")
            yield AIMessageChunk(content="说明")

    with patch("travel_agent.agent.harness.model", return_value=Model()):
        assert Harness(created["id"], lease).stream_reply([], "B") == "方案说明"
    with Session.begin() as db:
        events = db.scalars(select(Event).where(Event.task_id == created["id"]).order_by(Event.id)).all()
        chunks = [e.data for e in events if e.kind == "assistant_token"]
        assert [c["delta"] for c in chunks] == ["方案", "说明"]
        assert all(c["variant"] == "B" for c in chunks)
        db.get(Task, created["id"]).status = "cancelled"


def test_preferences_seed_and_twenty_turn_conditions(account):
    response = account.put("/api/v1/preferences", json={"default_city": "上海", "default_days": "2"})
    assert response.status_code == 200
    assert account.put("/api/v1/preferences", json={"default_days": "99"}).status_code == 422
    conv = account.post("/api/v1/conversations", json={"fixture": True}).json()
    assert conv["slots"]["destination"] == "上海"
    slots = {
        **conv["slots"],
        "needs_accommodation": False,
        "start_location": "declined",
        "interests": "历史文化",
    }
    for i in range(20):
        slots, _, _, _ = extract("谢谢" if i % 2 else "这次不用推荐酒店", slots, fixture=True)
        assert gate(slots, i + 1, ["origin", "accommodation", "intent"], "直接规划")[0] is None
        assert slots["destination"] == "上海" and slots["duration"] == "2 days"
        assert slots["needs_accommodation"] is False


def test_change_city_invalidates_previous_city_allocation():
    slots, _, _, _ = extract("北京两天、上海两天", {}, fixture=True)
    slots, _, _, _ = extract("改去杭州三天", slots, fixture=True)
    assert to_requirements(slots).city == "杭州"
    assert not to_requirements(slots).city_stays


def test_hotel_requires_server_candidate_and_current_version(account):
    created = task(account)
    execute(created["id"])
    trip = account.get("/api/v1/trips/" + created["trip_id"]).json()
    endpoint = f"/api/v1/trips/{trip['id']}"
    assert (
        account.post(
            endpoint + "/hotel", json={"city": "北京", "place_id": "forged", "base_version": 1}
        ).status_code
        == 409
    )
    candidates = account.get(endpoint + "/hotels", params={"query": "北京站", "city": "北京"}).json()["items"]
    chosen = {"city": "北京", "place_id": candidates[0]["id"], "base_version": trip["version"]}
    assert account.post(endpoint + "/hotel", json=chosen).status_code == 200
    assert account.post(endpoint + "/hotel", json=chosen).status_code == 409
    saved = account.get(endpoint).json()
    assert saved["plan"]["hotels"][0]["booking_status"] == "未预订"


def test_cleanup_is_durable_after_es_failure(account):
    from travel_agent.privacy_cleanup import process_pending

    with Session.begin() as db:
        pending = PrivacyCleanup(owner="synthetic-deleted-user", document_ids=[])
        db.add(pending)
        db.flush()
        ident = pending.id
    with patch("travel_agent.privacy_cleanup.es", side_effect=TimeoutError):
        process_pending(1000)
    with Session() as db:
        assert db.get(PrivacyCleanup, ident).status == "pending"
    with patch("travel_agent.privacy_cleanup.es", return_value={}):
        process_pending(1000)
    with Session() as db:
        assert db.get(PrivacyCleanup, ident).status == "done"
        assert db.get(PrivacyCleanup, ident).owner == ""


def test_local_jwt_key_creation_is_atomic(tmp_path, monkeypatch):
    from travel_agent.security import signing_key

    monkeypatch.setattr(settings, "data_dir", str(tmp_path))
    monkeypatch.setattr(settings, "jwt_secret", "")
    with ThreadPoolExecutor(max_workers=8) as pool:
        values = list(pool.map(lambda _: signing_key(), range(32)))
    assert len(set(values)) == 1 and len(values[0]) >= 32


def test_model_region_error_is_actionable_without_raw_exception():
    from travel_agent.model_errors import classify

    error = RuntimeError("FAILED_PRECONDITION: User location is not supported for the API use. key=private")
    safe = classify(error)
    assert safe.code == "model_region" and "密钥已读取" in str(safe)
    assert "private" not in str(safe)
