import copy
from sqlalchemy import select
from travel_agent.budgeting import calculate_budget, reference_meal_price
from travel_agent.db import Base, engine, Session, User, Trip, DailyDetailSnapshot


def setup_module():
    Base.metadata.create_all(engine)


def case():
    plan = {
        "requirements": {
            "city": "北京",
            "days": 3,
            "people": 2,
            "budget": 3000,
            "origin": "北京站",
            "transport": "walk",
            "needs_accommodation": True,
        },
        "days": [],
        "budget_settings": {"rooms": 2, "overrides": {}},
    }
    snapshots = []
    for n in range(1, 4):
        stop = {"id": f"poi:{n}", "name": "公园", "price_cny": 15, "source": {"provider": "高德地图"}}
        plan["days"].append({"day": n, "date": f"2027-05-0{n}", "city": "北京", "stops": [stop]})
        meals = []
        for slot, price in [("breakfast", 20), ("lunch", 35), ("dinner", 40)]:
            meals.append(
                {
                    "slot": slot,
                    "place": {
                        "id": slot,
                        "name": slot,
                        "price_text": str(price),
                        "source": {"provider": "高德地图"},
                    },
                }
            )
        snapshots.append(
            {
                "day": n,
                "date": f"2027-05-0{n}",
                "mode": "walk",
                "timeline": [
                    {"kind": "origin", "place": {"id": "origin", "name": "北京站"}},
                    {"kind": "place", "place": stop},
                ],
                "meals": meals,
                "hotel": {"id": "hotel", "name": "旅居酒店", "price_text": "2晚共￥11XX"},
                "stay": {"people": 2},
                "legs": [
                    {
                        "from_id": "a",
                        "to_id": "b",
                        "from_name": "A",
                        "to_name": "B",
                        "mode": "walk",
                        "cost_cny": None,
                        "source": {"provider": "高德地图"},
                    }
                ],
            }
        )
        if n < 3:
            plan["budget_settings"]["overrides"][f"hotel:{n}"] = {
                "unit_price_cny": "500",
                "unit": "per_room_night",
                "confidence": "confirmed",
                "fingerprint": "hotel",
            }
    return plan, snapshots


def test_full_ledger_multiplies_people_and_rooms_and_does_not_bill_checkout_night():
    plan, snapshots = case()
    ledger = calculate_budget(plan, snapshots)
    # meals: (20+35+40)*2*3=570; tickets:15*2*3=90; hotel:500*2 rooms*2 nights=2000.
    assert ledger["trip"]["priced_subtotal_cny"] == 2660
    assert (
        sum(r["subtotal_cny"] or 0 for d in ledger["days"] for r in d["rows"] if r["category"] == "hotel")
        == 2000
    )
    assert not any(r["category"] == "hotel" for r in ledger["days"][2]["rows"])
    assert ledger["trip"]["status"] == "incomplete"  # return transport is not silently free
    assert ledger["trip"]["remaining_cny"] is None
    plan["budget_settings"]["overrides"]["return-travel"] = {
        "unit_price_cny": "0",
        "unit": "group",
        "confidence": "confirmed",
        "fingerprint": "",
        "note": "同城步行返程，无额外费用",
    }
    complete = calculate_budget(plan, snapshots)
    assert complete["trip"]["status"] == "within_estimate"
    assert complete["trip"]["remaining_cny"] == 340


def test_known_reference_cost_can_already_exceed_budget_while_other_prices_are_missing():
    plan, snapshots = case()
    plan["requirements"]["budget"] = 1000
    result = calculate_budget(plan, snapshots)
    assert result["trip"]["status"] == "over_budget"
    assert result["trip"]["overrun_cny"] == 1660
    assert result["trip"]["unpriced_count"] > 0
    assert result["trip"]["remaining_cny"] is None


def test_masked_or_unavailable_hotel_and_food_prices_are_never_zero():
    plan, snapshots = case()
    plan["budget_settings"]["overrides"] = {}
    snapshots[0]["meals"][0]["place"]["price_text"] = "￥2X"
    result = calculate_budget(plan, snapshots)
    assert result["days"][0]["rows"][0]["subtotal_cny"] is None
    assert all(
        r["subtotal_cny"] is None for d in result["days"] for r in d["rows"] if r["category"] == "hotel"
    )
    assert reference_meal_price({"price_text": "￥11XX", "source": {"provider": "高德地图"}}) is None
    assert result["trip"]["status"] == "incomplete"


def test_changing_restaurant_invalidates_its_old_confirmed_price():
    plan, snapshots = case()
    plan["budget_settings"]["overrides"]["meal:1:lunch"] = {
        "unit_price_cny": "1",
        "unit": "per_person",
        "confidence": "confirmed",
        "fingerprint": "different-restaurant",
    }
    result = calculate_budget(plan, snapshots)
    lunch = next(r for r in result["days"][0]["rows"] if r["key"] == "meal:1:lunch")
    assert lunch["subtotal_cny"] == 70
    assert lunch["confidence"] == "reference"


