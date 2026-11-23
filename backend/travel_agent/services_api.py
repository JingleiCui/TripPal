"""Daily meal, hotel and route facts tied to an accessible trip revision."""

import copy
from datetime import timedelta, date
from sqlalchemy import select
import hashlib
import json
import re
from typing import Literal
import redis
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field, field_validator
from .db import Session, Trip, Revision, DailyDetailSnapshot, Task, Conversation, Message, now
from .access import get_trip
from .security import require_user
from .config import settings
from .providers import meituan, amap
from .daily_services import daily_details, synthetic_nearby, DETAIL_CACHE_SECONDS

MARKET_CACHE_SECONDS = 600
router = APIRouter(prefix="/api/v1")


def cache():
    return redis.Redis.from_url(settings.redis_url, socket_timeout=3)


def detail_key(actor, trip, version, day, mode, query="", replacing="", people=None):
    digest = hashlib.sha256(json.dumps([query, replacing, people]).encode()).hexdigest()[:16]
    return f"day-detail:{actor}:{trip}:{version}:{day}:{mode}:{digest}"


def market_quotes(actor, ident):
    """Read unmasked, parseable Meituan quotes cached for a trip or draft."""
    quotes = []
    try:
        keys = cache().keys(f"market-detail:{actor}:{ident}:*")
    except redis.RedisError:
        return quotes
    for raw_key in keys or []:
        key = raw_key.decode() if isinstance(raw_key, bytes) else str(raw_key)
        try:
            raw = cache().get(key)
        except redis.RedisError:
            continue
        if not raw:
            continue
        try:
            data = json.loads(raw)
        except (ValueError, TypeError):
            continue
        meta = data.get("market_query") or {}
        if not meta or data.get("venue_warning"):
            continue
        for item in data.get("items") or []:
            price = item.get("reference_price_cny")
            if price is None:
                continue
            quotes.append(
                {
                    "day": meta.get("day"),
                    "place_id": meta.get("place_id", ""),
                    "kind": meta.get("kind", ""),
                    "title": str(item.get("title") or "")[:200],
                    "price_cny": price,
                    "price_text": str(item.get("price_text") or "")[:100],
                    "price_basis": str(item.get("price_basis") or "参考")[:20],
                    "url": item.get("url", ""),
                }
            )
    return quotes


def day_plan(db, ident, actor, day, edit=False):
    trip = get_trip(db, ident, actor, edit=edit)
    if not trip.plan.get("days") or day > len(trip.plan["days"]):
        raise HTTPException(404, "当天行程尚未生成")
    return trip


@router.get("/trips/{ident}/daily-details")
def details(
    ident: str,
    day: int = Query(ge=1, le=14),
    mode: Literal["public_transit", "walk", "drive"] | None = None,
    query: str = Query(default="", max_length=80),
    replacing: Literal["", "breakfast", "lunch", "dinner", "hotel"] = "",
    refresh: bool = False,
    actor=Depends(require_user),
):
    with Session() as db:
        trip = day_plan(db, ident, actor, day)
        plan, version = copy.deepcopy(trip.plan), trip.version
    return plan_details(plan, ident, version, actor, day, mode, query, replacing, refresh)


