import io
import json
import re
import uuid
import zipfile
from unittest.mock import patch

import httpx
from fastapi.testclient import TestClient
from sqlalchemy import select
from travel_agent.api import app
from travel_agent.config import settings
from travel_agent.db import AccountProfile, AuthToken, Document, LoginSession, Session, Task, Trip, User
from travel_agent.mailer import deliver_pending


def new_email_account():
    client = TestClient(app)
    name = "email-" + uuid.uuid4().hex[:12]
    email = name + "@example.com"
    result = client.post(
        "/api/v1/auth/register", json={"name": name, "email": email, "password": "test-password-123"}
    )
    assert result.status_code == 200, result.text
    client.headers["X-CSRF-Token"] = result.json()["csrf"]
    return client, name, email


def mail_token(email, subject):
    deliver_pending()
    messages = httpx.get("http://127.0.0.1:18026/api/v1/messages", timeout=5, trust_env=False).json()[
        "messages"
    ]
    matched = [
        m for m in messages if subject in m["Subject"] and any(to.get("Address") == email for to in m["To"])
    ]
    assert matched, "邮件没有实际进入本地 SMTP 收件箱"
    detail = httpx.get(
        "http://127.0.0.1:18026/api/v1/message/" + matched[0]["ID"], timeout=5, trust_env=False
    ).json()
    token = re.search(r"#token=([A-Za-z0-9_-]+)", detail["Text"])
    assert token
    return token.group(1)


def test_jwt_email_verification_and_single_use(account):
    client, name, email = new_email_account()
    token = client.cookies.get("travel_session")
    assert len(token.split(".")) == 3
    assert client.get("/api/v1/auth/me").json()["email_verified"] is False
    proof = mail_token(email, "验证邮箱")
    assert client.post("/api/v1/auth/verify-email", json={"token": proof}).status_code == 200
    assert client.get("/api/v1/auth/me").json()["email_verified"] is True
    assert client.post("/api/v1/auth/verify-email", json={"token": proof}).status_code == 400


def test_password_reset_invalidates_all_old_sessions(account):
    client, name, email = new_email_account()
    assert client.post("/api/v1/auth/forgot-password", json={"email": email}).status_code == 200
    token = mail_token(email, "重置密码")
    assert (
        client.post(
            "/api/v1/auth/reset-password", json={"token": token, "password": "new-test-password-456"}
        ).status_code
        == 200
    )
    assert client.get("/api/v1/auth/me").status_code == 401
    assert (
        client.post(
            "/api/v1/auth/reset-password", json={"token": token, "password": "other-test-password-456"}
        ).status_code
        == 400
    )
    assert (
        client.post("/api/v1/auth/login", json={"name": name, "password": "test-password-123"}).status_code
        == 401
    )
    assert (
        client.post(
            "/api/v1/auth/login", json={"name": name, "password": "new-test-password-456"}
        ).status_code
        == 200
    )


def test_export_and_account_deletion_cascade(account):
    conv = account.post("/api/v1/conversations", json={"fixture": True}).json()
    body = {"content": "北京两天，直接规划", "request_key": uuid.uuid4().hex, "version": 0}
    conv = account.post("/api/v1/conversations/" + conv["id"] + "/turns", json=body).json()
    from travel_agent.worker import execute

    execute(conv["state"]["task_id"])
    export = account.get("/api/v1/privacy/export")
    assert export.status_code == 200
    with zipfile.ZipFile(io.BytesIO(export.content)) as archive:
        data = json.loads(archive.read("personal-data.json"))
    assert data["conversations"] and data["trips"] and data["messages"]
    name = data["account"]["username"]
    assert "password" not in data["account"]
    with Session() as db:
        owner = db.scalar(select(User.id).where(User.name == name))
    assert (
        account.request(
            "DELETE", "/api/v1/privacy/account", json={"confirmation": name, "password": "wrong"}
        ).status_code
        == 403
    )
    result = account.request(
        "DELETE", "/api/v1/privacy/account", json={"confirmation": name, "password": "test-password-123"}
    )
    assert result.status_code == 200, result.text
    assert account.get("/api/v1/auth/me").status_code == 401
    with Session() as db:
        assert not db.get(User, owner)
        for model in [Trip, Task, Document, LoginSession, AccountProfile, AuthToken]:
            assert db.scalar(select(model).where(model.owner == owner)) is None
    assert account.get("/api/v1/conversations/" + conv["id"]).status_code == 401


def test_posthog_double_gate_is_a_hard_noop(account):
    with (
        patch("travel_agent.lifecycle_api.httpx.Client") as client,
        patch.object(settings, "posthog_key", ""),
    ):
        assert (
            account.post("/api/v1/privacy/analytics", json={"event": "plan_requested"}).json()["sent"]
            is False
        )
        assert not client.called
        account.put("/api/v1/privacy/consent", json={"analytics": True})
        assert (
            account.post("/api/v1/privacy/analytics", json={"event": "plan_requested"}).json()["sent"]
            is False
        )
        assert not client.called
    with (
        patch("travel_agent.lifecycle_api.httpx.Client") as client,
        patch.object(settings, "posthog_key", "test-project-key"),
    ):
        account.put("/api/v1/privacy/consent", json={"analytics": False})
        account.post("/api/v1/privacy/analytics", json={"event": "plan_requested"})
        assert not client.called
        account.put("/api/v1/privacy/consent", json={"analytics": True})
        client.return_value.__enter__.return_value.post.return_value.is_success = True
        assert (
            account.post("/api/v1/privacy/analytics", json={"event": "plan_requested"}).json()["sent"] is True
        )
        sent = client.return_value.__enter__.return_value.post.call_args.kwargs["json"]
        assert set(sent["properties"]) == {"distinct_id", "source"}
