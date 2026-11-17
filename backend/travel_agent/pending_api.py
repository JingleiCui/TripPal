"""逐变更卡片确认 + 撤销窗口的 HTTP 端点。

Agent 提交修改后生成 PendingChange 卡片，用户在时间窗内可一键撤销（回到上一版本），
超时后卡片淡出但历史仍可恢复。比 interrupt 阻塞更顺滑，Agent 提交后不阻断自身，
控制权交还用户。
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from .db import Session, Trip, Revision, PendingChange, now
from .security import require_user
from .access import get_trip

router = APIRouter(prefix="/api/v1")


def _trip_view(trip):
    return {"id": trip.id, "version": trip.version, "title": trip.title, "plan": trip.plan}


def _restore(db, trip, version, message):
    revision = db.scalar(select(Revision).where(Revision.trip_id == trip.id, Revision.version == version))
    if not revision:
        raise HTTPException(404, "历史版本不存在")
    trip.plan, trip.version, trip.updated = revision.plan, trip.version + 1, now()
    db.add(Revision(trip_id=trip.id, version=trip.version, plan=trip.plan, message=message))
    return trip


@router.get("/trips/{ident}/pending-changes")
def pending_changes(ident: str, owner=Depends(require_user)):
    with Session() as db:
        get_trip(db, ident, owner)
        rows = db.scalars(
            select(PendingChange).where(PendingChange.trip_id == ident, PendingChange.status == "pending")
        ).all()
        now_t = now()
        return [
            {
                "id": r.id,
                "kind": r.kind,
                "summary": r.summary,
                "changes": r.changes,
                "expires_at": r.expires_at.isoformat(),
                "expired": r.expires_at < now_t,
                "applied_plan_version": r.applied_plan_version,
                "previous_plan_version": r.previous_plan_version,
            }
            for r in rows
        ]


@router.post("/trips/{ident}/pending-changes/{change_id}/dismiss")
def dismiss_pending(ident: str, change_id: str, owner=Depends(require_user)):
    with Session.begin() as db:
        get_trip(db, ident, owner, edit=True)
        pc = db.get(PendingChange, change_id, with_for_update=True)
        if not pc or pc.trip_id != ident or pc.status != "pending":
            raise HTTPException(404, "变更卡片不存在或已处理")
        pc.status = "dismissed"
        return {"ok": True}


@router.post("/trips/{ident}/pending-changes/{change_id}/undo")
def undo_pending(ident: str, change_id: str, owner=Depends(require_user)):
    with Session.begin() as db:
        get_trip(db, ident, owner, edit=True)
        pc = db.get(PendingChange, change_id, with_for_update=True)
        if not pc or pc.trip_id != ident or pc.status != "pending":
            raise HTTPException(404, "变更卡片不存在或已处理")
        trip = db.get(Trip, ident, with_for_update=True)
        if trip.version != pc.applied_plan_version:
            raise HTTPException(409, "行程已被其他修改覆盖，无法撤销此变更")
        if pc.previous_plan_version and pc.previous_plan_version > 0:
            _restore(db, trip, pc.previous_plan_version, f"撤销变更 {change_id[:8]}")
        else:
            trip.plan, trip.version, trip.updated = {}, trip.version + 1, now()
            db.add(
                Revision(trip_id=trip.id, version=trip.version, plan=trip.plan, message="撤销至初始空行程")
            )
        pc.status = "dismissed"
        return _trip_view(trip)
