"""Explicit synthetic fixtures. Never used as fallback for a live provider error."""

from .base import source

# Finite synthetic catalogue used only when fixture mode is explicitly selected.
FIXTURE_DISCOVERY_COUNT = 36


def places(city="北京", query=""):
    names = [
        ("演示·城市博物馆", 116.407, 39.908, True),
        ("演示·古城公园", 116.410, 39.925, False),
        ("演示·历史街区", 116.395, 39.933, False),
        ("演示·艺术展馆", 116.430, 39.940, True),
        ("演示·滨水公园", 116.385, 39.945, False),
        ("演示·科学馆", 116.398, 39.970, True),
        ("演示·郊野景区", 116.270, 40.010, False),
        ("演示·自然教育馆", 116.280, 40.020, True),
        ("演示·文化展厅", 116.391, 39.917, True),
    ]
    return [
        {
            "id": f"fixture:{i}" if city == "北京" else f"fixture:{city}:{i}",
            "city": city,
            "name": n,
            "lon": x,
            "lat": y,
            "coordinate_system": "GCJ-02",
            "address": "合成测试地点，不代表真实营业场所",
            "category": "合成资料",
            "photos": [],
            "description": "仅用于验证流程，不可据此出游。",
            "opening_text": "测试窗口 09:00–17:00",
            "opening_minutes": [540, 1020],
            "price_text": "测试费用 0 元",
            "price_cny": 0,
            "indoor": inside,
            "source": source("合成测试夹具", None, "2026-11-12T00:00:00Z", synthetic=True),
        }
        for i, (n, x, y, inside) in enumerate(names)
    ]


def route(a, b, mode, city):
    return {
        "from_id": a["id"],
        "to_id": b["id"],
        "mode": mode,
        "minutes": 25,
        "distance_meters": 3000,
        "walking_meters": 400,
        "cost_cny": 4,
        "polyline": [[a["lon"], a["lat"]], [b["lon"], b["lat"]]],
        "instructions": ["合成测试线路"],
        "source": source("合成测试夹具", None, "2026-11-12T00:00:00Z", synthetic=True),
    }


def discovery_places(city, category="all"):
    """A finite, explicitly synthetic catalogue for exercising multi-page browsing."""
    base = places(city)
    noun = {"food": "餐厅", "stays": "酒店", "nature": "公园", "art": "展馆"}.get(category, "景点")
    items = []
    for index in range(FIXTURE_DISCOVERY_COUNT):
        original = base[index % len(base)]
        first_catalogue = index < len(base) and category not in {"food", "stays"}
        items.append({
            **original,
            "id": original["id"] if first_catalogue else f"fixture:discovery:{city}:{category}:{index}",
            "name": original["name"] if first_catalogue else f"演示·{city}{noun} {index + 1}",
            "category": "合成测试" + noun,
            "lon": original["lon"] + (index // len(base)) * 0.003,
            "lat": original["lat"] + (index // len(base)) * 0.002,
        })
    return items
