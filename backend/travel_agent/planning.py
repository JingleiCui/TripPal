"""Pure domain code. LLM-selected IDs are resolved against provider facts only."""

from datetime import timedelta
from .schemas import Requirements, day_cities


def clock(minutes):
    return f"{minutes // 60:02}:{minutes % 60:02}"


def validate_selection(selection, places, req: Requirements, old_plan=None):
    if len(selection) != req.days:
        raise ValueError("每日安排数量不符合出游天数")
    by_id = {p["id"]: p for p in places}
    flattened = [x for day in selection for x in day]
    if len(set(flattened)) != len(flattened):
        raise ValueError("行程中出现重复地点")
    if any(x not in by_id for x in flattened):
        raise ValueError("模型选择了无来源的地点")
    cities = day_cities(req)
    if any(by_id[x].get("city", req.city) != cities[i] for i, day in enumerate(selection) for x in day):
        raise ValueError("每日地点必须属于当天指定的城市，不能把跨城交通当成市内路线")
    if any(x in req.excluded_ids for x in flattened):
        raise ValueError("行程包含已排除地点")
    if set(req.locked_ids) - set(flattened):
        raise ValueError("修改遗漏了锁定地点")
    if old_plan:
        old_slots = {
            p["id"]: (day["day"] - 1, day.get("date"))
            for day in old_plan.get("days", [])
            for p in day["stops"]
        }
        new_slots = {p: i for i, day in enumerate(selection) for p in day}
        for ident in req.locked_ids:
            if ident in old_slots:
                day_index, old_date = old_slots[ident]
                if new_slots.get(ident) != day_index or (
                    req.start_date
                    and old_date
                    and str(req.start_date + timedelta(days=day_index)) != old_date
                ):
                    raise ValueError("修改会改变锁定地点的日期，请先解除锁定或保持原日期")
    if any(len(day) > 4 for day in selection):
        raise ValueError("每天最多安排四处地点，避免过密")
    if req.indoor_only and any(by_id[x].get("indoor") is not True for x in flattened):
        raise ValueError("缺少可确认的室内地点，不能保证雨天方案")
    return by_id


