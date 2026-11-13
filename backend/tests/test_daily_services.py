import copy
from sqlalchemy import select
from travel_agent.db import Base, engine, Session, User, Trip, TripMember
from travel_agent.schemas import Requirements
from travel_agent.planning import build_plan
from travel_agent.providers import fixtures
from travel_agent.daily_services import daily_details
from fastapi.testclient import TestClient
from travel_agent.api import app
import uuid


def setup_module():
    Base.metadata.create_all(engine)


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


def test_daily_plan_contains_concrete_meals_hotel_and_every_leg():
    details = daily_details(plan(), 1, "public_transit")
    assert [m["slot"] for m in details["meals"]] == ["breakfast", "lunch", "dinner"]
    assert all(m["place"]["source"]["synthetic"] for m in details["meals"])
    assert details["hotel"]["name"].startswith("演示·")
    assert details["stay"] == {
        "checkin": "2027-05-01",
        "checkout": "2027-05-03",
        "nights": 2,
        "people": 1,
        "selected": False,
    }
    assert len(details["legs"]) == len(details["timeline"]) - 1
    assert details["timeline"][0]["place"]["name"] == "北京站"
    assert details["timeline"][-1]["kind"] == "hotel"
    assert all(l["instructions"] and l["from_name"] and l["to_name"] for l in details["legs"])
    assert details["meals"][1]["planned_start"] >= "12:00"


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
    assert any(l["to_id"] == lunch["id"] for l in updated["legs"])
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


def test_real_provider_failure_does_not_create_meals_or_claim_routes(monkeypatch):
    from travel_agent.providers import amap

    p = plan()
    p["fixture"] = False

    def fail(*args, **kwargs):
        raise RuntimeError("provider unavailable")

    monkeypatch.setattr(amap, "search_nearby", fail)
    monkeypatch.setattr(amap, "route_between", fail)
    monkeypatch.setattr(amap, "resolve_origin", fail)
    details = daily_details(p, 1, "public_transit")
    assert all(m["place"] is None for m in details["meals"])
    assert details["hotel"] is None
    assert details["warnings"]
    assert any(l.get("error") for l in details["legs"])
    assert details["timeline"][-1]["timing_verified"] is False


def test_explicit_no_hotel_and_single_day_do_not_invent_stay():
    p = plan()
    p["requirements"]["needs_accommodation"] = False
    assert daily_details(p, 1, "walk")["hotel"] is None


def test_transit_instructions_include_boarding_and_alighting(monkeypatch):
    from travel_agent.providers import amap

    monkeypatch.setattr(
        amap,
        "request",
        lambda *a, **kw: {
            "retrieved_at": "2026-11-13T00:00:00Z",
            "data": {
                "route": {
                    "transits": [
                        {
                            "duration": "1800",
                            "distance": "6000",
                            "walking_distance": "400",
                            "cost": "4",
                            "segments": [
                                {
                                    "walking": {
                                        "steps": [
                                            {
                                                "instruction": "步行至车站",
                                                "polyline": "116.4,39.9;116.41,39.91",
                                            }
                                        ]
                                    },
                                    "bus": {
                                        "buslines": [
                                            {
                                                "name": "地铁8号线",
                                                "departure_stop": {"name": "什刹海"},
                                                "arrival_stop": {"name": "王府井"},
                                                "via_num": "3",
                                                "start_time": "0500",
                                                "end_time": "2300",
                                                "polyline": "116.41,39.91;116.42,39.92",
                                            }
                                        ]
                                    },
                                }
                            ],
                        }
                    ]
                }
            },
        },
    )
    route = amap.route_between(
        {"id": "a", "name": "A", "lon": 116.4, "lat": 39.9},
        {"id": "b", "name": "B", "lon": 116.42, "lat": 39.92},
        "public_transit",
        "北京",
    )
    assert "什刹海上车" in route["instructions"][1]
    assert "王府井下车" in route["instructions"][1]
    assert route["transit_segments"][0]["via_stops"] == 3
    assert route["minutes"] == 30
    assert route["cost_cny"] == 4


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
