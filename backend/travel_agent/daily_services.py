"""Concrete daily dining, accommodation and transport. Provider facts remain separate from estimates."""

import copy
import time
import re
import math
from datetime import date, timedelta
from .providers import amap, fixtures
from .providers.base import timestamp

# Daily read budget: three nearby meal searches, one hotel search and up to ten legs.
DETAIL_CACHE_SECONDS = 1800
MAX_ROUTE_LEGS = 10
DAILY_LOOKUP_BUDGET_SECONDS = 120
MEAL_DURATION_MINUTES = {"breakfast": 40, "lunch": 60, "dinner": 60}
MEAL_LABELS = {"breakfast": "早餐", "lunch": "午餐", "dinner": "晚餐"}


def synthetic_nearby(city, anchor, kind, slot):
    names = (
        (
            ["早餐铺", "豆浆烧饼店", "包子铺"]
            if slot == "breakfast"
            else ["本地家常菜馆", "街角面馆", "风味小吃店"]
        )
        if kind == "food"
        else ["城市旅居酒店", "街区精品酒店", "便捷酒店"]
    )
    return [
        {
            "id": f"fixture-service:{city}:{'breakfast' if slot == 'breakfast' else kind}:{i}",
            "name": "演示·" + name,
            "city": city,
            "address": "合成测试地址，不代表真实营业场所",
            "lon": anchor["lon"] + 0.002 * (i + 1),
            "lat": anchor["lat"] + 0.001 * (i + 1),
            "coordinate_system": "GCJ-02",
            "category": "合成测试餐厅" if kind == "food" else "合成测试酒店",
            "photos": [],
            "description": "仅供流程验证，不可据此出游。",
            "phone": "",
            "rating": None,
            "opening_text": "合成营业时间 07:00–22:00",
            "price_text": "合成参考费用，非真实价格",
            "source": {
                "provider": "合成测试资料",
                "synthetic": True,
                "retrieved_at": timestamp(),
                "url": None,
            },
        }
        for i, name in enumerate(names)
    ]


def opening_window(place):
    text = place.get("opening_text") or ""
    match = re.search(r"(\d{1,2}):(\d{2})\s*[-—–~至]\s*(\d{1,2}):(\d{2})", text)
    if not match:
        return None
    h1, m1, h2, m2 = map(int, match.groups())
    start, end = h1 * 60 + m1, h2 * 60 + m2
    return (start, end) if end > start else None


def near_distance(a, b):
    lat1, lat2 = math.radians(a["lat"]), math.radians(b["lat"])
    dlat, dlon = lat2 - lat1, math.radians(b["lon"] - a["lon"])
    value = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return 6371000 * 2 * math.asin(min(1, math.sqrt(value)))


def minutes(value):
    h, m = map(int, value.split(":"))
    return h * 60 + m


def clock(value):
    return f"{value // 60:02}:{value % 60:02}"


