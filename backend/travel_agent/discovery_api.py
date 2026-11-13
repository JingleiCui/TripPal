"""Source-backed discovery and owner-scoped saved places; no fabricated availability."""

import hashlib
import json
from typing import Literal
import redis
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select, func
from .config import settings
from .db import Session, SavedPlace, User, now
from .security import require_user
from .providers import amap, fixtures
from .providers.base import ProviderError

# User-editable runtime limits. Search candidates expire; saved snapshots persist in SQL.
CANDIDATE_TTL_SECONDS = 1800
MAX_SAVED_PLACES = 300
CATEGORY_QUERIES = {
    "all": "景点 公园 博物馆",
    "sights": "风景名胜",
    "food": "餐饮服务",
    "stays": "酒店",
    "nature": "公园",
    "art": "博物馆 美术馆",
}
router = APIRouter(prefix="/api/v1")


def cache():
    return redis.Redis.from_url(settings.redis_url, socket_timeout=3)


def candidate_key(actor, place_id):
    return "discovery:" + actor + ":" + hashlib.sha256(place_id.encode()).hexdigest()


def saved_view(row):
    return {
        "id": row.id,
        "place": row.place,
        "collection": row.collection,
        "note": row.note,
        "created": row.created.isoformat(),
        "updated": row.updated.isoformat(),
    }


@router.get("/explore")
def explore(
    city: str = Query(min_length=1, max_length=40),
    query: str = Query(default="", max_length=100),
    category: Literal["all", "sights", "food", "stays", "nature", "art"] = "all",
    fixture: bool = False,
    actor=Depends(require_user),
):
    city, query = city.strip(), query.strip()
    if not city:
        raise HTTPException(422, "请输入目的地城市")
    if fixture and not settings.fixture_enabled:
        raise HTTPException(403, "当前环境不提供合成资料")
    try:
        if fixture:
            items = fixtures.places(city)[:6]
            if category in {"food", "stays"}:
                noun = "餐厅" if category == "food" else "酒店"
                items = [
                    {
                        **p,
                        "id": p["id"] + ":" + category,
                        "name": f"演示·{city}{noun} {i + 1}",
                        "category": "合成测试" + noun,
                    }
                    for i, p in enumerate(items)
                ]
        else:
            items = amap.search_places(
                city,
                " ".join(
                    filter(
                        None, [query, CATEGORY_QUERIES[category] if category != "all" or not query else ""]
                    )
                ),
            )
        client = cache()
        for item in items:
            client.setex(
                candidate_key(actor, item["id"]), CANDIDATE_TTL_SECONDS, json.dumps(item, ensure_ascii=False)
            )
    except ProviderError:
        raise HTTPException(503, "地点查询暂不可用，请检查地图服务配置后重试")
    except redis.RedisError:
        raise HTTPException(503, "地点暂存服务不可用，请稍后重试")
    return {
        "items": items,
        "city": city,
        "fixture": fixture,
        "notice": "合成资料仅供流程体验，不可据此出游"
        if fixture
        else "地点资料来自高德地图；营业时间、价格及预约情况请向场所核实。",
    }


@router.get("/saved-places")
def saved_places(actor=Depends(require_user)):
    with Session() as db:
        return [
            saved_view(row)
            for row in db.scalars(
                select(SavedPlace).where(SavedPlace.owner == actor).order_by(SavedPlace.updated.desc())
            )
        ]


class SavePlace(BaseModel):
    place_id: str = Field(min_length=1, max_length=120)
    collection: str = Field(default="旅行心愿单", min_length=1, max_length=60)
    note: str = Field(default="", max_length=1000)

    @field_validator("collection")
    @classmethod
    def nonblank(cls, value):
        if not value.strip():
            raise ValueError("收藏夹名称不能为空")
        return value.strip()


@router.post("/saved-places", status_code=201)
def save_place(body: SavePlace, actor=Depends(require_user)):
    with Session.begin() as db:
        # Serialize creates per owner so repeated clicks and multiple tabs stay idempotent.
        db.get(User, actor, with_for_update=True)
        row = db.scalar(
            select(SavedPlace).where(SavedPlace.owner == actor, SavedPlace.place_id == body.place_id)
        )
        if row:
            return saved_view(row)
        if (
            db.scalar(select(func.count()).select_from(SavedPlace).where(SavedPlace.owner == actor))
            >= MAX_SAVED_PLACES
        ):
            raise HTTPException(409, "收藏已达上限，请先整理收藏夹")
        try:
            raw = cache().get(candidate_key(actor, body.place_id))
        except redis.RedisError:
            raise HTTPException(503, "地点暂存服务不可用，请稍后重试")
        if not raw:
            raise HTTPException(409, "地点资料已过期，请重新搜索后收藏")
        row = SavedPlace(
            owner=actor,
            place_id=body.place_id,
            place=json.loads(raw),
            collection=body.collection,
            note=body.note,
        )
        db.add(row)
        db.flush()
        return saved_view(row)


class EditSaved(BaseModel):
    collection: str = Field(min_length=1, max_length=60)
    note: str = Field(default="", max_length=1000)

    @field_validator("collection")
    @classmethod
    def nonblank(cls, value):
        return SavePlace.nonblank(value)


def own_saved(db, ident, actor):
    row = db.get(SavedPlace, ident, with_for_update=True)
    if not row or row.owner != actor:
        raise HTTPException(404, "收藏不存在")
    return row


@router.patch("/saved-places/{ident}")
def edit_saved(ident: str, body: EditSaved, actor=Depends(require_user)):
    with Session.begin() as db:
        row = own_saved(db, ident, actor)
        row.collection, row.note, row.updated = body.collection, body.note, now()
        db.flush()
        return saved_view(row)


@router.delete("/saved-places/{ident}")
def remove_saved(ident: str, actor=Depends(require_user)):
    with Session.begin() as db:
        db.delete(own_saved(db, ident, actor))
    return {"ok": True}