def plan_details(plan, ident, version, actor, day, mode=None, query="", replacing="", refresh=False, persist=True):
    mode = mode or plan["days"][day - 1].get("transport_mode") or plan["requirements"]["transport"]
    people = plan["requirements"].get("people", 1)
    key = detail_key(actor, ident, version, day, mode, query, replacing, people)
    try:
        raw = None if refresh else cache().get(key)
        if raw:
            return json.loads(raw)
    except redis.RedisError:
        raise HTTPException(503, "吃住行资料暂存服务不可用，请稍后重试")
    result = None
    if persist and not query and not replacing and not refresh:
        with Session() as db:
            snapshot = next(
                (
                    s for s in db.scalars(
                        select(DailyDetailSnapshot).where(
                            DailyDetailSnapshot.trip_id == ident,
                            DailyDetailSnapshot.version == version,
                            DailyDetailSnapshot.day == day,
                            DailyDetailSnapshot.mode == mode,
                        )
                    ).all()
                    if s.data.get("stay", {}).get("people", 1) == people
                ),
                None,
            )
            if snapshot and snapshot.created > now() - timedelta(seconds=DETAIL_CACHE_SECONDS):
                result = snapshot.data
    if result is None:
        if replacing:
            base_key = detail_key(actor, ident, version, day, mode, people=people)
            base_raw = cache().get(base_key)
            if base_raw:
                base = json.loads(base_raw)
            else:
                with Session() as db:
                    snapshot = next(
                        (
                            s for s in db.scalars(
                                select(DailyDetailSnapshot).where(
                                    DailyDetailSnapshot.trip_id == ident,
                                    DailyDetailSnapshot.version == version,
                                    DailyDetailSnapshot.day == day,
                                    DailyDetailSnapshot.mode == mode,
                                )
                            ).all()
                            if s.data.get("stay", {}).get("people", 1) == people
                        ),
                        None,
                    )
                    base = copy.deepcopy(snapshot.data) if snapshot else None
                base = base or {**daily_details(plan, day, mode), "version": version, "trip_id": ident}
            result = copy.deepcopy(base)
            stops = plan["days"][day - 1]["stops"]
            anchor = (
                stops[-1]
                if replacing == "dinner"
                else stops[min(1, len(stops) - 1)]
                if replacing == "lunch"
                else stops[0]
            )
            kind = "stays" if replacing == "hotel" else "food"
            try:
                candidates = (
                    synthetic_nearby(result["city"], anchor, kind, replacing)
                    if plan.get("fixture")
                    else amap.search_nearby(
                        result["city"],
                        anchor["lon"],
                        anchor["lat"],
                        kind,
                        query or ("早餐" if replacing == "breakfast" else "餐厅" if kind == "food" else ""),
                    )
                )
            except Exception:
                raise HTTPException(503, "附近候选暂未查询成功，请换个关键词或稍后重试")
            if replacing == "hotel":
                result["hotels"] = candidates
            else:
                for meal in result["meals"]:
                    if meal["slot"] == replacing:
                        meal["alternatives"] = candidates
        else:
            result = {
                **daily_details(plan, day, mode, query, replacing),
                "version": version,
                "trip_id": ident,
            }
        if persist and not query and not replacing:
            with Session.begin() as db:
                current = db.get(Trip, ident, with_for_update=True)
                if current and current.version == version:
                    snapshot = db.scalar(
                        select(DailyDetailSnapshot).where(
                            DailyDetailSnapshot.trip_id == ident,
                            DailyDetailSnapshot.version == version,
                            DailyDetailSnapshot.day == day,
                            DailyDetailSnapshot.mode == mode,
                        )
                    )
                    if snapshot:
                        snapshot.data, snapshot.created = result, now()
                    else:
                        db.add(
                            DailyDetailSnapshot(
                                trip_id=ident, version=version, day=day, mode=mode, data=result
                            )
                        )
    try:
        cache().setex(key, DETAIL_CACHE_SECONDS, json.dumps(result, ensure_ascii=False))
    except redis.RedisError:
        raise HTTPException(503, "查询结果暂时无法保存，请稍后重试")
    return result


class ServiceChoice(BaseModel):
    day: int = Field(ge=1, le=14)
    base_version: int = Field(ge=1)
    slot: Literal["breakfast", "lunch", "dinner", "hotel", "transport"]
    place_id: str = Field(default="", max_length=150)
    mode: Literal["public_transit", "walk", "drive"]
    query: str = Field(default="", max_length=80)
    replacing: Literal["", "breakfast", "lunch", "dinner", "hotel"] = ""


