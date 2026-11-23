from travel_agent.daily_services import daily_details
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
    assert all(leg["instructions"] and leg["from_name"] and leg["to_name"] for leg in details["legs"])
    assert details["meals"][1]["planned_start"] >= "12:00"


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
    assert any(leg.get("error") for leg in details["legs"])
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
