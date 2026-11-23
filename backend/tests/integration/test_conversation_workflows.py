import uuid

from fastapi.testclient import TestClient
from travel_agent.worker import execute


def test_conversation_persistence_compare_and_choice(account):
    conv = account.post("/api/v1/conversations", json={"fixture": True}).json()
    first = account.post(
        f"/api/v1/conversations/{conv['id']}/turns",
        json={"content": "去北京", "request_key": uuid.uuid4().hex, "version": 0},
    ).json()
    assert first["state"]["last_question"] == "duration", first
    dated = account.post(
        f"/api/v1/conversations/{conv['id']}/turns",
        json={"content": "三天", "request_key": uuid.uuid4().hex, "version": 1},
    ).json()
    assert dated["state"]["last_question"] == "travel_dates", dated
    body = {"content": "2027-05-01，直接规划", "request_key": uuid.uuid4().hex, "version": 2, "compare": True}
    second = account.post(f"/api/v1/conversations/{conv['id']}/turns", json=body)
    assert second.status_code == 200, second.text
    second = second.json()
    task_id = second["state"]["task_id"]
    execute(task_id)
    task = account.get("/api/v1/tasks/" + task_id).json()
    assert task["status"] == "waiting_choice", task
    assert set(task["result"]["variants"]) == {"A", "B"}
    assert account.get("/api/v1/trips/" + second["trip_id"]).json()["version"] == 0
    chosen = account.post(f"/api/v1/tasks/{task_id}/variants/B", json={"base_version": 0})
    assert chosen.status_code == 200, chosen.text
    assert account.post(f"/api/v1/tasks/{task_id}/variants/B", json={"base_version": 0}).status_code == 200
    assert account.post(f"/api/v1/tasks/{task_id}/variants/A", json={"base_version": 0}).status_code == 409
    saved = account.get("/api/v1/trips/" + second["trip_id"]).json()
    assert saved["version"] == 1
    assert (
        saved["plan"]["days"][0]["stops"][0]["id"]
        != task["result"]["variants"]["A"]["days"][0]["stops"][0]["id"]
    )
    assert len(account.get("/api/v1/conversations/" + conv["id"]).json()["messages"]) >= 5
    replay = account.post(f"/api/v1/conversations/{conv['id']}/turns", json=body)
    assert replay.status_code == 200
    assert replay.json()["state"]["task_id"] == task_id


def test_viewer_editor_and_revocation(account):
    from travel_agent.api import app

    member = TestClient(app)
    task = account.post(
        "/api/v1/tasks",
        json={
            "request_key": uuid.uuid4().hex,
            "fixture": True,
            "message": "test",
            "requirements": {"city": "北京", "start_date": "2027-05-01", "origin": "北京站"},
        },
    ).json()
    execute(task["id"])
    trip = account.get("/api/v1/trips/" + task["trip_id"]).json()
    name = "member-" + uuid.uuid4().hex[:10]
    other = member.post("/api/v1/auth/register", json={"name": name, "password": "test-password-123"}).json()
    member.headers["X-CSRF-Token"] = other["csrf"]
    assert (
        account.put(
            f"/api/v1/trips/{trip['id']}/members", json={"username": name, "role": "viewer"}
        ).status_code
        == 200
    )
    visible = member.get("/api/v1/trips/" + trip["id"])
    assert visible.status_code == 200
    assert visible.json()["role"] == "viewer"
    assert (
        member.put(f"/api/v1/trips/{trip['id']}/locks", json={"version": 1, "locked_ids": []}).status_code
        == 403
    )
    assert any(t["id"] == trip["id"] for t in member.get("/api/v1/trips").json())
    account.put(f"/api/v1/trips/{trip['id']}/members", json={"username": name, "role": "editor"})
    member_id = account.get(f"/api/v1/trips/{trip['id']}/members").json()["members"][0]["user_id"]
    assert (
        member.put(f"/api/v1/trips/{trip['id']}/locks", json={"version": 1, "locked_ids": []}).status_code
        == 200
    )
    assert account.delete(f"/api/v1/trips/{trip['id']}/members/{member_id}").status_code == 200
    assert member.get("/api/v1/trips/" + trip["id"]).status_code == 404
