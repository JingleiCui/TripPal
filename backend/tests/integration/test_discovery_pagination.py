"""Browsing uses upstream pages, with finite bounds and saved-candidate integrity."""

import uuid

import pytest
from travel_agent.providers import amap, meituan


@pytest.fixture
def hotel_trip(account):
    from travel_agent.worker import execute

    created = account.post(
        "/api/v1/tasks",
        json={
            "request_key": uuid.uuid4().hex,
            "fixture": True,
            "message": "分页验证",
            "requirements": {"city": "北京", "days": 2, "origin": "北京站", "start_date": "2027-05-01"},
        },
    ).json()
    execute(created["id"])
    return account.get("/api/v1/trips/" + created["trip_id"]).json()


def poi(ident, *, company=False):
    return {
        "id": str(ident),
        "name": "餐饮管理公司" if company else f"餐厅 {ident}",
        "location": "116.407,39.908",
        "type": "餐饮服务;中餐厅",
        "typecode": "050100",
    }


def test_fixture_pages_are_disjoint_finite_and_saveable(account):
    params = {"city": "北京", "fixture": True, "category": "stays"}
    first = account.get("/api/v1/explore", params=params).json()
    second = account.get("/api/v1/explore", params={**params, "page": first["next_page"]}).json()
    assert len(first["items"]) == 20
    assert len(second["items"]) == 16
    assert first["has_more"] is True
    assert second["next_page"] is None
    assert second["end_reason"] == "exhausted"
    ids = [item["id"] for item in first["items"] + second["items"]]
    assert len(set(ids)) == 36
    last = second["items"][-1]
    saved = account.post("/api/v1/saved-places", json={"place_id": last["id"]})
    assert saved.status_code == 201
    assert saved.json()["place"]["name"] == last["name"]
    assert account.get("/api/v1/explore", params={**params, "page": 3}).json()["items"] == []


@pytest.mark.parametrize("extra", [{"page": 0}, {"page_size": 26}, {"page": 11}, {"page": 201}])
def test_invalid_pagination_is_rejected_before_provider_call(account, monkeypatch, extra):
    monkeypatch.setattr(amap, "request", lambda *args, **kwargs: pytest.fail("Must not call upstream"))
    assert account.get("/api/v1/explore", params={"city": "北京", **extra}).status_code == 422


def test_meituan_is_not_repeated_on_later_pages(account, monkeypatch):
    calls = []
    monkeypatch.setattr(
        amap,
        "request",
        lambda path, params, ttl: {
            "data": {"count": "40", "pois": [poi((params["page"] - 1) * 20 + i) for i in range(20)]},
            "retrieved_at": "2026-11-17T00:00:00Z",
        },
    )
    monkeypatch.setattr(meituan, "configured", lambda: True)

    def recommend(*args, **kwargs):
        calls.append(1)
        return {"items": [{"title": "团购餐厅", "url": "https://www.meituan.com/example"}]}

    monkeypatch.setattr(meituan, "food_recommend", recommend)
    params = {"city": "北京", "category": "food"}
    first = account.get("/api/v1/explore", params=params).json()
    second = account.get("/api/v1/explore", params={**params, "page": 2}).json()
    assert len(calls) == 1
    assert len(first["items"]) == 21 and len(second["items"]) == 20
    assert second["next_page"] is None


def test_hotel_selector_pages_can_be_selected_with_version_check(account, hotel_trip):
    endpoint = f"/api/v1/trips/{hotel_trip['id']}"
    first = account.get(endpoint + "/hotels", params={"city": "北京", "query": "北京站"}).json()
    second = account.get(endpoint + "/hotels", params={"city": "北京", "query": "北京站", "page": 2}).json()
    assert len(first["items"]) == 20 and len(second["items"]) == 16
    assert second["next_page"] is None
    assert not ({p["id"] for p in first["items"]} & {p["id"] for p in second["items"]})
    choice = {"city": "北京", "place_id": second["items"][-1]["id"], "base_version": hotel_trip["version"]}
    assert account.post(endpoint + "/hotel", json=choice).status_code == 200
    assert account.post(endpoint + "/hotel", json=choice).status_code == 409
    saved = account.get(endpoint).json()
    assert saved["plan"]["hotels"][0]["name"] == "演示·北京旅居酒店 36"
    assert (
        account.get(endpoint + "/hotels", params={"city": "北京", "query": "酒店", "page": 11}).status_code
        == 422
    )
