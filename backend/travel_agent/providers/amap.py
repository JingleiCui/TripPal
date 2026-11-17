"""高德 Web 服务适配器。所有坐标端到端保持 GCJ-02。"""

import math
from urllib.parse import urlencode, urlparse
from .base import ProviderError, read_json, source, safe_url
from ..config import settings

MODE_PATHS = {
    "public_transit": "/v3/direction/transit/integrated",
    "walk": "/v3/direction/walking",
    "drive": "/v3/direction/driving",
}

# Discovery uses real upstream pagination; agent tool calls retain a small default.
# AMap POI text search exposes at most 200 results for one set of search parameters.
SEARCH_MAX_RESULTS = 200
SEARCH_MAX_PAGE_SIZE = 25
AGENT_SEARCH_PAGE_SIZE = 8


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


# 餐饮检索里要把「不是吃饭的地方」剔除：餐饮管理公司、中央厨房、
# 食材/食品配送、以及各类「XX 餐饮股份有限公司」「XX 食品股份」等。
# 它们在高德里 typecode 也落在 05 餐饮大类，仅靠大类码拦不住；
# 用分类路径(type)与名称双重信号识别。
NON_DINING_HINTS = (
    "餐饮管理", "管理", "集团", "总部", "办事处", "配送", "供应链",
    "中央厨房", "食材", "食品厂", "工业园", "商行", "贸易", "科技",
    "投资", "咨询", "加盟", "招商", "运营", "股份", "实业", "控股",
    "产业园", "物流", "仓储", "加工", "合作社",
)


def _is_dining_outlet(place):
    category = place.get("category") or ""
    name = place.get("name") or ""
    # 分类路径直接标明「餐饮管理」的，是管理机构而非门店。
    if "餐饮管理" in category or "餐饮管理" in name:
        return False
    # 名称出现明显企业/机构信号 → 不是可就餐门店。
    if any(hint in name for hint in NON_DINING_HINTS):
        return False
    # 必须落在餐饮大类(05)，公司企业大类(17)等自然排除。
    if not str(place.get("typecode") or "").startswith("05"):
        return False
    return True


def search_places(city, query, types=None):
    """Bounded first-page lookup for planning agents and existing tools."""
    return search_places_page(city, query, types, page_size=AGENT_SEARCH_PAGE_SIZE)["items"]


def search_places_page(city, query, types=None, *, page=1, page_size=20):
    """按关键词检索城市 POI。

    ``types`` 是高德 POI 大类码（如 050000 餐饮服务）。文本检索即使带
    types，仍可能返回名称相近的公司/管理机构（例如「XX 餐饮管理有限公司」，
    typecode 属于 170000 公司企业），因此在规范化之后按返回的 typecode
    再兜一层，只保留目标大类，避免把企业条目当成可以吃饭的门店。
    """
    if not 1 <= page_size <= SEARCH_MAX_PAGE_SIZE or page < 1:
        raise ValueError("Invalid POI pagination")
    start = (page - 1) * page_size
    if start >= SEARCH_MAX_RESULTS:
        raise ValueError("POI search page exceeds provider result window")
    params = {
        "keywords": query,
        "city": city,
        "citylimit": "true",
        "offset": page_size,
        "page": page,
        "extensions": "all",
    }
    if types:
        params["types"] = types
    raw = request("/v3/place/text", params, 3600)
    # Stop from raw upstream pagination, not from the filtered display count:
    # a page of rejected companies must not hide restaurants on the next page.
    if not isinstance(raw["data"].get("pois"), list):
        raise ProviderError("schema", "地点查询缺少地点列表")
    raw_count = len(raw["data"]["pois"])
    visible_raw = {**raw, "data": {**raw["data"], "pois": raw["data"]["pois"][: SEARCH_MAX_RESULTS - start]}}
    places = normalize_places(visible_raw, city)
    count_value = number(raw["data"].get("count"))
    total = int(count_value) if count_value is not None else None
    if types:
        if types.startswith("05"):
            # 餐饮大类里混入餐饮管理公司/中央厨房/食材配送/股份公司等，
            # 仅按 typecode 前缀无法剔除，改用就餐门店判定。
            places = [place for place in places if _is_dining_outlet(place)]
        else:
            prefix = types.split("|")[0][:2]
            places = [
                place
                for place in places
                if str(place.get("typecode") or "").startswith(prefix)
            ]
    places = list({place["id"]: place for place in places}.values())
    # Keep the upstream offset stable on the last page, even for uneven page sizes.
    places = places[: max(0, SEARCH_MAX_RESULTS - start)]
    reached_limit = start + raw_count >= SEARCH_MAX_RESULTS
    has_more = (
        raw_count >= page_size
        and not reached_limit
        and (total is None or start + raw_count < total)
    )
    return {
        "items": places,
        "page": page,
        "page_size": page_size,
        "next_page": page + 1 if has_more else None,
        "has_more": has_more,
        "end_reason": None if has_more else "provider_limit" if reached_limit else "exhausted",
    }


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
    places = normalize_places(raw, city)
    if category == "food":
        places = [place for place in places if _is_dining_outlet(place)]
    return places


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
        "traffic": _traffic_summary(steps, mode),
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


