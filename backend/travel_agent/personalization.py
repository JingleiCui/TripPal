"""Bounded behavioral hints; explicit requirements always take precedence."""

from datetime import datetime, timezone
from sqlalchemy import select
from .db import Signal, User
from .signals import aggregate_signals, render_learned_context, classify_edit_intent


def descriptors(requirements):
    text = str(requirements.get("interests", ""))
    interests = [
        name
        for word, name in [
            ("博物馆", "museums"),
            ("美食", "food"),
            ("自然", "nature"),
            ("历史", "history"),
            ("艺术", "art"),
        ]
        if word in text
    ]
    return {"interests": ",".join(interests)}


def edit_intents(text):
    result = classify_edit_intent(text)
    for word, intent in [
        ("减少步行", "less_walking"),
        ("少走路", "less_walking"),
        ("轻松", "pace_lighter"),
        ("减少安排", "pace_lighter"),
        ("省钱", "more_budget_conscious"),
        ("降低预算", "more_budget_conscious"),
        ("多些美食", "more_food"),
        ("增加博物馆", "more_museums"),
    ]:
        if word in text:
            result.append(intent)
    return list(dict.fromkeys(result))


def record(db, owner, trip_id, request_key, event_type, requirements=None, **payload):
    if not db.scalar(select(Signal.id).where(Signal.owner == owner, Signal.request_key == request_key)):
        db.add(
            Signal(
                owner=owner,
                trip_id=trip_id,
                request_key=request_key,
                event_type=event_type,
                payload={**descriptors(requirements or {}), **payload},
            )
        )


def portrait(db, owner):
    rows = db.scalars(
        select(Signal).where(Signal.owner == owner).order_by(Signal.created.desc()).limit(200)
    ).all()
    data = []
    for row in rows:
        kind = row.event_type
        if kind == "rating":
            rating = row.payload.get("rating")
            if rating is None or rating == 3:
                continue
            kind = "thumb_up" if rating >= 4 else "thumb_down"
        data.append({"event_type": kind, "payload": row.payload, "created_at": row.created})
    return aggregate_signals(data, db.get(User, owner).preferences, now=datetime.now(timezone.utc))


def advisory(db, owner):
    return render_learned_context(portrait(db, owner)) or ""
