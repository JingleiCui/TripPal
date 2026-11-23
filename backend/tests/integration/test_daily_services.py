import uuid

from fastapi.testclient import TestClient
from sqlalchemy import select
from travel_agent.api import app
from travel_agent.db import Session, Trip, TripMember, User
from travel_agent.planning import build_plan
from travel_agent.providers import fixtures
from travel_agent.schemas import Requirements


def plan():
    req = Requirements(city="北京", days=3, origin="北京站", start_date="2027-05-01")
    return build_plan(
        [["fixture:0", "fixture:1"], ["fixture:2", "fixture:3"], ["fixture:4", "fixture:5"]],
        fixtures.places(),
        req,
        fixtures.route,
        fixture=True,
    )


def trip_for(account):
    with Session.begin() as db:
        owner = db.scalar(select(User).where(User.name == account.get("/api/v1/auth/me").json()["name"]))
        trip = Trip(owner=owner.id, title="吃住行验证", plan=plan(), version=1)
        db.add(trip)
        db.flush()
        return trip.id


def test_daily_services_choices_are_revisioned_and_scoped(account):
    ident = trip_for(account)
    response = account.get(f"/api/v1/trips/{ident}/daily-details?day=1")
    assert response.status_code == 200, response.text
    result = response.json()
    lunch = next(m for m in result["meals"] if m["slot"] == "lunch")["alternatives"][1]
    body = {"day": 1, "base_version": 1, "slot": "lunch", "place_id": lunch["id"], "mode": "public_transit"}
    assert (
        account.post(
            f"/api/v1/trips/{ident}/service-choice", json={**body, "place_id": "invented"}
        ).status_code
        == 422
    )
    assert account.post(f"/api/v1/trips/{ident}/service-choice", json=body).json()["version"] == 2
    updated = account.get(f"/api/v1/trips/{ident}/daily-details?day=1").json()
    assert updated["meals"][1]["place"]["id"] == lunch["id"]
    assert updated["meals"][1]["user_selected"] is True
    assert any(leg["to_id"] == lunch["id"] for leg in updated["legs"])
    assert account.post(f"/api/v1/trips/{ident}/service-choice", json=body).status_code == 409
    transport = {"day": 1, "base_version": 2, "slot": "transport", "mode": "walk"}
    assert account.post(f"/api/v1/trips/{ident}/service-choice", json=transport).status_code == 200
    assert account.get(f"/api/v1/trips/{ident}/daily-details?day=1").json()["mode"] == "walk"
    assert account.get(f"/api/v1/trips/{ident}/daily-details?day=14").status_code == 404
    other = TestClient(app)
    auth = other.post(
        "/api/v1/auth/register",
        json={"name": "daily-" + uuid.uuid4().hex[:12], "password": "test-password-123"},
    ).json()
    other.headers["X-CSRF-Token"] = auth["csrf"]
    assert other.get(f"/api/v1/trips/{ident}/daily-details?day=1").status_code == 404
    with Session.begin() as db:
        user = db.scalar(select(User).where(User.name == auth["name"]))
        db.add(TripMember(trip_id=ident, user_id=user.id, role="viewer"))
    assert other.get(f"/api/v1/trips/{ident}/daily-details?day=1").status_code == 200
    assert (
        other.post(f"/api/v1/trips/{ident}/service-choice", json={**transport, "base_version": 3}).status_code
        == 403
    )


def test_intercity_query_is_validated_and_never_fabricates_schedule(account, monkeypatch):
    ident = trip_for(account)
    body = {
        "origin": "上海虹桥",
        "destination": "北京南",
        "departure_date": "2027-05-01",
        "kind": "train",
        "people": 2,
    }
    result = account.post(f"/api/v1/trips/{ident}/intercity-options", json=body)
    assert result.status_code == 200
    assert "未提供真实车次" in result.json()["raw_text"]
    assert (
        account.post(
            f"/api/v1/trips/{ident}/intercity-options", json={**body, "departure_date": "2027-02-30"}
        ).status_code
        == 422
    )
    assert (
        account.post(f"/api/v1/trips/{ident}/intercity-options", json={**body, "origin": " "}).status_code
        == 422
    )


def test_market_branch_mismatch_is_not_presented_as_same_merchant(account, monkeypatch):
    from travel_agent import services_api

    ident = trip_for(account)
    place = {
        "id": "amap:restaurant",
        "name": "老北京炸酱面(景山西街店)",
        "address": "景山西街",
        "source": {"provider": "高德地图"},
    }
    monkeypatch.setattr(
        services_api,
        "details",
        lambda *a, **kw: {
            "fixture": False,
            "city": "北京",
            "version": 1,
            "hotels": [],
            "meals": [{"alternatives": [place]}],
            "stay": {"checkin": "2027-05-01", "checkout": "2027-05-03", "people": 2},
        },
    )
    monkeypatch.setattr(
        services_api.meituan,
        "query",
        lambda *a, **kw: {"raw_text": "老北京炸酱面（景山前街店）参考人均27元", "items": []},
    )
    result = account.post(
        f"/api/v1/trips/{ident}/market-details",
        json={"day": 1, "place_id": "amap:restaurant", "kind": "food"},
    )
    assert result.status_code == 200
    assert "未能精确匹配" in result.json()["venue_warning"]
