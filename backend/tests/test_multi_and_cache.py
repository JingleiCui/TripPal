import uuid
import pytest
from travel_agent.providers import fixtures
from travel_agent.planning import build_plan, validate_selection
from travel_agent.conversation import extract, to_requirements
from travel_agent.research_cache import store, lookup, scope_for, semantic_eligible


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


@pytest.mark.timeout(120)
def test_real_es_semantic_cache_scope_and_freshness():
    owner = "cache-test-" + uuid.uuid4().hex
    result = fixtures.places()[:1]
    store(owner, "北京", "博物馆", {}, result)
    hit = lookup(owner, "北京", "博物馆", {})
    assert hit and hit["results"][0]["id"] == "fixture:0"
    assert lookup("other-owner", "北京", "博物馆", {}) is None
    assert lookup(owner, "上海", "博物馆", {}) is None
    assert lookup(owner, "北京", "博物馆", {"indoor_only": True}) is None
    assert not semantic_eligible("不要博物馆")
    assert not semantic_eligible("预算200元")
    assert scope_for(owner, "北京", {}) != scope_for(owner, "北京", {"excluded_ids": ["a"]})