@router.post("/trips/{ident}/service-choice")
def choose_service(ident: str, body: ServiceChoice, actor=Depends(require_user)):
    with Session.begin() as db:
        day_plan(db, ident, actor, body.day, edit=True)
        trip = db.get(Trip, ident, with_for_update=True)
        if trip.version != body.base_version:
            raise HTTPException(409, "行程已更新，请刷新后重新选择")
        plan = copy.deepcopy(trip.plan)
        if body.slot == "transport":
            plan["days"][body.day - 1]["transport_mode"] = body.mode
            message = f"第 {body.day} 天调整交通方式"
        else:
            key = detail_key(
                actor, ident, body.base_version, body.day, body.mode,
                body.query, body.replacing, plan["requirements"].get("people", 1),
            )
            try:
                raw = cache().get(key)
            except redis.RedisError:
                raise HTTPException(503, "候选资料暂不可用")
            if not raw:
                raise HTTPException(409, "候选资料已过期，请重新查询")
            result = json.loads(raw)
            candidates = (
                result["hotels"]
                if body.slot == "hotel"
                else next(m["alternatives"] for m in result["meals"] if m["slot"] == body.slot)
            )
            place = next((p for p in candidates if p["id"] == body.place_id), None)
            if not place:
                raise HTTPException(422, "请选择本次查询返回的真实候选地点")
            if body.slot == "hotel":
                plan["requirements"]["needs_accommodation"] = True
                plan["hotels"] = [h for h in plan.get("hotels", []) if h.get("city") != result["city"]] + [
                    {**place, "user_selected": True, "booking_status": "未预订"}
                ]
            else:
                current_day = plan["days"][body.day - 1]
                current_day["meals"] = [m for m in current_day.get("meals", []) if m["slot"] != body.slot] + [
                    {"slot": body.slot, "place": place, "user_selected": True}
                ]
            message = (
                f"第 {body.day} 天选择"
                + (
                    "住宿"
                    if body.slot == "hotel"
                    else {"breakfast": "早餐", "lunch": "午餐", "dinner": "晚餐"}[body.slot]
                )
                + "："
                + place["name"]
            )
        trip.plan, trip.updated = plan, now()
        trip.version += 1
        db.add(Revision(trip_id=trip.id, version=trip.version, plan=plan, message=message))
        return {"version": trip.version, "trip_id": trip.id}


def draft_plan(db, ident, label, actor, edit=False, lock=False):
    task = db.get(Task, ident)
    if not task:
        raise HTTPException(404, "草稿不存在")
    get_trip(db, task.trip_id, actor, edit=edit)
    if task.status != "waiting_choice":
        raise HTTPException(409, "该草稿已被替代或不再等待确认")
    conv_id = task.payload.get("conversation_id")
    conv = db.get(Conversation, conv_id, with_for_update=lock) if conv_id else None
    if lock:
        task = db.get(Task, ident, with_for_update=True, populate_existing=True)
        if task.status != "waiting_choice":
            raise HTTPException(409, "草稿已变化，请刷新后重试")
    if conv and conv.state.get("task_id") != task.id:
        raise HTTPException(409, "草稿正在修改，请等待最新结果")
    plan = task.result.get("variants", {}).get(label)
    if not plan:
        raise HTTPException(404, "方案不存在")
    return task, copy.deepcopy(plan)


@router.get("/tasks/{ident}/variants/{label}/daily-details")
def draft_details(
    ident: str, label: str, day: int = Query(ge=1, le=14),
    mode: Literal["public_transit", "walk", "drive"] | None = None,
    query: str = Query(default="", max_length=80),
    replacing: Literal["", "breakfast", "lunch", "dinner", "hotel"] = "",
    refresh: bool = False, actor=Depends(require_user),
):
    with Session() as db:
        task, plan = draft_plan(db, ident, label, actor)
        revision = task.result.get("draft_revision", 1)
    if day > len(plan.get("days", [])):
        raise HTTPException(404, "当天行程尚未生成")
    return plan_details(plan, f"draft:{ident}:{label}", revision, actor, day, mode, query, replacing, refresh, persist=False)


