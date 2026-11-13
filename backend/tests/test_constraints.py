from datetime import date
import pytest
from travel_agent.planning import build_plan, validate_selection
from travel_agent.providers import fixtures
from travel_agent.schemas import Requirements


def test_locked_date_cannot_move():
    req = Requirements(days=1, start_date=date(2027, 5, 1), origin="北京站")
    old = build_plan([["fixture:0"]], fixtures.places(), req, fixtures.route)
    req.start_date = date(2027, 5, 2)
    req.locked_ids = ["fixture:0"]
    with pytest.raises(ValueError, match="日期"):
        validate_selection([["fixture:0"]], fixtures.places(), req, old)


def test_arrival_route_is_in_schedule_and_cost():
    req = Requirements(days=1, start_date=date(2027, 5, 1), origin="北京站")
    origin = {"id": "origin:test", "name": "测试起点", "lon": 116.4, "lat": 39.9}
    plan = build_plan([["fixture:0"]], fixtures.places(), req, fixtures.route, origin=origin)
    assert plan["days"][0]["stops"][0]["planned_start"] == "09:40"
    assert plan["budget"]["known_subtotal_cny"] == 4
    assert plan["days"][0]["arrival_route"]["from_id"] == "origin:test"
