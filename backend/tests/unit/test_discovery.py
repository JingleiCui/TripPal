from travel_agent.discovery_api import _merge_meituan_food
from travel_agent.providers import meituan
from travel_agent.providers.amap import normalize_places, place_photo_url, strict_price_cny
from travel_agent.providers.base import ProviderError


def test_only_exact_numeric_amap_cost_becomes_price_cny():
    assert strict_price_cny("16.00") == 16.0
    assert strict_price_cny("120") == 120.0
    assert strict_price_cny("￥16") is None
    assert strict_price_cny("16 元") is None
    assert strict_price_cny("￥16起") is None
    assert strict_price_cny("16-20") is None
    assert strict_price_cny("免费") is None


def test_is_dining_outlet_filter():
    """就餐门店判定：真餐厅保留，餐饮管理/股份/公司企业/非餐饮都排除。"""
    from travel_agent.providers.amap import _is_dining_outlet

    assert _is_dining_outlet({"name": "老正兴菜馆", "category": "餐饮服务;中餐厅", "typecode": "050100"})
    assert not _is_dining_outlet(
        {"name": "某餐饮管理公司", "category": "餐饮服务;餐饮管理", "typecode": "050600"}
    )
    assert not _is_dining_outlet(
        {"name": "上海某某餐饮股份有限公司", "category": "餐饮服务;中餐厅", "typecode": "050100"}
    )
    assert not _is_dining_outlet({"name": "某餐饮集团", "category": "公司企业", "typecode": "170000"})
    assert not _is_dining_outlet({"name": "故宫", "category": "风景名胜;公园", "typecode": "110200"})


def test_amap_http_photos_are_upgraded_instead_of_silently_discarded():
    source = "http://store.is.autonavi.com/showpic/poi.jpg?size=large"
    assert place_photo_url(source) == "https://store.is.autonavi.com/showpic/poi.jpg?size=large"
    assert place_photo_url("//aos-comment.amap.com/image.jpg") == "https://aos-comment.amap.com/image.jpg"
    assert place_photo_url("javascript:alert(1)") is None
    assert place_photo_url("http://unknown.example/photo.jpg") is None
    assert place_photo_url("http://user:secret@store.is.autonavi.com/photo.jpg") is None
    raw = {
        "retrieved_at": "2026-11-13T00:00:00Z",
        "data": {
            "pois": [
                {
                    "id": "test",
                    "name": "景山公园",
                    "location": "116.39,39.92",
                    "photos": [
                        {"url": source},
                        {"url": "https://store.is.autonavi.com/showpic/poi.jpg?size=large"},
                        {"url": "https://store.is.autonavi.com/second.jpg"},
                    ],
                }
            ]
        },
    }
    assert len(normalize_places(raw, "北京")[0]["photos"]) == 2


def test_merge_skips_when_meituan_disabled(monkeypatch):
    monkeypatch.setattr(meituan, "configured", lambda: False)
    items = [{"id": "amap:1", "name": "高德餐厅"}]
    out, merged = _merge_meituan_food(items, "上海", "餐厅")
    assert merged is False
    assert len(out) == 1


def test_merge_appends_meituan_cards(monkeypatch):
    monkeypatch.setattr(meituan, "configured", lambda: True)
    monkeypatch.setattr(
        meituan,
        "food_recommend",
        lambda *a, **k: {"items": [{"title": "美团餐厅", "url": "https://dpurl.cn/x", "price_text": "¥99"}]},
    )
    items = [{"id": "amap:1", "name": "高德餐厅"}]
    out, merged = _merge_meituan_food(items, "上海", "餐厅")
    assert merged is True
    assert len(out) == 2
    assert out[1]["name"] == "美团餐厅"
    assert out[1]["source_label"] == "美团"
    assert out[1]["category"] == "美团美食"


def test_merge_degrades_on_error(monkeypatch):
    monkeypatch.setattr(meituan, "configured", lambda: True)

    def boom(*a, **k):
        raise ProviderError("upstream_rejected", "美团暂不可用")

    monkeypatch.setattr(meituan, "food_recommend", boom)
    items = [{"id": "amap:1", "name": "高德餐厅"}]
    out, merged = _merge_meituan_food(items, "上海", "餐厅")
    assert merged is False
    assert len(out) == 1