def test_budget_api_revision_scope_and_snapshot_carryover(account):
    plan, snapshots = case()
    with Session.begin() as db:
        user = db.scalar(select(User).where(User.name == account.get("/api/v1/auth/me").json()["name"]))
        trip = Trip(owner=user.id, title="预算验收", version=1, plan=plan)
        db.add(trip)
        db.flush()
        ident = trip.id
        for data in snapshots:
            db.add(
                DailyDetailSnapshot(
                    trip_id=ident, version=1, day=data["day"], mode="walk", data={**data, "version": 1}
                )
            )
    current = account.get(f"/api/v1/trips/{ident}/budget").json()
    assert current["trip"]["priced_subtotal_cny"] == 2660
    body = {"base_version": 1, "total_limit_cny": 2500, "rooms": 2, "daily_limits": {"1": 1000}}
    updated = account.put(f"/api/v1/trips/{ident}/budget", json=body)
    assert updated.status_code == 200, updated.text
    assert updated.json()["trip"]["status"] == "over_budget"
    assert updated.json()["version"] == 2
    assert account.put(f"/api/v1/trips/{ident}/budget", json=body).status_code == 409
    with Session() as db:
        assert (
            len(
                db.scalars(
                    select(DailyDetailSnapshot).where(
                        DailyDetailSnapshot.trip_id == ident, DailyDetailSnapshot.version == 2
                    )
                ).all()
            )
            == 3
        )
    assert (
        account.put(
            f"/api/v1/trips/{ident}/budget", json={**body, "base_version": 2, "daily_limits": {"9": 100}}
        ).status_code
        == 422
    )


def test_bus_fares_multiply_people_but_vehicle_fees_do_not():
    plan, snapshots = case()
    plan["days"][0]["transport_mode"] = "public_transit"
    snapshots[0]["mode"] = "public_transit"
    snapshots[0]["legs"][0].update(mode="public_transit", cost_cny=4)
    rows = calculate_budget(plan, snapshots)["days"][0]["rows"]
    fare = next(r for r in rows if r["key"].startswith("route:"))
    assert fare["quantity"] == 2 and fare["subtotal_cny"] == 8
    plan["days"][0]["transport_mode"] = "drive"
    snapshots[0]["mode"] = "drive"
    snapshots[0]["legs"][0].update(mode="drive", cost_cny=30)
    rows = calculate_budget(plan, snapshots)["days"][0]["rows"]
    fare = next(r for r in rows if r["key"].startswith("route:"))
    assert fare["quantity"] == 1 and fare["subtotal_cny"] == 30
    assert next(r for r in rows if r["key"].startswith("driving-extras:"))["subtotal_cny"] is None


def test_replanning_preserves_checked_prices_but_date_change_requires_review(account):
    import uuid
    from decimal import Decimal
    from langgraph.checkpoint.mysql.pymysql import PyMySQLSaver
    from travel_agent.config import settings
    from travel_agent.worker import execute

    with PyMySQLSaver.from_conn_string(settings.checkpoint_url) as saver:
        saver.setup()
    req = {
        "city": "北京",
        "days": 3,
        "people": 1,
        "origin": "北京站",
        "start_date": "2027-05-01",
        "budget": 5000,
    }

    def run_task(trip_id=None, base_version=0, requirements=None):
        response = account.post(
            "/api/v1/tasks",
            json={
                "request_key": uuid.uuid4().hex,
                "message": "请保持行程条件安排旅行",
                "fixture": True,
                "trip_id": trip_id,
                "base_version": base_version,
                "requirements": requirements or req,
            },
        )
        assert response.status_code == 202, response.text
        task = response.json()
        execute(task["id"])
        task = account.get("/api/v1/tasks/" + task["id"]).json()
        assert task["status"] == "completed", task
        return account.get("/api/v1/trips/" + task["trip_id"]).json()

    trip = run_task()
    ident = trip["id"]
    account.get(f"/api/v1/trips/{ident}/daily-details?day=1")
    ledger = account.get(f"/api/v1/trips/{ident}/budget").json()
    row = next(r for r in ledger["days"][0]["rows"] if r["key"] == "meal:1:breakfast")
    response = account.put(
        f"/api/v1/trips/{ident}/budget",
        json={
            "base_version": 1,
            "total_limit_cny": 5000,
            "rooms": 1,
            "expense": {
                "key": row["key"],
                "unit_price_cny": 80,
                "unit": "per_person",
                "confidence": "estimated",
                "fingerprint": row["fingerprint"],
            },
        },
    )
    assert response.status_code == 200, response.text
    trip = run_task(ident, 2)
    assert Decimal(trip["plan"]["budget_settings"]["overrides"]["meal:1:breakfast"]["unit_price_cny"]) == 80
    updated = run_task(ident, trip["version"], {**req, "start_date": "2027-05-10"})
    assert updated["plan"]["budget_settings"]["overrides"] == {}
    assert any("日期或人数" in w for w in updated["plan"]["warnings"])
