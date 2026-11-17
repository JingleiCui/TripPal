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
from .db import Session, Trip, Revision, DailyDetailSnapshot, now
from .access import get_trip
from .security import require_user
from .config import settings
from .providers import meituan, amap
from .daily_services import daily_details, synthetic_nearby, DETAIL_CACHE_SECONDS

MARKET_CACHE_SECONDS = 600
router = APIRouter(prefix="/api/v1")


def cache():
    return redis.Redis.from_url(settings.redis_url, socket_timeout=3)


def detail_key(actor, trip, version, day, mode, query="", replacing=""):
    digest = hashlib.sha256(json.dumps([query, replacing]).encode()).hexdigest()[:16]
    return f"day-detail:{actor}:{trip}:{version}:{day}:{mode}:{digest}"


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
    mode = mode or plan["days"][day - 1].get("transport_mode") or plan["requirements"]["transport"]
    key = detail_key(actor, ident, version, day, mode, query, replacing)
    try:
        raw = None if refresh else cache().get(key)
        if raw:
            return json.loads(raw)
    except redis.RedisError:
        raise HTTPException(503, "吃住行资料暂存服务不可用，请稍后重试")
    result = None
    if not query and not replacing and not refresh:
        with Session() as db:
            snapshot = db.scalar(
                select(DailyDetailSnapshot).where(
                    DailyDetailSnapshot.trip_id == ident,
                    DailyDetailSnapshot.version == version,
                    DailyDetailSnapshot.day == day,
                    DailyDetailSnapshot.mode == mode,
                )
            )
            if snapshot and snapshot.created > now() - timedelta(seconds=DETAIL_CACHE_SECONDS):
                result = snapshot.data
    if result is None:
        if replacing:
            base_key = detail_key(actor, ident, version, day, mode)
            base_raw = cache().get(base_key)
            if base_raw:
                base = json.loads(base_raw)
            else:
                with Session() as db:
                    snapshot = db.scalar(
                        select(DailyDetailSnapshot).where(
                            DailyDetailSnapshot.trip_id == ident,
                            DailyDetailSnapshot.version == version,
                            DailyDetailSnapshot.day == day,
                            DailyDetailSnapshot.mode == mode,
                        )
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
        if not query and not replacing:
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
            key = detail_key(actor, ident, body.base_version, body.day, body.mode, body.query, body.replacing)
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


class MarketQuery(BaseModel):
    day: int = Field(ge=1, le=14)
    place_id: str = Field(min_length=1, max_length=150)
    kind: Literal["hotel", "food"] = "hotel"


@router.post("/trips/{ident}/market-details")
def market_details(ident: str, body: MarketQuery, actor=Depends(require_user)):
    result = details(ident, day=body.day, mode=None, query="", replacing="", actor=actor)
    places = (
        result["hotels"] if body.kind == "hotel" else [p for m in result["meals"] for p in m["alternatives"]]
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
        else f"查询{place['name']}，地址{place['address']}，列出可查的菜品、参考消费、营业时间和商家入口；不要编造菜单和价格。"
    )
    query_hash = hashlib.sha256(question.encode()).hexdigest()
    market_key = f"market-detail:{actor}:{ident}:{query_hash}"
    try:
        cached = cache().get(market_key)
        if cached:
            return json.loads(cached)
    except redis.RedisError:
        pass
    try:
        response = meituan.query(result["city"], question)
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
