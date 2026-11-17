from travel_agent.discovery_api import _merge_meituan_food
from travel_agent.providers import meituan
from travel_agent.providers.base import ProviderError


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
