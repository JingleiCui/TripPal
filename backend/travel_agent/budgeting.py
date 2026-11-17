"""Itemized CNY planning ledger. Missing or masked prices are never treated as zero."""

from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
import re

CATEGORIES = {"food": "餐饮", "hotel": "住宿", "transport": "交通", "tickets": "门票", "other": "其他"}


def amount(value):
    if value is None or isinstance(value, bool):
        return None
    try:
        result = Decimal(str(value))
        return result if result.is_finite() and 0 <= result <= 10000000 else None
    except (InvalidOperation, ValueError):
        return None


def cny(value):
    return float(value.quantize(Decimal(".01"), rounding=ROUND_HALF_UP)) if value is not None else None


def reference_meal_price(place):
    if not place or place.get("source", {}).get("synthetic"):
        return None
    text = str(place.get("price_text") or "").strip()
    match = re.fullmatch(r"[￥¥]?\s*(\d+(?:\.\d{1,2})?)\s*(?:元)?(?:\s*/\s*人)?", text)
    return amount(match.group(1)) if match else None


def compatible_snapshot(plan, day, snapshot):
    data = snapshot.data if hasattr(snapshot, "data") else snapshot
    if data.get("day") != day["day"] or data.get("date") != day.get("date"):
        return False
    mode = day.get("transport_mode") or plan["requirements"]["transport"]
    if data.get("mode") != mode:
        return False
    planned = [p["id"] for p in day.get("stops", [])]
    actual = [e["place"]["id"] for e in data.get("timeline", []) if e["kind"] == "place"]
    if (
        planned != actual
        or data.get("stay", {}).get("people", plan["requirements"]["people"])
        != plan["requirements"]["people"]
    ):
        return False
    meals = {m["slot"]: (m.get("place") or {}).get("id") for m in data.get("meals", [])}
    if any(meals.get(m["slot"]) != m["place"]["id"] for m in day.get("meals", [])):
        return False
    city = day.get("city") or plan["requirements"]["city"]
    chosen = next((h for h in plan.get("hotels", []) if h.get("city") == city), None)
    return not chosen or (data.get("hotel") or {}).get("id") == chosen["id"]


