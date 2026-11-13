"""Amap Web Service adapter. All coordinates remain GCJ-02 end to end.

Mode endpoint mapping references JourneyPilot, MIT; see docs/upstream/NOTICE.md.
"""

import math
from urllib.parse import urlencode, urlparse
from .base import ProviderError, read_json, source, safe_url
from ..config import settings

MODE_PATHS = {
    "public_transit": "/v3/direction/transit/integrated",
    "walk": "/v3/direction/walking",
    "drive": "/v3/direction/driving",
}


def request(path, params, ttl=900):
    if not settings.amap_key:
        raise ProviderError("credentials", "尚未配置高德 Web 服务 Key，请先完成平台配置")
    return read_json("https://restapi.amap.com" + path, {**params, "key": settings.amap_key}, ttl)


def number(value):
    try:
        result = float(value)
        return result if math.isfinite(result) and result >= 0 else None
    except (ValueError, TypeError):
        return None


def poi_url(name, lon, lat):
    return "https://uri.amap.com/marker?" + urlencode(
        {"position": f"{lon},{lat}", "name": name, "src": "travel_agent", "coordinate": "gaode"}
    )


def search_places(city, query):
    raw = request(
        "/v3/place/text",
        {"keywords": query, "city": city, "citylimit": "true", "offset": 8, "extensions": "all"},
        3600,
    )
    return normalize_places(raw, city)


def search_nearby(city, lon, lat, category="food", query=""):
    raw = request(
        "/v3/place/around",
        {
            "location": f"{lon},{lat}",
            "radius": 3000 if category == "food" else 5000,
            "types": "050000" if category == "food" else "100000",
            "keywords": query,
            "sortrule": "distance",
            "offset": 6,
            "extensions": "all",
        },
        1800,
    )
    return normalize_places(raw, city)


def place_photo_url(value):
    if not isinstance(value, str):
        return None
    value = value.strip()
    if value.startswith("//"):
        value = "https:" + value
    try:
        parsed = urlparse(value)
        host = (parsed.hostname or "").lower()
        if parsed.scheme == "http" and host in {"store.is.autonavi.com", "aos-comment.amap.com", "aos-cdn-image.amap.com"} and not parsed.username and not parsed.password and parsed.port in (None, 80):
            value = parsed._replace(scheme="https", netloc=host).geturl()
        return safe_url(value)
    except ValueError:
        return None


def normalize_places(raw, city):
    pois = raw["data"].get("pois")
    if not isinstance(pois, list):
        raise ProviderError("schema", "地点查询缺少地点列表")
    result = []
    for item in pois:
        try:
            lon, lat = map(float, item["location"].split(","))
        except (ValueError, KeyError, TypeError):
            continue
        photos = item.get("photos") or []
        photos = list(
            dict.fromkeys(
                url
                for photo in photos
                if isinstance(photo, dict) and (url := place_photo_url(photo.get("url")))
            )
        )
        ext = item.get("biz_ext") if isinstance(item.get("biz_ext"), dict) else {}
        result.append(
            {
                "id": "amap:" + item["id"],
                "name": str(item.get("name", "")),
                "lon": lon,
                "lat": lat,
                "coordinate_system": "GCJ-02",
                "city": city,
                "address": item.get("address") if isinstance(item.get("address"), str) else "",
                "category": item.get("type", ""),
                "photos": photos,
                "description": "高德地点资料；介绍与预约要求请以原始来源为准。",
                "opening_text": ext.get("open_time") if isinstance(ext.get("open_time"), str) else None,
                "price_text": str(ext["cost"]) if ext.get("cost") not in (None, "", []) else None,
                "price_cny": None,
                "rating": number(ext.get("rating")),
                "phone": item.get("tel")[:150] if isinstance(item.get("tel"), str) else "",
                "distance_meters": number(item.get("distance")),
                "business_area": item.get("business_area")
                if isinstance(item.get("business_area"), str)
                else "",
                "district": item.get("adname") if isinstance(item.get("adname"), str) else "",
                "typecode": item.get("typecode") or "",
                "indoor": None,
                "source": source("高德地图", poi_url(item.get("name", ""), lon, lat), raw["retrieved_at"]),
            }
        )
    from .curated import enrich

    return [enrich(p) for p in result]


