"""Browsing uses upstream pages, with finite bounds and saved-candidate integrity."""

from travel_agent.providers import amap


def poi(ident, *, company=False):
    return {
        "id": str(ident),
        "name": "餐饮管理公司" if company else f"餐厅 {ident}",
        "location": "116.407,39.908",
        "type": "餐饮服务;中餐厅",
        "typecode": "050100",
    }


def test_food_filtering_does_not_prematurely_end_raw_pages(monkeypatch):
    calls = []

    def fake_request(path, params, ttl):
        calls.append(params.copy())
        return {
            "data": {"count": "40", "pois": [poi(i, company=i < 19) for i in range(20)]},
            "retrieved_at": "2026-11-17T00:00:00Z",
        }

    monkeypatch.setattr(amap, "request", fake_request)
    page = amap.search_places_page("北京", "餐厅", "050000", page=1, page_size=20)
    assert len(page["items"]) == 1
    assert page["next_page"] == 2
    assert calls[0]["offset"] == 20 and calls[0]["page"] == 1


def test_upstream_end_cap_and_legacy_agent_budget(monkeypatch):
    calls = []

    def fake_request(path, params, ttl):
        calls.append(params.copy())
        start = (params["page"] - 1) * params["offset"]
        return {
            "data": {"count": "1000", "pois": [poi(i) for i in range(start, start + params["offset"])]},
            "retrieved_at": "2026-11-17T00:00:00Z",
        }

    monkeypatch.setattr(amap, "request", fake_request)
    assert len(amap.search_places("北京", "餐厅")) == 8
    assert calls[-1]["offset"] == 8
    last = amap.search_places_page("北京", "餐厅", page=9, page_size=23)
    assert len(last["items"]) == 16
    assert last["next_page"] is None and last["end_reason"] == "provider_limit"