def calculate_budget(plan, snapshots):
    req = plan["requirements"]
    days = plan.get("days", [])
    people = req.get("people", 1)
    settings = plan.get("budget_settings", {})
    rooms = settings.get("rooms", max(1, (people + 1) // 2))
    overrides = settings.get("overrides", {})
    total_limit = amount(req.get("budget"))
    rows_by_day = {}
    source_times = []
    for day in days:
        n = day["day"]
        city = day.get("city") or req["city"]
        rows = []
        snapshot = next(
            (s.data if hasattr(s, "data") else s for s in snapshots if compatible_snapshot(plan, day, s)),
            None,
        )
        if snapshot and snapshot.get("retrieved_at"):
            source_times.append(snapshot["retrieved_at"])

        def add(
            key,
            category,
            label,
            unit_price=None,
            unit="per_person",
            fingerprint="",
            source="",
            note="",
            confidence="reference",
        ):
            override = overrides.get(key)
            if override and override.get("fingerprint", "") == fingerprint:
                unit_price = amount(override["unit_price_cny"])
                unit = override["unit"]
                source = "手动填写"
                confidence = override["confidence"]
                note = override.get("note", "")
            else:
                unit_price = amount(unit_price)
                if override:
                    note = "地点或路线已变更，未继续套用旧手填金额。" + note
            quantity = people if unit == "per_person" else rooms if unit == "per_room_night" else 1
            subtotal = unit_price * quantity if unit_price is not None else None
            rows.append(
                {
                    "key": key,
                    "day": n,
                    "category": category,
                    "category_name": CATEGORIES[category],
                    "label": label,
                    "unit_price_cny": cny(unit_price),
                    "unit": unit,
                    "quantity": quantity,
                    "subtotal_cny": cny(subtotal),
                    "confidence": confidence if subtotal is not None else "unknown",
                    "fingerprint": fingerprint,
                    "source": source,
                    "note": note,
                }
            )

        meals = {m["slot"]: m for m in (snapshot or {}).get("meals", [])}
        for slot, label in [("breakfast", "早餐"), ("lunch", "午餐"), ("dinner", "晚餐")]:
            place = (meals.get(slot) or {}).get("place")
            add(
                f"meal:{n}:{slot}",
                "food",
                label + (" · " + place["name"] if place else " · 餐厅待核实"),
                reference_meal_price(place),
                fingerprint=place["id"] if place else "",
                source=(place or {}).get("source", {}).get("provider", ""),
                note="地图参考人均，非实际结账金额",
            )
        for stop in day.get("stops", []):
            add(
                f"ticket:{n}:{stop['id']}",
                "tickets",
                stop["name"] + " · 门票",
                stop.get("price_cny"),
                fingerprint=stop["id"],
                source=stop.get("source", {}).get("provider", ""),
                note="未查到票价时需核对预约平台；不能按免费处理",
            )
        hotel = (snapshot or {}).get("hotel") or next(
            (h for h in plan.get("hotels", []) if h.get("city") == city), None
        )
        needs_hotel = req.get("needs_accommodation") is True or (
            req.get("needs_accommodation") is not False and len(days) > 1
        )
        overnight = n < len(days) or (len(days) == 1 and req.get("needs_accommodation") is True)
        if needs_hotel and overnight:
            add(
                f"hotel:{n}",
                "hotel",
                (hotel["name"] if hotel else city + "住宿") + " · 当晚",
                unit="per_room_night",
                fingerprint=(hotel or {}).get("id", ""),
                note="每晚房价×房间数；脱敏报价不换算为确定金额，离店日不重复计房费",
            )
        legs = (snapshot or {}).get("legs", [])
        if legs:
            for i, leg in enumerate(legs):
                mode = leg.get("mode") or req["transport"]
                price = 0 if mode == "walk" else leg.get("cost_cny")
                label = leg.get("from_name", "上一站") + " → " + leg.get("to_name", "下一站")
                add(
                    f"route:{n}:{i}:{leg.get('from_id', '')}:{leg.get('to_id', '')}",
                    "transport",
                    label,
                    price,
                    unit="group" if mode == "drive" else "per_person",
                    fingerprint=mode,
                    source=leg.get("source", {}).get("provider", ""),
                    note="步行本身无票价"
                    if mode == "walk"
                    else "驾车路段费用不含尚未核对的油费与停车费"
                    if mode == "drive"
                    else "票价按出行人数计算",
                )
            if any(leg.get("mode") == "drive" for leg in legs):
                add(f"driving-extras:{n}", "transport", "油费与停车费", unit="group")
        else:
            add(f"local-transport:{n}", "transport", "当天市内接驳 · 路线尚未完整核算", unit="group")
        if (
            n == 1
            and snapshot
            and req.get("origin")
            and city in req["origin"]
            and not any(entry.get("kind") == "origin" for entry in snapshot.get("timeline", []))
        ):
            add(
                "arrival-local-connection",
                "transport",
                "出发位置到当天首站的接驳",
                note="尚未获得起点接驳费用，不能按免费计",
            )
        if n == 1 and not (req.get("origin") and city in req["origin"]):
            add(
                "arrival-travel",
                "transport",
                "到达目的地的车票 / 机票",
                note="如本次不需要，可填写 0 并注明原因",
            )
        if n == len(days):
            add(
                "return-travel",
                "transport",
                "返程 / 离开最后一站的交通",
                note="含必要的机场或车站接驳；如不需要，可填写 0",
            )
        if n > 1:
            previous = days[n - 2].get("city") or req["city"]
            if previous != city:
                add(f"intercity:{n}", "transport", previous + " → " + city + " · 城际交通")
        add(
            f"extra:{n}",
            "other",
            "其他消费 / 机动预留",
            0,
            unit="group",
            source="未安排额外消费",
            confidence="estimated",
            note="可填写零食、购物、行李寄存及机动金额",
        )
        rows_by_day[n] = rows

    def summarize(rows, limit):
        subtotal = sum((amount(r["subtotal_cny"]) or Decimal(0) for r in rows), Decimal(0))
        missing = [r for r in rows if r["subtotal_cny"] is None]
        reference = any(
            r["confidence"] != "confirmed" and (r["subtotal_cny"] or 0) > 0
            for r in rows
            if r["subtotal_cny"] is not None
        )
        if limit is None:
            status = "no_budget"
        elif subtotal > limit:
            status = "over_budget"
        elif missing:
            status = "incomplete"
        else:
            status = "within_estimate" if reference else "within_budget"
        return {
            "priced_subtotal_cny": cny(subtotal),
            "limit_cny": cny(limit),
            "unpriced_count": len(missing),
            "unpriced_labels": [r["label"] for r in missing],
            "is_complete": not missing,
            "status": status,
            "overrun_cny": cny(max(Decimal(0), subtotal - limit)) if limit is not None else None,
            "remaining_cny": cny(limit - subtotal) if limit is not None and not missing else None,
            "confirmed_subtotal_cny": cny(
                sum(
                    (amount(r["subtotal_cny"]) or Decimal(0) for r in rows if r["confidence"] == "confirmed"),
                    Decimal(0),
                )
            ),
        }

    daily = []
    for day in days:
        n = day["day"]
        explicit = settings.get("daily_limits", {}).get(str(n))
        limit = (
            amount(explicit)
            if explicit is not None
            else total_limit / len(days)
            if total_limit is not None
            else None
        )
        daily.append(
            {
                "day": n,
                "date": day.get("date"),
                "city": day.get("city") or req["city"],
                "rows": rows_by_day[n],
                "limit_basis": "当日单独设置"
                if explicit is not None
                else "全程预算的日均参考，不是单独日预算",
                **summarize(rows_by_day[n], limit),
            }
        )
    all_rows = [r for rows in rows_by_day.values() for r in rows]
    return {
        "days": daily,
        "trip": summarize(all_rows, total_limit),
        "people": people,
        "rooms": rooms,
        "rooms_estimated": "rooms" not in settings,
        "source_times": sorted(set(source_times)),
        "notice": "金额均为人民币。已计小计不代表完整花费；缺失费用不按 0 元处理。餐厅参考价不等于实际结账，平台脱敏房价需另行确认。",
    }