def route_between(a, b, mode, city):
    params = {
        "origin": f"{a['lon']},{a['lat']}",
        "destination": f"{b['lon']},{b['lat']}",
        "extensions": "all",
    }
    if mode == "public_transit":
        params.update(city=city, cityd=city, strategy=0)
    raw = request(MODE_PATHS[mode], params, 900)
    root = raw["data"].get("route") or {}
    alternatives = root.get("transits" if mode == "public_transit" else "paths") or []
    if not alternatives:
        raise ProviderError("no_route", f"没有查到 {a['name']} 至 {b['name']} 的路线")
    first = alternatives[0]
    steps, polylines, transit_segments = [], [], []
    if mode == "public_transit":
        for segment in first.get("segments", []):
            steps.extend((segment.get("walking") or {}).get("steps") or [])
            for bus in (segment.get("bus") or {}).get("buslines", []):
                departure = (bus.get("departure_stop") or {}).get("name", "上车站点待核实")
                arrival = (bus.get("arrival_stop") or {}).get("name", "下车站点待核实")
                count = number(bus.get("via_num"))
                instruction = f"{departure}上车，乘坐{bus.get('name', '公共交通')}，{arrival}下车"
                if count is not None:
                    instruction += f"（途经 {int(count)} 站）"
                steps.append({"instruction": instruction, "polyline": bus.get("polyline", "")})
                transit_segments.append(
                    {
                        "line": bus.get("name", "公共交通"),
                        "departure_stop": departure,
                        "arrival_stop": arrival,
                        "via_stops": count,
                        "first_departure": bus.get("start_time")
                        if isinstance(bus.get("start_time"), str)
                        else None,
                        "last_departure": bus.get("end_time")
                        if isinstance(bus.get("end_time"), str)
                        else None,
                    }
                )
        walking = number(first.get("walking_distance"))
    else:
        steps = first.get("steps", [])
        walking = number(first.get("distance")) if mode == "walk" else 0
    for step in steps:
        for pair in (step.get("polyline") or "").split(";"):
            try:
                polylines.append(list(map(float, pair.split(","))))
            except ValueError:
                pass
    duration = number(first.get("duration"))
    return {
        "transit_segments": transit_segments,
        "from_id": a["id"],
        "to_id": b["id"],
        "mode": mode,
        "minutes": math.ceil(duration / 60) if duration is not None else None,
        "distance_meters": number(first.get("distance")),
        "walking_meters": walking,
        "cost_cny": number(first.get("cost")),
        "polyline": polylines,
        "instructions": [s.get("instruction", "") for s in steps][:30],
        "source": source(
            "高德路线",
            "https://uri.amap.com/navigation?"
            + urlencode(
                {
                    "from": f"{a['lon']},{a['lat']},{a['name']}",
                    "to": f"{b['lon']},{b['lat']},{b['name']}",
                    "mode": {"public_transit": "bus", "walk": "walk", "drive": "car"}[mode],
                    "coordinate": "gaode",
                    "src": "travel_agent",
                }
            ),
            raw["retrieved_at"],
        ),
    }


def weather(city):
    geocode = request("/v3/geocode/geo", {"address": city, "city": city}, 86400)
    locations = geocode["data"].get("geocodes") or []
    if not locations:
        raise ProviderError("no_city", "没有查到该城市的行政区编码")
    result = request("/v3/weather/weatherInfo", {"city": locations[0]["adcode"], "extensions": "all"}, 1800)
    return {
        "forecasts": result["data"].get("forecasts", []),
        "source": source("高德天气", "https://www.amap.com/", result["retrieved_at"]),
    }


def resolve_origin(city, address):
    import hashlib

    raw = request("/v3/geocode/geo", {"address": address, "city": city}, 3600)
    entries = raw["data"].get("geocodes") or []
    if len(entries) != 1:
        raise ProviderError("ambiguous_origin", "出发位置未能唯一定位，请填写更具体的车站、酒店或地址")
    item = entries[0]
    lon, lat = map(float, item["location"].split(","))
    return {
        "id": "origin:" + hashlib.sha256(address.encode()).hexdigest()[:16],
        "name": address,
        "lon": lon,
        "lat": lat,
        "coordinate_system": "GCJ-02",
        "address": item.get("formatted_address", address),
        "source": source("高德地理编码", poi_url(address, lon, lat), raw["retrieved_at"]),
    }
