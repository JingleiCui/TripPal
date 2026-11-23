"""Owner/editor budget settings with the same optimistic revision checks as itinerary edits."""

import copy
from decimal import Decimal
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from typing import Literal
from sqlalchemy import select
from .db import Session, Trip, Revision, DailyDetailSnapshot, now
from .security import require_user
from .access import get_trip
from .budgeting import calculate_budget, compatible_snapshot

router = APIRouter(prefix="/api/v1")


def view(db, trip):
    from .services_api import market_quotes, plan_details

    snapshots = list(
        db.scalars(
            select(DailyDetailSnapshot)
            .where(DailyDetailSnapshot.trip_id == trip.id)
            .order_by(DailyDetailSnapshot.created.desc())
        ).all()
    )
    # 方案生成后首次查看费用时自动逐日补齐吃住行快照，不再等用户点「查询并核算全程」。
    for day in trip.plan.get("days", []):
        mode = day.get("transport_mode") or trip.plan["requirements"]["transport"]
        if any(compatible_snapshot(trip.plan, day, s) for s in snapshots):
            continue
        try:
            snapshots.append(
                plan_details(trip.plan, trip.id, trip.version, trip.owner, day["day"], mode, persist=True)
            )
        except Exception:
            continue
    return {
        "version": trip.version,
        "daily_limits": trip.plan.get("budget_settings", {}).get("daily_limits", {}),
        **calculate_budget(trip.plan, snapshots, market_quotes(trip.owner, trip.id)),
    }


@router.get("/trips/{ident}/budget")
def budget(ident: str, actor=Depends(require_user)):
    with Session() as db:
        trip = get_trip(db, ident, actor)
        if not trip.plan.get("days"):
            raise HTTPException(409, "先生成每日安排，再核算费用")
        return view(db, trip)


class ExpenseUpdate(BaseModel):
    key: str = Field(min_length=1, max_length=300)
    unit_price_cny: Decimal = Field(ge=0, le=1000000, max_digits=10, decimal_places=2)
    unit: Literal["per_person", "per_room_night", "group"]
    confidence: Literal["estimated", "confirmed"] = "estimated"
    note: str = Field(default="", max_length=500)
    fingerprint: str = Field(default="", max_length=200)


class BudgetUpdate(BaseModel):
    base_version: int = Field(ge=1)
    total_limit_cny: int | None = Field(default=None, ge=1, le=1000000)
    rooms: int | None = Field(default=None, ge=1, le=12)
    daily_limits: dict[str, Decimal] = Field(default_factory=dict, max_length=14)
    expense: ExpenseUpdate | None = None
    clear_expense: str | None = Field(default=None, max_length=300)


@router.put("/trips/{ident}/budget")
def update_budget(ident: str, body: BudgetUpdate, actor=Depends(require_user)):
    with Session.begin() as db:
        get_trip(db, ident, actor, edit=True)
        trip = db.get(Trip, ident, with_for_update=True)
        if trip.version != body.base_version:
            raise HTTPException(409, "行程已更新，请刷新费用表后再保存")
        if not trip.plan.get("days"):
            raise HTTPException(409, "先生成每日安排")
        for day, value in body.daily_limits.items():
            if (
                not day.isdigit()
                or not 1 <= int(day) <= len(trip.plan["days"])
                or not value.is_finite()
                or not 0 <= value <= 1000000
            ):
                raise HTTPException(422, "当日预算须属于当前行程且金额有效")
        plan = copy.deepcopy(trip.plan)
        settings = plan.get("budget_settings", {})
        overrides = dict(settings.get("overrides", {}))
        current = view(db, trip)
        keys = {row["key"]: row for day in current["days"] for row in day["rows"]}
        if body.expense:
            if body.expense.key not in keys:
                raise HTTPException(422, "该费用项已变化，请重新核对")
            row = keys[body.expense.key]
            if body.expense.unit == "per_room_night" and row["category"] != "hotel":
                raise HTTPException(422, "只有住宿费用可以按房间每晚计价")
            if body.expense.fingerprint != row["fingerprint"]:
                raise HTTPException(409, "该费用项对应地点或路线已变化")
            overrides[body.expense.key] = body.expense.model_dump(mode="json")
        if body.clear_expense:
            overrides.pop(body.clear_expense, None)
        plan["requirements"]["budget"] = body.total_limit_cny
        plan["budget_settings"] = {
            "daily_limits": {k: str(v) for k, v in body.daily_limits.items()},
            "overrides": overrides,
        }
        if body.rooms is not None:
            plan["budget_settings"]["rooms"] = body.rooms
        elif "rooms" in settings:
            plan["budget_settings"]["rooms"] = settings["rooms"]
        snapshots = db.scalars(
            select(DailyDetailSnapshot)
            .where(DailyDetailSnapshot.trip_id == ident)
            .order_by(DailyDetailSnapshot.created.desc())
        ).all()
        trip.plan, trip.updated = plan, now()
        trip.version += 1
        for day in plan["days"]:
            snapshot = next((s for s in snapshots if compatible_snapshot(plan, day, s)), None)
            if snapshot:
                data = copy.deepcopy(snapshot.data)
                data["version"] = trip.version
                db.add(
                    DailyDetailSnapshot(
                        trip_id=ident,
                        version=trip.version,
                        day=day["day"],
                        mode=data["mode"],
                        data=data,
                        created=snapshot.created,
                    )
                )
        db.add(Revision(trip_id=trip.id, version=trip.version, plan=plan, message="核对吃住行预算与费用"))
        db.flush()
        return view(db, trip)
