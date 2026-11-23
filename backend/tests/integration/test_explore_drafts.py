"""The exploration workspace must not write a trip until explicit confirmation."""
import uuid
from unittest.mock import patch

from fastapi.testclient import TestClient
from sqlalchemy import select

from travel_agent.api import app
from travel_agent.db import Session, Task, Trip, User, TripMember
from travel_agent.worker import execute


def start(account, compare=False):
    conv = account.post("/api/v1/conversations", json={"fixture": True}).json()
    response = account.post(f"/api/v1/conversations/{conv['id']}/turns", json={
        "content": "北京三天，需要住宿，直接规划", "version": conv["version"],
        "request_key": uuid.uuid4().hex, "compare": compare,
    })
    assert response.status_code == 200, response.text
    execute(response.json()["task"]["id"])
    return account.get(f"/api/v1/conversations/{conv['id']}").json()


def revise(account, conv, content="安排轻松一些，直接规划"):
    return account.post(f"/api/v1/conversations/{conv['id']}/turns", json={
        "content": content, "version": conv["version"], "request_key": uuid.uuid4().hex,
        "draft_task_id": conv["task"]["id"], "draft_variant": "A",
        "draft_revision": conv["task"]["result"]["draft_revision"],
    })


def test_single_draft_preview_choices_and_confirmation(account):
    conv = start(account)
    task = conv["task"]
    assert task["status"] == "waiting_choice"
    assert set(task["result"]["variants"]) == {"A"}
    base = f"/api/v1/tasks/{task['id']}/variants/A"
    trip_id = conv["trip_id"]
    assert account.get(f"/api/v1/trips/{trip_id}").json()["version"] == 0
    result = account.get(base + "/daily-details?day=1")
    assert result.status_code == 200, result.text
    details = result.json()
    assert len(details["meals"]) == 3 and details["hotel"] and details["legs"]
    lunch = details["meals"][1]["alternatives"][1]
    choice = {"day": 1, "base_version": 1, "slot": "lunch", "place_id": lunch["id"], "mode": "public_transit"}
    assert account.post(base + "/service-choice", json={**choice, "place_id": "invented"}).status_code == 422
    assert account.post(base + "/service-choice", json=choice).json()["draft_revision"] == 2
    assert account.post(base + "/service-choice", json=choice).status_code == 409
    refreshed = account.get(base + "/daily-details?day=1").json()
    assert refreshed["meals"][1]["place"]["id"] == lunch["id"]
    assert account.get(base + "/budget").status_code == 200
    assert account.post(base + "/market-details", json={"day": 1, "place_id": lunch["id"], "kind": "food"}).status_code == 200
    assert account.get(base + "/daily-details?day=14").status_code == 404
    assert account.get(f"/api/v1/trips/{trip_id}").json()["version"] == 0
    assert account.post(base, json={"base_version": 0, "draft_revision": 1}).status_code == 409
    confirmed = account.post(base, json={"base_version": 0, "draft_revision": 2})
    assert confirmed.status_code == 200, confirmed.text
    assert account.post(base, json={"base_version": 0, "draft_revision": 2}).status_code == 200
    saved = account.get(f"/api/v1/trips/{trip_id}").json()
    assert saved["version"] == 1
    assert saved["plan"]["days"][0]["meals"][0]["place"]["id"] == lunch["id"]


def test_edit_supersedes_only_after_success(account):
    conv = start(account, compare=True)
    old = conv["task"]["id"]
    response = revise(account, conv)
    assert response.status_code == 200, response.text
    new = response.json()["task"]["id"]
    assert new != old
    assert account.post(f"/api/v1/tasks/{old}/variants/A", json={"base_version": 0}).status_code == 409
    with Session() as db:
        assert db.get(Task, old).status == "waiting_choice"
        assert db.get(Task, new).payload["draft_plan"]["days"] == conv["task"]["result"]["variants"]["A"]["days"]
    execute(new)
    assert account.get(f"/api/v1/tasks/{old}").json()["status"] == "superseded"
    assert account.get(f"/api/v1/trips/{conv['trip_id']}").json()["version"] == 0
    assert account.get(f"/api/v1/conversations/{conv['id']}").json()["task"]["status"] == "waiting_choice"