@router.post("/tasks/{ident}/variants/{label}/service-choice")
def choose_draft_service(ident: str, label: str, body: ServiceChoice, actor=Depends(require_user)):
    with Session.begin() as db:
        task, plan = draft_plan(db, ident, label, actor, edit=True, lock=True)
        revision = task.result.get("draft_revision", 1)
        if revision != body.base_version:
            raise HTTPException(409, "草稿已更新，请刷新后重新选择")
        if body.day > len(plan.get("days", [])):
            raise HTTPException(404, "当天行程尚未生成")
        current = plan["days"][body.day - 1]
        if body.slot == "transport":
            current["transport_mode"] = body.mode
        else:
            key = detail_key(
                actor, f"draft:{ident}:{label}", revision, body.day, body.mode,
                body.query, body.replacing, plan["requirements"].get("people", 1),
            )
            try:
                raw = cache().get(key)
            except redis.RedisError:
                raise HTTPException(503, "候选资料暂不可用")
            if not raw:
                raise HTTPException(409, "候选资料已过期，请重新查询")
            result = json.loads(raw)
            candidates = result["hotels"] if body.slot == "hotel" else next(
                (m["alternatives"] for m in result["meals"] if m["slot"] == body.slot), []
            )
            place = next((p for p in candidates if p["id"] == body.place_id), None)
            if not place:
                raise HTTPException(422, "请选择本次查询返回的真实候选地点")
            if body.slot == "hotel":
                plan["requirements"]["needs_accommodation"] = True
                plan["hotels"] = [h for h in plan.get("hotels", []) if h.get("city") != result["city"]] + [
                    {**place, "user_selected": True, "booking_status": "未预订"}
                ]
            else:
                current["meals"] = [m for m in current.get("meals", []) if m["slot"] != body.slot] + [
                    {"slot": body.slot, "place": place, "user_selected": True}
                ]
        task.result = {
            **task.result, "variants": {**task.result["variants"], label: plan}, "draft_revision": revision + 1,
        }
        task.updated = now()
        conv_id = task.payload.get("conversation_id")
        if conv_id and (conv := db.get(Conversation, conv_id, with_for_update=True)):
            conv.version += 1
            conv.updated = now()
            db.add(Message(conversation_id=conv_id, owner=actor, role="assistant",
                           request_key=f"draft-service:{task.id}:{revision + 1}",
                           content=f"已更新方案 {label} 第 {body.day} 天的安排，草稿已自动保存，尚未写入正式行程。"))
        return {"draft_revision": revision + 1}


@router.get("/tasks/{ident}/variants/{label}/budget")
def draft_budget(ident: str, label: str, actor=Depends(require_user)):
    from .budgeting import calculate_budget
    with Session() as db:
        task, plan = draft_plan(db, ident, label, actor)
        revision = task.result.get("draft_revision", 1)
    from .budgeting import compatible_snapshot

    snapshots = []
    for day in plan["days"]:
        mode = day.get("transport_mode") or plan["requirements"]["transport"]
        try:
            raw = cache().get(
                detail_key(
                    actor, f"draft:{ident}:{label}", revision, day["day"], mode,
                    people=plan["requirements"].get("people", 1),
                )
            )
            if raw:
                snapshots.append(json.loads(raw))
        except redis.RedisError:
            pass
        if any(compatible_snapshot(plan, day, s) for s in snapshots):
            continue
        try:
            snapshots.append(
                plan_details(
                    plan,
                    f"draft:{ident}:{label}",
                    revision,
                    actor,
                    day["day"],
                    mode,
                    persist=False,
                )
            )
        except Exception:
            continue
    quotes = market_quotes(actor, f"draft:{ident}:{label}")
    return {"version": revision, "daily_limits": {}, **calculate_budget(plan, snapshots, quotes)}


class MarketQuery(BaseModel):
    day: int = Field(ge=1, le=14)
    place_id: str = Field(min_length=1, max_length=150)
    kind: Literal["hotel", "food", "ticket"] = "hotel"


@router.post("/trips/{ident}/market-details")
def market_details(ident: str, body: MarketQuery, actor=Depends(require_user)):
    result = details(ident, day=body.day, mode=None, query="", replacing="", actor=actor)
    return market_for_details(ident, body, actor, result)


@router.post("/tasks/{ident}/variants/{label}/market-details")
def draft_market_details(ident: str, label: str, body: MarketQuery, actor=Depends(require_user)):
    result = draft_details(ident, label, day=body.day, mode=None, query="", replacing="", actor=actor)
    return market_for_details(f"draft:{ident}:{label}", body, actor, result)


