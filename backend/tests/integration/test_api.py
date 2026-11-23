import uuid

from travel_agent.config import settings
from travel_agent.worker import execute


def request(**overrides):
    return {
        "request_key": uuid.uuid4().hex,
        "message": "请安排北京三日行程",
        "fixture": True,
        "requirements": {"city": "北京", "origin": "北京站", "start_date": "2027-05-01"},
        **overrides,
    }


def run(account, body=None):
    response = account.post("/api/v1/tasks", json=body or request())
    assert response.status_code == 202, response.text
    task = response.json()
    execute(task["id"])
    return account.get("/api/v1/tasks/" + task["id"]).json()


def test_unauthenticated_cannot_read(client):
    assert client.get("/api/v1/trips").status_code == 401


def test_csrf(account):
    token = account.headers.pop("X-CSRF-Token")
    assert account.post("/api/v1/tasks", json=request()).status_code == 403
    account.headers["X-CSRF-Token"] = token


def test_fixture_full_chain_and_replay(account):
    task = run(account)
    assert task["status"] == "completed", task
    trip = account.get("/api/v1/trips/" + task["trip_id"]).json()
    assert trip["version"] == 1
    assert trip["plan"]["fixture"] is True
    execute(task["id"])
    assert account.get("/api/v1/trips/" + trip["id"]).json()["version"] == 1


def test_idempotency_and_parameter_conflict(account):
    body = request()
    a = account.post("/api/v1/tasks", json=body)
    b = account.post("/api/v1/tasks", json=body)
    assert a.json()["id"] == b.json()["id"]
    body["message"] = "changed"
    assert account.post("/api/v1/tasks", json=body).status_code == 409


def test_interrupt_resume_persisted(account):
    body = request(requirements={"city": "北京", "days": 1})
    task = run(account, body)
    assert task["status"] == "waiting_input", task
    response = account.post(
        f"/api/v1/tasks/{task['id']}/resume",
        json={"requirements": {"city": "北京", "origin": "北京站", "start_date": "2027-05-01", "days": 1}},
    )
    assert response.status_code == 202, response.text
    execute(task["id"])
    assert account.get("/api/v1/tasks/" + task["id"]).json()["status"] == "completed"


def test_cancel_prevents_write(account):
    response = account.post("/api/v1/tasks", json=request()).json()
    account.post("/api/v1/tasks/" + response["id"] + "/cancel")
    execute(response["id"])
    assert account.get("/api/v1/trips/" + response["trip_id"]).json()["version"] == 0


def test_version_conflict_does_not_override(account):
    task = run(account)
    trip = account.get("/api/v1/trips/" + task["trip_id"]).json()
    lock = trip["plan"]["days"][0]["stops"][0]["id"]
    pending = account.post("/api/v1/tasks", json=request(trip_id=trip["id"], base_version=1)).json()
    update = account.put("/api/v1/trips/" + trip["id"] + "/locks", json={"version": 1, "locked_ids": [lock]})
    assert update.status_code == 200, update.text
    execute(pending["id"])
    assert account.get("/api/v1/tasks/" + pending["id"]).json()["status"] == "conflict"
    assert account.get("/api/v1/trips/" + trip["id"]).json()["version"] == 2


def test_locked_place_survives_modification(account):
    task = run(account)
    trip = account.get("/api/v1/trips/" + task["trip_id"]).json()
    lock = trip["plan"]["days"][0]["stops"][0]["id"]
    account.put("/api/v1/trips/" + trip["id"] + "/locks", json={"version": 1, "locked_ids": [lock]})
    task2 = run(
        account,
        request(
            trip_id=trip["id"],
            base_version=2,
            requirements={
                "city": "北京",
                "origin": "北京站",
                "start_date": "2027-05-01",
                "interests": "新的偏好",
            },
        ),
    )
    assert task2["status"] == "completed", task2
    new = account.get("/api/v1/trips/" + trip["id"]).json()
    assert lock in [s["id"] for d in new["plan"]["days"] for s in d["stops"]]


def test_share_revoke_and_no_auth_write(account):
    task = run(account)
    share = account.post("/api/v1/trips/" + task["trip_id"] + "/shares").json()
    assert account.get(share["path"]).status_code == 200
    assert account.delete("/api/v1/shares/" + share["id"]).status_code == 200
    assert account.get(share["path"]).status_code == 404


def test_exports_are_real_pdf_and_text(account):
    task = run(account)
    pdf = account.get("/api/v1/trips/" + task["trip_id"] + "/export/pdf")
    assert pdf.content.startswith(b"%PDF")
    assert "合成" in account.get("/api/v1/trips/" + task["trip_id"] + "/export/md").text


def test_cross_user_access_denied(account, client):
    task = run(account)
    other = client.post(
        "/api/v1/auth/register",
        json={"name": "other-" + uuid.uuid4().hex[:12], "password": "test-password-123"},
    ).json()
    client.headers["X-CSRF-Token"] = other["csrf"]
    assert client.get("/api/v1/trips/" + task["trip_id"]).status_code == 404
    assert client.get("/api/v1/tasks/" + task["id"]).status_code == 404


def test_upload_and_wrong_format(account):
    assert account.post("/api/v1/documents", files={"file": ("x.exe", b"bad")}).status_code == 415
    assert account.post("/api/v1/documents", files={"file": ("empty.txt", b"")}).status_code == 413
    result = account.post("/api/v1/documents", files={"file": ("../../guide.txt", "合成攻略资料".encode())})
    assert result.status_code == 202
    assert account.get("/api/v1/documents").json()[0]["name"] == "guide.txt"


def test_missing_credentials_is_not_fixture_fallback(account):
    if settings.amap_key:
        return
    task = run(account, request(fixture=False))
    assert task["status"] == "awaiting_credentials", task
    assert account.get("/api/v1/trips/" + task["trip_id"]).json()["version"] == 0
