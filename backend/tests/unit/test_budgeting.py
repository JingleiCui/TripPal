from travel_agent.budgeting import calculate_budget, reference_meal_price


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


def test_meituan_reference_quotes_fill_only_matching_rows():
    plan, snapshots = case()
    plan["budget_settings"]["overrides"] = {}
    for snapshot in snapshots:
        for meal in snapshot["meals"]:
            meal["place"]["price_text"] = "未查到"
    for day in plan["days"]:
        for stop in day["stops"]:
            stop["price_cny"] = None
    quotes = [
        {"day": 1, "place_id": "hotel", "kind": "hotel", "price_cny": 600,
         "price_text": "￥600起/晚", "price_basis": "起价"},
        {"day": 1, "place_id": "breakfast", "kind": "food", "price_cny": 25,
         "price_text": "人均￥25", "price_basis": "人均"},
        {"day": 1, "place_id": "poi:1", "kind": "ticket", "price_cny": 80,
         "price_text": "￥80起", "price_basis": "起价"},
        {"day": 2, "place_id": "hotel", "kind": "hotel", "price_cny": 999,
         "price_text": "￥999起/晚", "price_basis": "起价"},
    ]
    result = calculate_budget(plan, snapshots, quotes)
    rows = result["days"][0]["rows"]
    hotel = next(r for r in rows if r["key"] == "hotel:1")
    breakfast = next(r for r in rows if r["key"] == "meal:1:breakfast")
    ticket = next(r for r in rows if r["key"] == "ticket:1:poi:1")
    assert (hotel["subtotal_cny"], hotel["source"], hotel["confidence"]) == (1200, "美团酒旅", "reference")
    assert (breakfast["subtotal_cny"], breakfast["source"]) == (50, "美团酒旅")
    assert (ticket["subtotal_cny"], ticket["source"]) == (160, "美团酒旅")
    day2_hotel = next(r for r in result["days"][1]["rows"] if r["key"] == "hotel:2")
    day3_hotel = next(r for r in result["days"][2]["rows"] if r["key"] == "hotel:3") if any(
        r["key"] == "hotel:3" for r in result["days"][2]["rows"]
    ) else None
    assert day2_hotel["subtotal_cny"] == 1998
    assert day3_hotel is None or day3_hotel["subtotal_cny"] is None


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