def build_plan(selection, places, req, route_fn, fixture=False, old_plan=None, origin=None):
    by_id = validate_selection(selection, places, req, old_plan)
    locked_times = {
        p["id"]: p
        for day in (old_plan or {}).get("days", [])
        for p in day["stops"]
        if p["id"] in req.locked_ids
    }
    warnings, days, known_cost = [], [], 0.0
    all_unknown = set()
    for day_index, ids in enumerate(selection):
        day_city = day_cities(req)[day_index]
        current, stops, routes, walk = 540, [], [], 0
        arrival = None
        if day_index == 0 and ids and origin:
            try:
                arrival = route_fn(origin, by_id[ids[0]], req.transport, req.city)
                if arrival.get("minutes") is None:
                    raise ValueError("起点接驳缺少耗时")
                current += arrival["minutes"] + 15
                walk += arrival.get("walking_meters") or 0
                if arrival.get("cost_cny") is not None:
                    known_cost += arrival["cost_cny"] * req.people
                else:
                    all_unknown.add("起点接驳费用")
            except Exception:
                all_unknown.add("出发位置至首个地点的交通")
                warnings.append("起点接驳未核实，不能据此承诺到达时间")
        if not ids:
            warnings.append(f"第 {day_index + 1} 天没有足够候选地点，需要补充")
        for i, ident in enumerate(ids):
            place = by_id[ident]
            if i:
                try:
                    route = route_fn(by_id[ids[i - 1]], place, req.transport, day_city)
                    if route.get("minutes") is None:
                        raise ValueError("缺少交通耗时")
                    current += route["minutes"] + 15
                    walk += route.get("walking_meters") or 0
                    if route.get("walking_meters") is None:
                        all_unknown.add("部分路段步行距离")
                    routes.append(route)
                    if route.get("cost_cny") is not None:
                        known_cost += route["cost_cny"] * req.people
                    else:
                        all_unknown.add("部分交通费用")
                except Exception:
                    routes.append(
                        {
                            "from_id": ids[i - 1],
                            "to_id": ident,
                            "minutes": None,
                            "polyline": [],
                            "error": "路线未核实，请重试或人工确认",
                        }
                    )
                    all_unknown.add("部分交通时间与距离")
                    warnings.append(f"{by_id[ids[i - 1]]['name']} 到 {place['name']} 的路线未核实")
            if current >= 720 and not any(s.get("lunch_before") for s in stops):
                current += 60
                lunch = True
            else:
                lunch = False
            opening = place.get("opening_minutes")
            if ident in locked_times:
                locked = locked_times[ident]
                hour, minute = map(int, locked["planned_start"].split(":"))
                fixed_start = hour * 60 + minute
                if current > fixed_start:
                    raise ValueError("新路线与已锁定的时间冲突，请减少安排或解除锁定后重试")
                current = fixed_start
            if opening:
                current = max(current, opening[0])
                if current + 90 > opening[1]:
                    warnings.append(f"{place['name']} 的计划时段超出已知开放窗口")
            else:
                all_unknown.add("开放与预约条件")
            stops.append(
                {
                    **place,
                    "planned_start": clock(current),
                    "planned_end": clock(current + 90),
                    "visit_minutes": 90,
                    "visit_duration_basis": "计划停留时间，非平台事实",
                    "lunch_before": lunch,
                    "locked": ident in req.locked_ids,
                }
            )
            current += 90
            if place.get("price_cny") is None:
                all_unknown.add("门票费用")
            else:
                known_cost += place["price_cny"] * req.people
        if current > 1080:
            warnings.append(f"第 {day_index + 1} 天预计晚于 18:00，需要减少安排")
        if walk > req.max_walk_meters:
            warnings.append(f"第 {day_index + 1} 天路段步行距离超过限制")
        days.append(
            {
                "day": day_index + 1,
                "city": day_city,
                "date": str(req.start_date + timedelta(days=day_index)) if req.start_date else None,
                "stops": stops,
                "routes": routes,
                "arrival_route": arrival,
                "known_route_walking_meters": walk,
                "walking_note": "不包含景点内部步行，不能视为全天总步行量",
            }
        )
    all_unknown.update(["餐饮费用", "住宿费用", "景点内部步行", "住宿及返程接驳"])
    if origin is None:
        all_unknown.add("出发位置至首个地点的交通")
    if req.budget is not None and known_cost > req.budget:
        warnings.append("已知费用已经超过总预算")
    transfers = [
        {
            "from_city": day_cities(req)[i - 1],
            "to_city": city,
            "before_day": i + 1,
            "status": "待核实",
            "note": "跨城交通的班次、耗时、费用及到达时间需另行查询，不使用市内路线代替",
        }
        for i, city in enumerate(day_cities(req))
        if i and city != day_cities(req)[i - 1]
    ]
    if transfers:
        all_unknown.add("跨城交通班次、费用与到达衔接")
        warnings.append("跨城交通尚待核实，不能保证连续日安排能够衔接")
    return {
        "title": f"{' → '.join(dict.fromkeys(day_cities(req)))} · {req.days} 日{'轻户外' if req.style == 'outdoor' else '城市'}行程",
        "transfers": transfers,
        "requirements": req.model_dump(mode="json"),
        "days": days,
        "warnings": warnings,
        "budget": {
            "known_subtotal_cny": round(known_cost, 2),
            "limit_cny": req.budget,
            "unknown_items": sorted(all_unknown),
            "status": "费用不完整，不能保证总预算",
        },
        "verification": "needs_review" if warnings or all_unknown else "checked",
        "fixture": fixture,
        "booking_status": "未预订",
        "rationale": "",
    }


def plan_diff(old, new):
    old_ids = {s["id"] for d in old.get("days", []) for s in d["stops"]}
    new_ids = {s["id"] for d in new.get("days", []) for s in d["stops"]}
    return {
        "added": sorted(new_ids - old_ids),
        "removed": sorted(old_ids - new_ids),
        "retained": sorted(new_ids & old_ids),
    }