def market_for_details(ident, body, actor, result):
    places = (
        result["hotels"]
        if body.kind == "hotel"
        else [entry["place"] for entry in result.get("timeline", []) if entry.get("kind") == "place"]
        if body.kind == "ticket"
        else [p for m in result["meals"] for p in m["alternatives"]]
    )
    place = next((p for p in places if p["id"] == body.place_id), None)
    if not place:
        raise HTTPException(422, "请先从当天推荐中选择地点")
    if result["fixture"]:
        return {"raw_text": "合成体验没有真实房型、菜单、价格或库存。", "booking_status": "未预订"}
    stay = result["stay"]
    question = (
        f"查询{place['name']}，地址{place['address']}，入住{stay['checkin']}，退房{stay['checkout']}，{stay['people']}人。列出可查的房型、当日价格、取消规则和官方预订入口；缺失信息明确说明。"
        if body.kind == "hotel"
        else f"查询{place['name']}，地址{place['address']}，列出该景点的门票和预约价格、开放时间与官方入口；不要编造票价，脱敏价格原样说明。"
        if body.kind == "ticket"
        else f"查询{place['name']}，地址{place['address']}，列出可查的菜品、参考消费、营业时间和商家入口；不要编造菜单和价格。"
    )
    query_hash = hashlib.sha256(question.encode()).hexdigest()
    market_key = f"market-detail:{actor}:{ident}:{query_hash}"
    market_query = {
        "ident": ident,
        "day": body.day,
        "place_id": body.place_id,
        "kind": body.kind,
        "place_name": place["name"],
    }
    try:
        cached = cache().get(market_key)
        if cached:
            data = json.loads(cached)
            data["market_query"] = market_query
            return data
    except redis.RedisError:
        pass
    try:
        response = meituan.query(result["city"], question)
        response["market_query"] = market_query
        branch = re.search(r"[（(]([^）)]+)[）)]", place["name"])
        def normalize(value):
            return re.sub(r"[^\w\u4e00-\u9fff]", "", value).lower()
        marker = branch.group(1) if branch else place["name"].replace("酒店", "")
        if normalize(marker) not in normalize(response["raw_text"]):
            response["venue_warning"] = (
                "平台返回内容未能精确匹配当前门店，请核对分店名称和地址，勿将相近门店的菜单或价格直接用于本次安排。"
            )
        try:
            cache().setex(market_key, MARKET_CACHE_SECONDS, json.dumps(response, ensure_ascii=False))
        except redis.RedisError:
            pass
        return response
    except Exception:
        raise HTTPException(503, "商品详情暂未查询成功。请通过商家地图来源或电话确认房型、菜单和当日价格。")


class IntercityQuery(BaseModel):
    origin: str = Field(min_length=1, max_length=80)
    destination: str = Field(min_length=1, max_length=80)
    departure_date: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")
    kind: Literal["train", "flight"] = "train"
    people: int = Field(default=1, ge=1, le=12)

    @field_validator("departure_date")
    @classmethod
    def actual_date(cls, value):
        return date.fromisoformat(value).isoformat()

    @field_validator("origin", "destination")
    @classmethod
    def not_blank(cls, value):
        if not value.strip():
            raise ValueError("出发地和目的地不能为空")
        return value.strip()


@router.post("/trips/{ident}/intercity-options")
def intercity_options(ident: str, body: IntercityQuery, actor=Depends(require_user)):
    with Session() as db:
        trip = get_trip(db, ident, actor)
        fixture = trip.plan.get("fixture", False)
    if fixture:
        return {
            "raw_text": "合成体验未提供真实车次、航班、余票和价格。请在真实模式查询对应日期。",
            "booking_status": "未预订",
        }
    label = "高铁或火车" if body.kind == "train" else "航班"
    try:
        return meituan.query(
            body.destination,
            f"查询{body.departure_date}从{body.origin}到{body.destination}的{label}，{body.people}位出行者。只列出实际查询得到的班次、出发和到达站点、起降或发到时间、耗时、价格、余票以及预订入口。若未到预售期或接口不支持，请明确说明，不能虚构班次或库存。",
        )
    except Exception:
        raise HTTPException(
            503, "交通商品暂未查询成功。可通过铁路12306或航空公司官网核对对应日期的班次和余票。"
        )
