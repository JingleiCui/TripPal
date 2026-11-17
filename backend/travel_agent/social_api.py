import asyncio
import hashlib
import json
import re
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import select, or_, delete
from .db import Session, User, Trip, TripMember, Conversation, Message, Signal, Task, Event, Revision, now
from .security import require_user
from .access import get_trip, role_for, safe_plan
from .schemas import RunRequest
from .conversation import extract, gate, seed_slots, to_requirements
from .signals import render_learned_context
from .personalization import descriptors

router = APIRouter(prefix="/api/v1")


def get_conversation(db, ident, actor, edit=False):
    conv = db.get(Conversation, ident)
    if not conv:
        raise HTTPException(404, "会话不存在")
    if conv.owner == actor:
        return conv
    if not conv.trip_id:
        raise HTTPException(404, "会话不存在")
    get_trip(db, conv.trip_id, actor, edit=edit)
    return conv


def conversation_view(db, conv):
    messages = db.scalars(
        select(Message).where(Message.conversation_id == conv.id).order_by(Message.id)
    ).all()
    task_id = conv.state.get("task_id")
    task = db.get(Task, task_id) if task_id else None
    return {
        "id": conv.id,
        "version": conv.version,
        "trip_id": conv.trip_id,
        "slots": conv.slots,
        "state": conv.state,
        "messages": [
            {
                "id": m.id,
                "role": m.role,
                "content": m.content,
                "created": m.created.isoformat(),
                "meta": m.meta,
            }
            for m in messages
        ],
        "task": {
            "id": task.id,
            "status": task.status,
            "result": {
                **task.result,
                **(
                    {"variants": {k: safe_plan(v, False) for k, v in task.result["variants"].items()}}
                    if task.result.get("variants")
                    else {}
                ),
            },
        }
        if task
        else None,
    }


class ConversationCreate(BaseModel):
    fixture: bool = False


class Turn(BaseModel):
    content: str = Field(min_length=1, max_length=4000)
    request_key: str = Field(min_length=8, max_length=80)
    version: int = Field(ge=0)
    plan_now: bool = False
    compare: bool = False
    regenerate: bool = False


@router.post("/conversations", status_code=201)
def create_conversation(body: ConversationCreate, actor=Depends(require_user)):
    from .config import settings

    if body.fixture and not settings.fixture_enabled:
        raise HTTPException(403, "当前环境不提供合成资料")
    with Session.begin() as db:
        user = db.get(User, actor)
        conv = Conversation(
            owner=actor,
            slots=seed_slots(user.preferences),
            state={"fixture": body.fixture, "asked": [], "turns": 0},
        )
        db.add(conv)
        db.flush()
        db.add(
            Message(
                conversation_id=conv.id,
                owner=actor,
                request_key="welcome",
                role="assistant",
                content="告诉我想去哪里、玩几天；你已说过的条件会保存下来。也可以直接说“开始规划”跳过可选问题。",
            )
        )
        db.flush()
        return conversation_view(db, conv)


@router.get("/conversations")
def conversations(actor=Depends(require_user)):
    with Session() as db:
        accessible = select(TripMember.trip_id).where(TripMember.user_id == actor)
        rows = db.scalars(
            select(Conversation)
            .where(or_(Conversation.owner == actor, Conversation.trip_id.in_(accessible)))
            .order_by(Conversation.updated.desc())
            .limit(100)
        )
        return [
            {
                "id": c.id,
                "trip_id": c.trip_id,
                "version": c.version,
                "slots": c.slots,
                "updated": c.updated.isoformat(),
            }
            for c in rows
        ]


@router.get("/conversations/{ident}")
def conversation(ident: str, actor=Depends(require_user)):
    with Session() as db:
        return conversation_view(db, get_conversation(db, ident, actor))


