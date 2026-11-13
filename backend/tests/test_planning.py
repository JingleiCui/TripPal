from datetime import date
import pytest
from travel_agent.schemas import Requirements
from travel_agent.planning import build_plan, validate_selection, plan_diff
from travel_agent.providers import fixtures
from travel_agent.knowledge import chunks, rrf, parse_file
from travel_agent.security import password_hash, password_valid


def req(**kw):
    return Requirements(start_date=date(2027, 5, 1), origin="北京站", days=1, **kw)


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
