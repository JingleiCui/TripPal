import hashlib
import json
import redis
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from .db import Session, Trip, Revision, now
from .security import require_user
from .access import get_trip
from .schemas import Requirements, day_cities
from .config import settings
from .providers import amap, fixtures
from .providers.base import ProviderError

HOTEL_PAGE_SIZE = 20

router = APIRouter(prefix="/api/v1")


def choice_key(actor, trip, city, ident):
    return (
        "hotelchoice:" + actor + ":" + trip + ":" + hashlib.sha256((city + "\0" + ident).encode()).hexdigest()
    )


@router.get("/trips/{ident}/hotels")
def hotels(
    ident: str, query: str, city: str = "",
    page: int = Query(default=1, ge=1, le=amap.SEARCH_MAX_RESULTS),
    page_size: int = Query(default=HOTEL_PAGE_SIZE, ge=1, le=amap.SEARCH_MAX_PAGE_SIZE),
    actor=Depends(require_user),
):
    if not query.strip() or len(query) > 100:
        raise HTTPException(422, "请输入简短的酒店名称或区域")
    start = (page - 1) * page_size
    if start >= amap.SEARCH_MAX_RESULTS:
        raise HTTPException(422, "已超出可浏览范围，请细化酒店名称或区域")
    with Session() as db:
        trip = get_trip(db, ident, actor)
        if not trip.plan:
            raise HTTPException(409, "先生成一份行程")
        req = Requirements(**trip.plan["requirements"])
        city = city or req.city
        if city not in day_cities(req):
            raise HTTPException(422, "酒店必须属于当前行程城市")
        if trip.plan.get("fixture"):
            candidates = [
                {
                    **p,
                    "id": f"fixture-hotel:{city}:{i}",
                    "name": f"演示·{city}旅居酒店 {i + 1}",
                    "category": "合成测试酒店",
                }
                for i, p in enumerate(fixtures.discovery_places(city, "stays"))
            ]
            has_more = start + page_size < len(candidates)
            candidates = candidates[start : start + page_size]
            pagination = {"next_page": page + 1 if has_more else None, "has_more": has_more}
        else:
            try:
                pagination = amap.search_places_page(city, query.strip(), types="100000", page=page, page_size=page_size)
                candidates = pagination.pop("items")
            except ProviderError:
                raise HTTPException(503, "酒店地点查询暂不可用，请检查高德配置")
    client = redis.Redis.from_url(settings.redis_url, socket_timeout=3)
    try:
        for item in candidates:
            client.setex(
                choice_key(actor, ident, city, item["id"]), 600, json.dumps(item, ensure_ascii=False)
            )
    except redis.RedisError:
        raise HTTPException(503, "候选保存暂不可用，请稍后再试")
    return {**pagination, "items": candidates, "page": page, "page_size": page_size, "notice": "选择只用于行程与地图，不代表已预订；价格仍以预订平台为准"}


class HotelChoice(BaseModel):
    place_id: str = Field(min_length=1, max_length=100)
    city: str = Field(min_length=1, max_length=40)
    base_version: int = Field(ge=1)


@router.post("/trips/{ident}/hotel")
def select_hotel(ident: str, body: HotelChoice, actor=Depends(require_user)):
    try:
        raw = redis.Redis.from_url(settings.redis_url, socket_timeout=3).get(
            choice_key(actor, ident, body.city, body.place_id)
        )
    except redis.RedisError:
        raise HTTPException(503, "候选服务不可用")
    if not raw:
        raise HTTPException(409, "酒店候选已失效，请重新查询后选择")
    hotel = json.loads(raw)
    with Session.begin() as db:
        get_trip(db, ident, actor, edit=True)
        trip = db.get(Trip, ident, with_for_update=True)
        if trip.version != body.base_version:
            raise HTTPException(409, "行程已更新，请刷新再选择酒店")
        plan = json.loads(json.dumps(trip.plan))
        hotels = [h for h in plan.get("hotels", []) if h["city"] != body.city]
        plan["requirements"]["needs_accommodation"] = True
        plan["hotels"] = [*hotels, {**hotel, "user_selected": True, "booking_status": "未预订"}]
        trip.plan = plan
        trip.version += 1
        trip.updated = now()
        db.add(Revision(trip_id=trip.id, version=trip.version, plan=plan, message="选择住宿地点（未预订）"))
        return {"trip_id": trip.id, "version": trip.version, "hotel": hotel}