@router.post("/conversations/{ident}/turns")
def turn(ident: str, body: Turn, actor=Depends(require_user)):
    with Session() as db:
        conv = get_conversation(db, ident, actor, True)
        old_message = db.scalar(
            select(Message).where(Message.conversation_id == ident, Message.request_key == body.request_key)
        )
        if old_message:
            if old_message.content != body.content:
                raise HTTPException(409, "相同请求键不能重复提交不同文字")
            return conversation_view(db, conv)
        if conv.version != body.version:
            raise HTTPException(409, "会话已有新消息，请刷新后重试")
        snapshot = dict(conv.slots)
        state = dict(conv.state)
        active = db.get(Task, state.get("task_id")) if state.get("task_id") else None
        if active and active.status in {"queued", "running", "waiting_choice"}:
            raise HTTPException(409, "请等待本轮完成或先选择方案")
    try:
        slots, forced_key, forced_question, source = extract(
            body.content, snapshot, state.get("last_question"), state.get("fixture", False)
        )
    except Exception as exc:
        from .model_errors import classify

        failure = classify(exc)
        raise HTTPException(
            503, str(failure) if failure else "条件提取暂时失败；原有条件已保留，请重试或使用表单规划"
        )
    key, question = (
        (forced_key, forced_question)
        if forced_key
        else gate(slots, state.get("turns", 0) + 1, state.get("asked", []), body.content, body.plan_now)
    )
    with Session.begin() as db:
        conv = get_conversation(db, ident, actor, True)
        conv = db.get(Conversation, ident, with_for_update=True)
        if conv.version != body.version:
            raise HTTPException(409, "本轮处理期间会话发生变化，请刷新")
        db.add(
            Message(
                conversation_id=ident,
                owner=actor,
                request_key=body.request_key,
                role="user",
                content=body.content,
            )
        )
        conv.slots = slots
        conv.version += 1
        conv.updated = now()
        new_state = {**state, "turns": state.get("turns", 0) + 1, "last_question": key, "extraction": source}
        if key:
            new_state["asked"] = list(dict.fromkeys([*state.get("asked", []), key]))
            db.add(
                Message(
                    conversation_id=ident,
                    owner=actor,
                    request_key=body.request_key + ":reply",
                    role="assistant",
                    content=question,
                    meta={"question_key": key, "gate": "deterministic"},
                )
            )
        else:
            req = to_requirements(slots)
            trip = get_trip(db, conv.trip_id, actor, edit=True) if conv.trip_id else None
            if not trip:
                user = db.get(User, actor)
                trip = Trip(
                    owner=actor,
                    title=req.city + " · 对话规划",
                    context={"confirmed_preferences": user.preferences},
                )
                db.add(trip)
                db.flush()
                conv.trip_id = trip.id
            req.locked_ids = trip.plan.get("requirements", {}).get("locked_ids", [])
            run = RunRequest(
                trip_id=trip.id,
                base_version=trip.version,
                request_key=hashlib.sha256((ident + body.request_key).encode()).hexdigest(),
                message=body.content,
                requirements=req,
                fixture=state.get("fixture", False),
                conversation_id=ident,
                allow_undated_draft=True,
                compare=body.compare,
                regenerate=body.regenerate,
            )
            canonical = run.model_dump(mode="json")
            task = Task(
                owner=actor,
                trip_id=trip.id,
                request_key=run.request_key,
                request_hash=hashlib.sha256(json.dumps(canonical, sort_keys=True).encode()).hexdigest(),
                payload=canonical,
            )
            db.add(task)
            db.flush()
            new_state["task_id"] = task.id
            db.add(
                Message(
                    conversation_id=ident,
                    owner=actor,
                    request_key=body.request_key + ":reply",
                    role="assistant",
                    content="条件已经齐了，开始调查并检查行程。"
                    + ("将准备两种方案，选择后才会保存。" if body.compare else ""),
                    meta={"task_id": task.id},
                )
            )
        conv.state = new_state
        db.flush()
        return conversation_view(db, conv)


@router.get("/conversations/{ident}/events")
async def conversation_events(ident: str, request: Request, actor=Depends(require_user)):
    with Session() as db:
        get_conversation(db, ident, actor)
    match = re.fullmatch(r"m(\d+)-e(\d+)", request.headers.get("last-event-id", "m0-e0"))
    m_cursor, e_cursor = map(int, match.groups()) if match else (0, 0)

    async def stream():
        nonlocal m_cursor, e_cursor
        while not await request.is_disconnected():
            with Session() as db:
                try:
                    get_conversation(db, ident, actor)
                except HTTPException:
                    return
                messages = db.scalars(
                    select(Message)
                    .where(Message.conversation_id == ident, Message.id > m_cursor)
                    .order_by(Message.id)
                    .limit(100)
                ).all()
                ids = db.scalars(
                    select(Task.id).where(Task.payload["conversation_id"].as_string() == ident)
                ).all()
                tokens = (
                    db.scalars(
                        select(Event)
                        .where(
                            Event.task_id.in_(ids),
                            Event.kind.in_(["assistant_token", "assistant_reset", "variant_ready", "step"]),
                            Event.id > e_cursor,
                        )
                        .order_by(Event.id)
                        .limit(100)
                    ).all()
                    if ids
                    else []
                )
            for message in messages:
                m_cursor = message.id
                data = {
                    "id": message.id,
                    "role": message.role,
                    "content": message.content,
                    "meta": message.meta,
                }
                yield f"id: m{m_cursor}-e{e_cursor}\nevent: message\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"
            for token in tokens:
                e_cursor = token.id
                data = {**token.data, "task_id": token.task_id}
                if "plan" in data:
                    data["plan"] = safe_plan(data["plan"], False)
                kind = {
                    "assistant_token": "token",
                    "assistant_reset": "reset",
                    "variant_ready": "variant",
                    "step": "stage",
                }[token.kind]
                yield f"id: m{m_cursor}-e{e_cursor}\nevent: {kind}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"
            yield ": keepalive\n\n"
            await asyncio.sleep(1)

    return StreamingResponse(stream(), media_type="text/event-stream", headers={"X-Accel-Buffering": "no"})


class MemberInput(BaseModel):
    username: str = Field(min_length=2, max_length=60)
    role: str = Field(pattern="^(viewer|editor)$")