def _traffic_summary(steps, mode):
    if mode != "drive":
        return {"applicable": False}
    statuses = [s.get("traffic_status") for s in steps if isinstance(s, dict) and s.get("traffic_status")]
    return {
        "applicable": True,
        "congested_steps": sum(1 for s in statuses if s in ("缓行", "拥堵")),
        "has_congestion": any(s in ("缓行", "拥堵") for s in statuses),
    }


def poi_detail(poi_id, city=""):
    """地点详情：开放时间、电话、评分、照片。poi_id 形如 'amap:B0FF...'。"""
    raw_id = poi_id.split(":", 1)[-1] if isinstance(poi_id, str) else str(poi_id)
    raw = request("/v3/place/detail", {"id": raw_id}, 86400)
    data = raw["data"]
    poi = data.get("poi") or (data.get("pois") or [None])[0]
    if not isinstance(poi, dict):
        raise ProviderError("empty", "没有查到该地点详情")
    photos = poi.get("photos") or []
    photos = list(
        dict.fromkeys(
            url for photo in photos if isinstance(photo, dict) and (url := place_photo_url(photo.get("url")))
        )
    )
    return {
        "id": "amap:" + poi["id"],
        "name": str(poi.get("name", "")),
        "city": city,
        "address": poi.get("address") if isinstance(poi.get("address"), str) else "",
        "category": poi.get("type", ""),
        "phone": poi.get("tel")[:150] if isinstance(poi.get("tel"), str) else "",
        "rating": number(poi.get("rating")),
        "opening_text": poi.get("open_time") if isinstance(poi.get("open_time"), str) else None,
        "photos": photos,
        "business_area": poi.get("business_area")
        if isinstance(poi.get("business_area"), str)
        else "",
        "source": source("高德地点详情", poi_url(poi.get("name", ""), 0, 0), raw["retrieved_at"]),
    }


def distance_matrix(origins, destinations, mode="driving"):
    """多点到多点的距离矩阵。origins/destinations 为 (lon,lat) 字符串或含 lon/lat 的字典。"""

    def fmt(point):
        if isinstance(point, dict):
            return f"{point['lon']},{point['lat']}"
        return str(point)

    origin_str = ";".join(fmt(o) for o in origins)
    dest_str = ";".join(fmt(d) for d in destinations)
    type_flag = "0" if mode == "driving" else "1"
    params = {"origins": origin_str, "destination": dest_str, "type": type_flag}
    if mode == "driving":
        params["strategy"] = 0
    raw = request("/v3/distance", params, 3600)
    rows = raw["data"].get("results") or []
    return {
        "mode": mode,
        "rows": rows,
        "source": source("高德距离矩阵", "https://www.amap.com/", raw["retrieved_at"]),
    }


def traffic_route(a, b, mode="drive"):
    """实时路况路线：复用驾车路线（已含路况），并给出拥堵摘要。"""
    plan = route_between(a, b, mode, a.get("city", ""))
    summary = plan.get("traffic", {})
    plan["traffic_note"] = (
        "路线已尽量规避拥堵" if not summary.get("has_congestion") else f"途经 {summary.get('congested_steps', 0)} 个缓行/拥堵路段"
    )
    return plan
