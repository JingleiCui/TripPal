from datetime import date

import pytest
from travel_agent.conversation import extract, to_requirements
from travel_agent.knowledge import chunks, parse_file, rrf
from travel_agent.planning import build_plan, plan_diff, validate_selection, weekday_opening_note
from travel_agent.providers import fixtures
from travel_agent.schemas import Requirements
from travel_agent.security import password_hash, password_valid


def req(**kw):
    return Requirements(start_date=date(2027, 5, 1), origin="北京站", days=1, **kw)


def test_weekday_opening_rules_are_read_without_guessing():
    assert weekday_opening_note("每周一闭馆", 0)
    assert weekday_opening_note("周一、周三不开放", 2)
    assert weekday_opening_note("周一至周五 09:00-17:00", 5)
    assert weekday_opening_note("周末闭馆", 6)
    assert weekday_opening_note("工作日营业", 5)
    assert weekday_opening_note("每天 09:00-17:00", 0) is None
    assert weekday_opening_note("时间待核实", 0) is None


def test_plan_warns_when_selected_date_matches_weekday_closure():
    places = fixtures.places()
    places[0]["opening_text"] = "每周一闭馆"
    plan = build_plan(
        [["fixture:0"]],
        places,
        Requirements(start_date=date(2027, 5, 3), days=1, city="北京"),
        fixtures.route,
    )
    assert any("闭馆" in warning for warning in plan["warnings"])
    assert plan["days"][0]["stops"][0]["weekday_opening_note"]


def test_no_invented_places():
    with pytest.raises(ValueError, match="无来源"):
        validate_selection([["invented"]], fixtures.places(), req())


def test_no_duplicate_places():
    with pytest.raises(ValueError, match="重复"):
        validate_selection([["fixture:0", "fixture:0"]], fixtures.places(), req())


def test_locked_is_hard_constraint():
    with pytest.raises(ValueError, match="锁定"):
        validate_selection([["fixture:0"]], fixtures.places(), req(locked_ids=["fixture:1"]))


def test_indoor_unknown_is_not_true():
    p = fixtures.places()
    p[0]["indoor"] = None
    with pytest.raises(ValueError, match="室内"):
        validate_selection([["fixture:0"]], p, req(indoor_only=True))


def test_route_failure_retains_uncertainty():
    def failed(*_):
        raise TimeoutError()

    plan = build_plan([["fixture:0", "fixture:1"]], fixtures.places(), req(), failed)
    assert plan["verification"] == "needs_review"
    assert plan["days"][0]["routes"][0]["minutes"] is None
    assert any("未核实" in w for w in plan["warnings"])


def test_unknown_cost_is_not_zero_total():
    p = fixtures.places()
    p[0]["price_cny"] = None
    plan = build_plan([["fixture:0"]], p, req(budget=1), fixtures.route)
    assert "门票费用" in plan["budget"]["unknown_items"]
    assert "不完整" in plan["budget"]["status"]


def test_route_budget_warning():
    plan = build_plan([["fixture:0", "fixture:1"]], fixtures.places(), req(budget=1), fixtures.route)
    assert any("超过总预算" in w for w in plan["warnings"])


def test_diff():
    assert plan_diff({"days": [{"stops": [{"id": "a"}]}]}, {"days": [{"stops": [{"id": "b"}]}]}) == {
        "added": ["b"],
        "removed": ["a"],
        "retained": [],
    }


def test_rrf_calculation():
    ranked = rrf([[{"_id": "a"}, {"_id": "b"}], [{"_id": "b"}]])
    assert ranked[0][0]["_id"] == "b"
    assert ranked[0][1] == pytest.approx(1 / 62 + 1 / 61)


def test_chunk_source_anchor_and_overlap():
    result = chunks([("第 2 页", "甲" * 600)])
    assert result[0]["anchor"] == "第 2 页"
    assert result[1]["offset"] == 370
    assert len(result[0]["text"]) == 450


def test_parse_invalid_format():
    with pytest.raises(ValueError):
        parse_file(b"abc", "payload.exe")


def test_password_not_recoverable():
    stored = password_hash("hello-password")
    assert password_valid("hello-password", stored)
    assert not password_valid("wrong-password", stored)


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


def test_multi_destination_extraction_and_city_validation():
    slots, _, _, _ = extract("北京两天，上海两天，直接规划", {}, fixture=True)
    req = to_requirements(slots)
    assert req.days == 4
    assert [s.city for s in req.city_stays] == ["北京", "上海"]
    places = fixtures.places("北京") + fixtures.places("上海")
    plan = build_plan(
        [["fixture:0"], ["fixture:1"], ["fixture:上海:0"], ["fixture:上海:1"]],
        places,
        req,
        fixtures.route,
        True,
    )
    assert [d["city"] for d in plan["days"]] == ["北京", "北京", "上海", "上海"]
    assert len(plan["transfers"]) == 1
    assert plan["transfers"][0]["status"] == "待核实"
    with pytest.raises(ValueError, match="指定的城市"):
        validate_selection([["fixture:上海:0"], [], [], []], places, req)