@router.get("/trips/{ident}/members")
def members(ident: str, actor=Depends(require_user)):
    with Session() as db:
        trip = get_trip(db, ident, actor)
        rows = db.execute(
            select(TripMember, User.name)
            .join(User, User.id == TripMember.user_id)
            .where(TripMember.trip_id == ident)
        ).all()
        return {
            "role": role_for(db, trip, actor),
            "members": [{"user_id": m.user_id, "username": name, "role": m.role} for m, name in rows],
        }


@router.put("/trips/{ident}/members")
def add_member(ident: str, body: MemberInput, actor=Depends(require_user)):
    with Session.begin() as db:
        trip = get_trip(db, ident, actor, owner_only=True)
        user = db.scalar(select(User).where(User.name == body.username))
        if not user:
            raise HTTPException(404, "该注册用户不存在")
        if user.id == trip.owner:
            raise HTTPException(409, "不能修改所有者的角色")
        member = db.scalar(
            select(TripMember).where(TripMember.trip_id == ident, TripMember.user_id == user.id)
        )
        if member:
            member.role = body.role
        else:
            db.add(TripMember(trip_id=ident, user_id=user.id, role=body.role))
    return {"ok": True}


@router.delete("/trips/{ident}/members/{user_id}")
def remove_member(ident: str, user_id: str, actor=Depends(require_user)):
    with Session.begin() as db:
        get_trip(db, ident, actor, owner_only=True)
        db.execute(delete(TripMember).where(TripMember.trip_id == ident, TripMember.user_id == user_id))
    return {"ok": True}


class FeedbackInput(BaseModel):
    event_type: str = Field(
        pattern="^(itinerary_kept|itinerary_edited|itinerary_regenerated|variant_kept|trip_opened|rating)$"
    )
    request_key: str = Field(min_length=8, max_length=100)
    rating: int | None = Field(default=None, ge=1, le=5)


@router.post("/trips/{ident}/feedback")
def feedback(ident: str, body: FeedbackInput, actor=Depends(require_user)):
    if body.event_type == "rating" and body.rating is None:
        raise HTTPException(422, "评分须为 1—5 星")
    with Session.begin() as db:
        trip = get_trip(db, ident, actor)
        if not db.scalar(
            select(Signal.id).where(Signal.owner == actor, Signal.request_key == body.request_key)
        ):
            req = trip.plan.get("requirements", {})
            interests = ",".join(
                x
                for word, x in [("博物馆", "museums"), ("美食", "food"), ("自然", "nature"), ("艺术", "art")]
                if word in req.get("interests", "")
            )
            db.add(
                Signal(
                    owner=actor,
                    trip_id=ident,
                    request_key=body.request_key,
                    event_type=body.event_type,
                    payload={"interests": interests, "rating": body.rating},
                )
            )
    return {"ok": True}


@router.get("/preferences/portrait")
def portrait(actor=Depends(require_user)):
    from .personalization import portrait as build_portrait

    with Session() as db:
        value = build_portrait(db, actor)
        return {
            "portrait": value,
            "advisory_context": render_learned_context(value),
            "notice": "启发式建议，不是机器学习模型；不得覆盖明确条件",
        }


class VariantChoice(BaseModel):
    base_version: int = Field(ge=0)


@router.post("/tasks/{ident}/variants/{label}")
def choose_variant(ident: str, label: str, body: VariantChoice, actor=Depends(require_user)):
    with Session.begin() as db:
        task = db.get(Task, ident, with_for_update=True)
        if not task:
            raise HTTPException(404, "任务不存在")
        trip = get_trip(db, task.trip_id, actor, edit=True)
        trip = db.get(Trip, trip.id, with_for_update=True)
        if task.status == "completed" and task.result.get("chosen") == label:
            return {"trip_id": trip.id, "version": trip.version, "replayed": True}
        if task.status != "waiting_choice":
            raise HTTPException(409, "任务当前不等待方案选择")
        if label not in task.result.get("variants", {}):
            raise HTTPException(422, "方案不存在")
        if trip.version != body.base_version or trip.version != task.payload["base_version"]:
            raise HTTPException(409, "行程已被更新，请重新生成或选择最新版本")
        plan = task.result["variants"][label]
        trip.version += 1
        trip.plan = plan
        trip.title = plan["title"]
        trip.updated = now()
        db.add(Revision(trip_id=trip.id, version=trip.version, plan=plan, message="选择方案 " + label))
        task.status = "completed"
        task.result = {"chosen": label, "trip_id": trip.id, "version": trip.version}
        task.updated = now()
        conv_id = task.payload.get("conversation_id")
        if conv_id:
            db.add(
                Message(
                    conversation_id=conv_id,
                    owner=actor,
                    role="assistant",
                    request_key="choice:" + task.id,
                    content="方案 " + label + " 已保存为行程版本 " + str(trip.version) + "。",
                )
            )
        db.add(
            Signal(
                owner=actor,
                trip_id=trip.id,
                request_key="choice:" + task.id,
                event_type="variant_kept",
                payload={"variant": label, **descriptors(plan.get("requirements", {}))},
            )
        )
        return {"trip_id": trip.id, "version": trip.version}