def daily_details(plan, day_number, mode, query="", replacing=""):
    deadline = time.monotonic() + DAILY_LOOKUP_BUDGET_SECONDS
    day = plan["days"][day_number - 1]
    stops = day.get("stops", [])
    city = day.get("city") or plan["requirements"]["city"]
    fixture = plan.get("fixture", False)
    warnings, provider_errors = [], []
    if not stops:
        return {
            "day": day_number,
            "city": city,
            "meals": [],
            "hotels": [],
            "timeline": [],
            "legs": [],
            "warnings": ["当天尚无地点，请先生成每日安排。"],
            "fixture": fixture,
        }
    anchors = {"breakfast": stops[0], "lunch": stops[min(1, len(stops) - 1)], "dinner": stops[-1]}
    saved_meals = {meal["slot"]: meal["place"] for meal in day.get("meals", [])}
    meals = []
    used_meal_ids = set()
    for slot, anchor in anchors.items():
        try:
            if time.monotonic() >= deadline:
                raise TimeoutError("daily lookup budget")
            items = (
                synthetic_nearby(city, anchor, "food", slot)
                if fixture
                else amap.search_nearby(
                    city,
                    anchor["lon"],
                    anchor["lat"],
                    "food",
                    query if replacing == slot else ("早餐" if slot == "breakfast" else "餐厅"),
                )
            )
            if not fixture:
                target = {
                    "breakfast": 480,
                    "lunch": 720,
                    "dinner": max(1080, minutes(stops[-1].get("planned_end", "18:00"))),
                }[slot]
                items = [
                    p
                    for p in items
                    if (
                        slot == "breakfast"
                        or not any(
                            w in p.get("category", "")
                            for w in ["茶艺馆", "咖啡厅", "冷饮店", "甜品店", "酒吧"]
                        )
                    )
                    and (
                        opening_window(p) is None
                        or opening_window(p)[1] >= target + MEAL_DURATION_MINUTES[slot]
                    )
                ]
            selected = saved_meals.get(slot)
            if selected:
                fresh_selected = next((p for p in items if p["id"] == selected["id"]), None)
                selected = {**selected, **fresh_selected} if fresh_selected else selected
                items = [selected, *[p for p in items if p["id"] != selected["id"]]]
            else:
                fresh = [p for p in items if p["id"] not in used_meal_ids]
                items = fresh + [p for p in items if p["id"] in used_meal_ids] if fresh else items
            if items:
                used_meal_ids.add(items[0]["id"])
            meals.append(
                {
                    "slot": slot,
                    "label": MEAL_LABELS[slot],
                    "place": items[0] if items else None,
                    "alternatives": items,
                    "user_selected": bool(selected),
                    "anchor_name": anchor["name"],
                }
            )
            if not items:
                warnings.append(f"{MEAL_LABELS[slot]}：附近未查到匹配餐厅，可修改关键词再找。")
        except Exception:
            provider_errors.append(f"{MEAL_LABELS[slot]}地点查询暂不可用")
            selected = saved_meals.get(slot)
            meals.append(
                {
                    "slot": slot,
                    "label": MEAL_LABELS[slot],
                    "place": selected,
                    "alternatives": [selected] if selected else [],
                    "user_selected": bool(selected),
                    "anchor_name": anchor["name"],
                }
            )
    hotels, hotel = [], None
    needs_accommodation = plan["requirements"].get("needs_accommodation")
    if needs_accommodation is True or (needs_accommodation is None and len(plan["days"]) > 1):
        chosen = next((h for h in plan.get("hotels", []) if h.get("city") == city), None)
        try:
            if time.monotonic() >= deadline:
                raise TimeoutError("daily lookup budget")
            hotels = (
                synthetic_nearby(city, stops[0], "stays", "hotel")
                if fixture
                else amap.search_nearby(
                    city, stops[0]["lon"], stops[0]["lat"], "stays", query if replacing == "hotel" else ""
                )
            )
        except Exception:
            provider_errors.append("住宿地点查询暂不可用")
        if not fixture and not chosen and not query:
            hotels.sort(key=lambda p: -(p.get("rating") or 0) + (p.get("distance_meters") or 0) / 10000)
        if chosen:
            fresh_chosen = next((p for p in hotels if p["id"] == chosen["id"]), None)
            chosen = {**chosen, **fresh_chosen} if fresh_chosen else chosen
            hotels = [chosen, *[p for p in hotels if p["id"] != chosen["id"]]]
        hotel = hotels[0] if hotels else None
        if not hotel:
            warnings.append("暂未找到住宿地点，可以更换区域或关键词。")
    by_slot = {meal["slot"]: meal for meal in meals}
    sequence = []
    origin = None
    if day_number == 1 and plan["requirements"].get("origin"):
        try:
            if fixture:
                origin = {**stops[0], "id": "fixture-origin", "name": plan["requirements"]["origin"]}
            elif time.monotonic() < deadline:
                origin = amap.resolve_origin(city, plan["requirements"]["origin"])
            if origin:
                sequence.append(
                    {
                        "kind": "origin",
                        "label": "从出发位置开始",
                        "place": origin,
                        "minimum": 480,
                        "duration": 0,
                    }
                )
        except Exception:
            warnings.append("出发位置接驳暂未核实，请先确认到达城市的时间。")
    previous_city = plan["days"][day_number - 2].get("city") if day_number > 1 else None
    if day_number > 1 and previous_city and previous_city != city:
        warnings.append("跨城到达时间尚未确认，当天的用餐与游览时刻需按实际到达时间调整。")
    if hotel and day_number > 1 and previous_city == city:
        sequence.append(
            {"kind": "hotel_departure", "label": "从住宿出发", "place": hotel, "minimum": 480, "duration": 0}
        )
    if by_slot["breakfast"]["place"]:
        sequence.append(
            {
                "kind": "meal",
                "slot": "breakfast",
                "label": "早餐",
                "place": by_slot["breakfast"]["place"],
                "minimum": 480,
                "duration": 40,
            }
        )
    lunch_added = False
    for i, stop in enumerate(stops):
        if (
            (stop.get("lunch_before") or (len(stops) > 1 and i == min(2, len(stops) - 1)))
            and not lunch_added
            and by_slot["lunch"]["place"]
        ):
            sequence.append(
                {
                    "kind": "meal",
                    "slot": "lunch",
                    "label": "午餐",
                    "place": by_slot["lunch"]["place"],
                    "minimum": 720,
                    "duration": 60,
                }
            )
            lunch_added = True
        sequence.append(
            {
                "kind": "place",
                "label": "游览",
                "place": stop,
                "minimum": minutes(stop.get("planned_start", "09:00")),
                "duration": stop.get("visit_minutes", 90),
            }
        )
    if not lunch_added and by_slot["lunch"]["place"]:
        sequence.append(
            {
                "kind": "meal",
                "slot": "lunch",
                "label": "午餐",
                "place": by_slot["lunch"]["place"],
                "minimum": 720,
                "duration": 60,
            }
        )
    if by_slot["dinner"]["place"]:
        sequence.append(
            {
                "kind": "meal",
                "slot": "dinner",
                "label": "晚餐",
                "place": by_slot["dinner"]["place"],
                "minimum": 1080,
                "duration": 60,
            }
        )
    if hotel:
        sequence.append({"kind": "hotel", "label": "回到住宿", "place": hotel, "minimum": 0, "duration": 0})
    timeline, legs, current, walking, transit_cost = [], [], 480, 0, 0.0
    routes = {
        (r.get("from_id"), r.get("to_id")): r
        for r in day.get("routes", [])
        if not r.get("error")
        and r.get("mode") == mode
        and (fixture or not r.get("source", {}).get("synthetic"))
    }
    previous = None
    timing_verified = True
    for index, entry in enumerate(sequence):
        place = entry["place"]
        if previous and previous["id"] != place["id"] and len(legs) < MAX_ROUTE_LEGS:
            try:
                if time.monotonic() >= deadline:
                    raise TimeoutError("daily lookup budget")
                route = routes.get((previous["id"], place["id"]))
                if route is None:
                    leg_mode = (
                        "walk" if mode == "public_transit" and near_distance(previous, place) < 800 else mode
                    )
                    route = (
                        fixtures.route(previous, place, leg_mode, city)
                        if fixture
                        else amap.route_between(previous, place, leg_mode, city)
                    )
                route = {
                    **copy.deepcopy(route),
                    "from_name": previous["name"],
                    "to_name": place["name"],
                    "mode": route.get("mode", mode),
                    "before_index": index,
                }
                if route.get("minutes") is not None:
                    current += int(route["minutes"]) + 10
                else:
                    timing_verified = False
                    warnings.append(f"{previous['name']}至{place['name']}的到达时间待核实")
                walking += route.get("walking_meters") or 0
                if route.get("cost_cny") is not None:
                    transit_cost += route["cost_cny"]
                route["arrival"] = clock(current)
                legs.append(route)
            except Exception:
                timing_verified = False
                legs.append(
                    {
                        "from_id": previous["id"],
                        "to_id": place["id"],
                        "from_name": previous["name"],
                        "to_name": place["name"],
                        "mode": mode,
                        "before_index": index,
                        "minutes": None,
                        "polyline": [],
                        "error": "未查到可核实路线，请在地图中确认。",
                    }
                )
        current = max(current, entry["minimum"])
        if entry["kind"] == "meal":
            window = opening_window(place)
            if window:
                current = max(current, window[0])
                if current + entry["duration"] > window[1]:
                    warnings.append(f"{place['name']}的用餐时段可能超出营业时间，请换一家或调整顺序。")
        if entry["kind"] == "place" and place.get("locked") and current > entry["minimum"]:
            warnings.append(f"加入吃住安排后，{place['name']}可能无法按锁定时间到达，请调整安排。")
        timeline.append(
            {
                "kind": entry["kind"],
                "slot": entry.get("slot"),
                "label": entry["label"],
                "place": place,
                "start": clock(current),
                "end": clock(current + entry["duration"]),
                "duration": entry["duration"],
                "timing_verified": timing_verified,
            }
        )
        if entry.get("slot"):
            by_slot[entry["slot"]]["planned_start"] = clock(current)
        current += entry["duration"]
        previous = place
    lunch_time = by_slot["lunch"].get("planned_start")
    if lunch_time and minutes(lunch_time) > 810:
        warnings.append("午餐预计晚于 13:30，可缩短上午游览或选择更近的餐厅。")
    if current > 1260:
        warnings.append("加入餐饮与接驳后预计晚于 21:00，可减少景点或调整餐厅位置。")
    if walking > plan["requirements"].get("max_walk_meters", 8000):
        warnings.append("当天已知路段步行距离超过设定上限，建议切换交通方式。")
    city_days = sum(1 for d in plan["days"] if (d.get("city") or city) == city)
    final_city = plan["days"][-1].get("city") or city
    nights = max(1, city_days - (1 if city == final_city else 0))
    checkin = next((d.get("date") for d in plan["days"] if (d.get("city") or city) == city), None)
    checkout = (date.fromisoformat(checkin) + timedelta(days=nights)).isoformat() if checkin else None
    return {
        "day": day_number,
        "date": day.get("date"),
        "city": city,
        "fixture": fixture,
        "mode": mode,
        "meals": meals,
        "hotel": hotel,
        "hotels": hotels,
        "stay": {
            "checkin": checkin,
            "checkout": checkout,
            "nights": nights,
            "people": plan["requirements"].get("people", 1),
            "selected": bool(hotel and hotel.get("user_selected")),
        },
        "timeline": timeline,
        "legs": legs,
        "walking_meters": walking,
        "known_transport_cny_per_person": round(transit_cost, 2),
        "warnings": [*warnings, *provider_errors],
        "retrieved_at": timestamp(),
        "notice": "合成流程资料，不能用于出游。"
        if fixture
        else "具体店铺与路线来自高德；用餐时长和游览时长为计划建议，交通耗时为查询时参考，不代表指定日期的班次。餐厅营业、菜单、酒店房型和当日价格需向商家确认。",
    }
