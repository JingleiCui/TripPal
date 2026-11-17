"""行程数据的数据库访问边界与成员角色校验。"""

from fastapi import HTTPException
from sqlalchemy import select
from .db import Trip, TripMember
from .roles import access_role, role_can_edit


def role_for(db, trip, user_id):
    member = db.scalar(select(TripMember).where(TripMember.trip_id == trip.id, TripMember.user_id == user_id))
    return access_role(trip.owner, member.role if member else None, user_id)


def get_trip(db, ident, user_id, edit=False, owner_only=False):
    trip = db.get(Trip, ident)
    role = role_for(db, trip, user_id) if trip else None
    if not role:
        raise HTTPException(404, "行程不存在")
    if owner_only and role != "owner":
        raise HTTPException(403, "只有行程所有者可以管理成员和公开分享")
    if edit and not role_can_edit(role):
        raise HTTPException(403, "你只有查看权限")
    return trip


def safe_plan(plan, can_read_private):
    if can_read_private:
        return plan
    return {k: v for k, v in plan.items() if k not in {"knowledge", "findings"}}
