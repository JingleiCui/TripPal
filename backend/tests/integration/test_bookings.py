import io
import json
import uuid
import zipfile

from fastapi.testclient import TestClient
from sqlalchemy import select
from travel_agent.api import app
from travel_agent.db import Session, Trip, TripMember, User


def create_trip(account):
    with Session.begin() as db:
        owner = db.scalar(select(User).where(User.name == account.get("/api/v1/auth/me").json()["name"]))
        row = Trip(owner=owner.id, title="订单测试行程")
        db.add(row)
        db.flush()
        return row.id


def payload(**overrides):
    return {
        "kind": "train",
        "title": "北京南到上海虹桥",
        "start": "2027-05-01T09:00:00",
        "end": "2027-05-01T14:00:00",
        "reference": "私密确认号",
        **overrides,
    }


def test_bookings_roundtrip_and_private_export(account):
    trip_id = create_trip(account)
    document = account.post(
        "/api/v1/documents", files={"file": ("订单.txt", "车次 G101 已确认".encode(), "text/plain")}
    )
    assert document.status_code == 202
    created = account.post(
        f"/api/v1/trips/{trip_id}/bookings", json=payload(document_id=document.json()["id"])
    )
    assert created.status_code == 201, created.text
    ident = created.json()["id"]
    assert account.get(f"/api/v1/trips/{trip_id}/bookings").json()[0]["reference"] == "私密确认号"
    assert account.put("/api/v1/bookings/" + ident, json=payload(title="改签后的车次")).status_code == 200
    exported = account.get("/api/v1/privacy/export")
    with zipfile.ZipFile(io.BytesIO(exported.content)) as archive:
        data = json.loads(archive.read("personal-data.json"))
    assert data["bookings"][0]["title"] == "改签后的车次"
    assert account.delete("/api/v1/bookings/" + ident).status_code == 200
    assert account.get(f"/api/v1/trips/{trip_id}/bookings").json() == []


def test_booking_validation_and_document_ownership(account):
    ident = create_trip(account)
    for body in [
        payload(end="2027-04-01T08:00:00"),
        payload(title=" "),
        payload(start="2027-05-01T09:00:00Z"),
        payload(kind="payment"),
    ]:
        assert account.post(f"/api/v1/trips/{ident}/bookings", json=body).status_code == 422
    assert (
        account.post(f"/api/v1/trips/{ident}/bookings", json=payload(document_id="missing")).status_code
        == 404
    )
    other = TestClient(app)
    auth = other.post(
        "/api/v1/auth/register",
        json={"name": "booking-" + uuid.uuid4().hex[:12], "password": "test-password-123"},
    ).json()
    other.headers["X-CSRF-Token"] = auth["csrf"]
    doc = other.post("/api/v1/documents", files={"file": ("私密.txt", b"private", "text/plain")}).json()
    assert (
        account.post(f"/api/v1/trips/{ident}/bookings", json=payload(document_id=doc["id"])).status_code
        == 404
    )
    assert other.get(f"/api/v1/trips/{ident}/bookings").status_code == 404
    created = account.post(f"/api/v1/trips/{ident}/bookings", json=payload()).json()
    assert other.delete("/api/v1/bookings/" + created["id"]).status_code == 404
    # Even collaborators cannot see a creator's confirmation codes or documents.
    with Session.begin() as db:
        user = db.scalar(select(User).where(User.name == auth["name"]))
        db.add(TripMember(trip_id=ident, user_id=user.id, role="editor"))
    assert other.get(f"/api/v1/trips/{ident}/bookings").status_code == 403
    assert other.post(f"/api/v1/trips/{ident}/bookings", json=payload()).status_code == 403
