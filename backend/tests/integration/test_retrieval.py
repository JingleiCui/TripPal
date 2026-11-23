import uuid

import pytest
from travel_agent.providers import fixtures
from travel_agent.research_cache import lookup, scope_for, semantic_eligible, store


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