def test_failed_edit_restores_previous_draft(account):
    conv = start(account)
    response = revise(account, conv)
    with patch("travel_agent.worker.build_graph", side_effect=ValueError("测试：生成失败")):
        execute(response.json()["task"]["id"])
    restored = account.get(f"/api/v1/conversations/{conv['id']}").json()
    assert restored["task"]["id"] == conv["task"]["id"]
    assert restored["task"]["status"] == "waiting_choice"
    assert "上一份草稿已保留" in restored["messages"][-1]["content"]
    assert revise(account, restored).status_code == 200


def test_draft_access_and_version_conflicts(account):
    conv = start(account)
    ident = conv["task"]["id"]
    base = f"/api/v1/tasks/{ident}/variants/A"
    other = TestClient(app)
    auth = other.post("/api/v1/auth/register", json={"name": "draft-" + uuid.uuid4().hex[:10], "password": "password-123"}).json()
    other.headers["X-CSRF-Token"] = auth["csrf"]
    assert other.get(base + "/daily-details?day=1").status_code == 404
    with Session.begin() as db:
        user = db.scalar(select(User).where(User.name == auth["name"]))
        db.add(TripMember(trip_id=conv["trip_id"], user_id=user.id, role="viewer"))
    assert other.get(base + "/daily-details?day=1").status_code == 200
    assert other.post(base + "/service-choice", json={"day": 1, "base_version": 1, "slot": "transport", "mode": "walk"}).status_code == 403
    assert other.post(base, json={"base_version": 0}).status_code == 403
    with Session.begin() as db:
        trip = db.get(Trip, conv["trip_id"])
        trip.version = 1
    assert account.post(base, json={"base_version": 0}).status_code == 409


def test_double_variant_preview_does_not_mix_choices(account):
    conv = start(account, compare=True)
    task = conv["task"]
    base = f"/api/v1/tasks/{task['id']}/variants"
    assert set(task["result"]["variants"]) == {"A", "B"}
    a = account.get(base + "/A/daily-details?day=1").json()
    b = account.get(base + "/B/daily-details?day=1").json()
    assert a["timeline"] != b["timeline"]
    assert account.post(base + "/A/service-choice", json={"day": 1, "base_version": 1, "slot": "transport", "mode": "walk"}).status_code == 200
    assert account.get(base + "/A/daily-details?day=1").json()["mode"] == "walk"
    assert account.get(base + "/B/daily-details?day=1").json()["mode"] == "public_transit"


def test_second_variant_failure_keeps_first_draft(account, monkeypatch):
    from travel_agent.agent import graph
    original = graph.build_plan
    calls = 0

    def fail_second(*args, **kwargs):
        nonlocal calls
        calls += 1
        if calls > 1:
            raise ValueError("测试：B 方案路线查询失败")
        return original(*args, **kwargs)

    monkeypatch.setattr(graph, "build_plan", fail_second)
    conv = start(account, compare=True)
    assert conv["task"]["status"] == "waiting_choice"
    assert set(conv["task"]["result"]["variants"]) == {"A"}
    assert "方案 B 暂未生成成功" in conv["task"]["result"]["missing_variant_reason"]


def test_edit_preserves_explicit_service_choices(account):
    conv = start(account)
    base = f"/api/v1/tasks/{conv['task']['id']}/variants/A"
    details = account.get(base + "/daily-details?day=1").json()
    hotel = details["hotels"][1]
    assert account.post(base + "/service-choice", json={"day": 1, "base_version": 1, "slot": "hotel", "place_id": hotel["id"], "mode": "public_transit"}).status_code == 200
    assert account.post(base + "/service-choice", json={"day": 1, "base_version": 2, "slot": "transport", "mode": "walk"}).status_code == 200
    latest = account.get(f"/api/v1/conversations/{conv['id']}").json()
    edit = revise(account, latest)
    execute(edit.json()["task"]["id"])
    updated = account.get(f"/api/v1/conversations/{conv['id']}").json()["task"]["result"]["variants"]["A"]
    assert updated["days"][0]["transport_mode"] == "walk"
    assert any(h["id"] == hotel["id"] and h["user_selected"] for h in updated["hotels"])
