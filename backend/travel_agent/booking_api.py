"""Private itinerary logistics supplied by the owner, not a booking/payment service."""

from datetime import datetime
from typing import Literal
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import select, func
from .db import Session, TravelBooking, Document, User, now
from .security import require_user
from .access import get_trip

MAX_BOOKINGS_PER_TRIP = 100
router = APIRouter(prefix="/api/v1")


class BookingInput(BaseModel):
    kind: Literal["hotel", "flight", "train", "activity", "other"]
    title: str = Field(min_length=1, max_length=150)
    start: datetime
    end: datetime | None = None
    location: str = Field(default="", max_length=300)
    reference: str = Field(default="", max_length=100)
    note: str = Field(default="", max_length=2000)
    document_id: str | None = Field(default=None, max_length=32)

    @model_validator(mode="after")
    def valid_times(self):
        self.title = self.title.strip()
        if not self.title:
            raise ValueError("请填写安排名称")
        # Local wall-clock times; timezone offsets are not accepted without an explicit location timezone.
        if self.start.tzinfo or (self.end and self.end.tzinfo):
            raise ValueError("请填写当地日期和时间，不包含时区偏移")
        if self.end and self.end < self.start:
            raise ValueError("结束时间不能早于开始时间")
        return self


def private_trip(db, ident, actor):
    trip = get_trip(db, ident, actor)
    if trip.owner != actor:
        raise HTTPException(403, "订单与凭证仅供行程创建者查看")
    return trip


def view(row):
    return {"id": row.id, "trip_id": row.trip_id, **row.details, "updated": row.updated.isoformat()}


def check_document(db, ident, actor):
    if ident:
        doc = db.get(Document, ident)
        if not doc or doc.owner != actor or doc.status == "deleted":
            raise HTTPException(404, "旅行凭证资料不存在")


@router.get("/trips/{ident}/bookings")
def bookings(ident: str, actor=Depends(require_user)):
    with Session() as db:
        private_trip(db, ident, actor)
        rows = db.scalars(
            select(TravelBooking).where(TravelBooking.trip_id == ident, TravelBooking.owner == actor)
        ).all()
        return sorted([view(row) for row in rows], key=lambda row: row["start"])


@router.post("/trips/{ident}/bookings", status_code=201)
def add_booking(ident: str, body: BookingInput, actor=Depends(require_user)):
    with Session.begin() as db:
        db.get(User, actor, with_for_update=True)
        private_trip(db, ident, actor)
        check_document(db, body.document_id, actor)
        if (
            db.scalar(select(func.count()).select_from(TravelBooking).where(TravelBooking.trip_id == ident))
            >= MAX_BOOKINGS_PER_TRIP
        ):
            raise HTTPException(409, "行程安排记录已达上限，请先整理已有记录")
        row = TravelBooking(owner=actor, trip_id=ident, details=body.model_dump(mode="json"))
        db.add(row)
        db.flush()
        return view(row)


def own_booking(db, ident, actor):
    row = db.get(TravelBooking, ident, with_for_update=True)
    if not row or row.owner != actor:
        raise HTTPException(404, "安排记录不存在")
    private_trip(db, row.trip_id, actor)
    return row


@router.put("/bookings/{ident}")
def edit_booking(ident: str, body: BookingInput, actor=Depends(require_user)):
    with Session.begin() as db:
        row = own_booking(db, ident, actor)
        check_document(db, body.document_id, actor)
        row.details, row.updated = body.model_dump(mode="json"), now()
        db.flush()
        return view(row)


@router.delete("/bookings/{ident}")
def remove_booking(ident: str, actor=Depends(require_user)):
    with Session.begin() as db:
        db.delete(own_booking(db, ident, actor))
    return {"ok": True}
