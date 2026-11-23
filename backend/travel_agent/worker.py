"""Durable SQL receipts + leased workers. Broker delivery is at least once."""

import threading
import copy
from datetime import timedelta
from celery import Celery
from langgraph.checkpoint.mysql.pymysql import PyMySQLSaver
from langgraph.types import Command
from sqlalchemy import select, update
from .observability import logger
from .config import settings
from .db import Session, Task, Trip, Revision, Document, Message, Conversation, User, uid, now, event, PendingChange
from .access import role_for
from .roles import role_can_edit
from .agent.harness import Harness, Cancelled
from .agent.graph import build_graph
from .providers.base import ProviderError
from . import knowledge
from .personalization import advisory, record, edit_intents

celery = Celery("travel_agent", broker=settings.broker_url)
celery.conf.update(
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    task_reject_on_worker_lost=True,
    broker_transport_options={"visibility_timeout": 900},
    task_ignore_result=True,
    broker_connection_retry_on_startup=True,
    task_serializer="json",
    accept_content=["json"],
)


def acquire(task_id):
    with Session.begin() as db:
        task = db.get(Task, task_id, with_for_update=True)
        if not task or task.status not in {"queued", "running"}:
            return None
        if task.status == "running" and task.lease_until and task.lease_until > now():
            return None
        trip = db.get(Trip, task.trip_id)
        if not trip or not role_can_edit(role_for(db, trip, task.owner)):
            task.status = "cancelled"
            task.result = {"error": "已无行程编辑权限"}
            return None
        lease = uid()
        task.status, task.lease, task.lease_until = "running", lease, now() + timedelta(seconds=90)
        task.payload = {**task.payload, "execution_attempt": task.payload.get("execution_attempt", 0) + 1}
        task.updated = now()
        return lease, dict(task.payload)


def heartbeat(task_id, lease, stop):
    while not stop.wait(15):
        try:
            with Session.begin() as db:
                db.execute(
                    update(Task)
                    .where(Task.id == task_id, Task.lease == lease, Task.status == "running")
                    .values(lease_until=now() + timedelta(seconds=90), updated=now())
                )
        except Exception:
            # Loss of the lease is checked again before every tool and final commit.
            logger.warning(
                "lease_heartbeat_failed task_id=%s", task_id, exc_info=True
            )


@celery.task(name="travel.execute")
def execute(task_id):
    acquired = acquire(task_id)
    if not acquired:
        return
    lease, payload = acquired
    stop = threading.Event()
    thread = threading.Thread(target=heartbeat, args=(task_id, lease, stop), daemon=True)
    thread.start()
    try:
        with Session() as db:
            task = db.get(Task, task_id)
            trip = db.get(Trip, task.trip_id)
            from .notes.api import confirmed_context
            current_notes = confirmed_context(db, task.owner, payload.get("attachment_ids", []))
            if current_notes != payload.get("note_sources", []):
                raise ProviderError("source_changed", "攻略资料已变化，请重新确认后规划")
            state = {
                "owner": task.owner,
                "requirements": payload["requirements"],
                "message": payload["message"],
                "fixture": payload["fixture"],
                "fixture_model": payload.get("fixture_model", False),
                "strategy": payload["strategy"],
                "old_plan": payload.get("draft_plan") or trip.plan,
                "context": {
                    **trip.context,
                    "note_sources": current_notes,
                    "confirmed_preferences": db.get(User, task.owner).preferences,
                    "advisory_portrait": advisory(db, task.owner),
                },
                "allow_undated_draft": payload.get("allow_undated_draft", False),
                "compare": payload.get("compare", False),
                "conversation_draft": bool(payload.get("conversation_id")),
                "regenerate": payload.get("regenerate", False),
            }
        harness = Harness(task_id, lease, capabilities=payload.get("capabilities"))
        with PyMySQLSaver.from_conn_string(settings.checkpoint_url) as saver:
            graph = build_graph(saver, harness)
            config = {"configurable": {"thread_id": task_id}, "recursion_limit": 30}
            snapshot = graph.get_state(config)
            if snapshot.values:
                value = Command(resume=payload["resume"]) if payload.get("resume") else None
            else:
                value = state
            output = graph.invoke(value, config)
            pending = graph.get_state(config)
        harness.check()
        with Session() as note_db:
            if confirmed_context(note_db, state["owner"], payload.get("attachment_ids", [])) != current_notes:
                raise ProviderError("source_changed", "攻略资料已变化，本次结果未写入")
        with Session.begin() as db:
            task = db.get(Task, task_id, with_for_update=True)
            if not task or task.lease != lease or task.status != "running" or task.lease_until < now():
                return
            if pending.next:
                task.status = "waiting_input"
                task.result = {"interrupts": [i.value for t in pending.tasks for i in t.interrupts]}
            else:
                trip = db.get(Trip, task.trip_id, with_for_update=True)
                if not trip or not role_can_edit(role_for(db, trip, task.owner)):
                    task.status = "cancelled"
                    task.result = {"error": "当前已无行程编辑权限，结果未写入"}
                elif trip.version != payload["base_version"]:
                    task.status = "conflict"
                    task.result = {"error": "行程已有新版本，结果没有覆盖当前行程，请重新加载后修改"}
                elif output.get("variants") or payload.get("conversation_id"):
                    variants = output.get("variants") or {"A": output["plan"]}
                    # Explicit meal/hotel selections survive conversational edits in the same city.
                    old = payload.get("draft_plan") or trip.plan
                    for candidate in variants.values():
                        if old.get("budget_settings"):
                            candidate["budget_settings"] = copy.deepcopy(old["budget_settings"])
                        selected_hotels = [h for h in old.get("hotels", []) if h.get("user_selected")]
                        if candidate["requirements"].get("needs_accommodation") is not False:
                            cities = {d.get("city") or candidate["requirements"]["city"] for d in candidate["days"]}
                            selected_hotels = [h for h in selected_hotels if h.get("city") in cities]
                            candidate["hotels"] = [h for h in candidate.get("hotels", []) if h.get("city") not in {p.get("city") for p in selected_hotels}] + copy.deepcopy(selected_hotels)
                        for day in candidate["days"]:
                            old_day = next((d for d in old.get("days", []) if d["day"] == day["day"] and
                                            (d.get("city") or old.get("requirements", {}).get("city")) ==
                                            (day.get("city") or candidate["requirements"]["city"])), None)
                            if old_day:
                                day["meals"] = copy.deepcopy(old_day.get("meals", []))
                                if old.get("requirements", {}).get("transport") == candidate["requirements"].get("transport") and old_day.get("transport_mode"):
                                    day["transport_mode"] = old_day["transport_mode"]
                    task.status = "waiting_choice"
                    task.result = {
                        "variants": variants,
                        "draft_revision": 1,
                        "requested_count": 2 if payload.get("compare") else 1,
                        "missing_variant_reason": output.get("missing_variant_reason"),
                        "trip_id": trip.id,
                        "base_version": trip.version,
                    }
                else:
                    plan = output["plan"]
                    trip.version += 1
                    trip.plan, trip.title, trip.updated = plan, plan["title"], now()
                    trip.context = {
                        "goal": payload["message"],
                        "constraints": output["requirements"],
                        "pending": plan["warnings"],
                        "confirmed_preferences": trip.context.get("confirmed_preferences", {}),
                    }
                    db.add(
                        Revision(trip_id=trip.id, version=trip.version, plan=plan, message=payload["message"])
                    )
                    # 逐变更卡片确认 + 撤销窗口：提交即生成可撤销卡片，而非阻塞中断。
                    diff = plan.get("diff") or {"added": [], "removed": [], "retained": []}
                    db.add(
                        PendingChange(
                            trip_id=trip.id,
                            task_id=task.id,
                            owner=task.owner,
                            kind="plan_edit",
                            summary=f"已更新行程：新增 {len(diff.get('added', []))} 处、移除 {len(diff.get('removed', []))} 处",
                            changes={"diff": diff, "title": plan.get("title", "")},
                            applied_plan_version=trip.version,
                            previous_plan_version=payload["base_version"],
                            expires_at=now() + timedelta(minutes=settings.pending_change_ttl_minutes),
                            status="pending",
                        )
                    )
                    if payload.get("regenerate") or payload["base_version"]:
                        record(
                            db,
                            task.owner,
                            trip.id,
                            "task:" + task.id,
                            "itinerary_regenerated" if payload.get("regenerate") else "itinerary_edited",
                            payload["requirements"],
                            edit_intents=edit_intents(payload["message"]),
                        )
                    task.status = "completed"
                    task.result = {"trip_id": trip.id, "version": trip.version, "warnings": plan["warnings"]}
                if task.status == "waiting_choice" and payload.get("previous_draft_task_id"):
                    previous = db.get(Task, payload["previous_draft_task_id"], with_for_update=True)
                    if previous and previous.status == "waiting_choice":
                        previous.status = "superseded"
                        previous.result = {**previous.result, "superseded_by": task.id}
                if payload.get("conversation_id"):
                    conv = db.get(Conversation, payload["conversation_id"])
                    if conv:
                        reply = output.get("assistant_reply") or (
                            "草稿已准备好，可继续修改或确认保存。"
                            if task.status == "waiting_choice"
                            else "行程已生成；请查看地图、每日安排和待确认事项。"
                            if task.status == "completed"
                            else task.result.get("error", "任务结束")
                        )
                        db.add(
                            Message(
                                conversation_id=conv.id,
                                owner=task.owner,
                                request_key="task:" + task.id,
                                role="assistant",
                                content=reply,
                                meta={"task_id": task.id, "status": task.status},
                            )
                        )
            final_status = task.status
            task.lease, task.lease_until, task.updated = None, None, now()
        event(task_id, "finished", status=final_status)
    except Cancelled:
        pass
    except Exception as exc:
        code = exc.code if isinstance(exc, ProviderError) else "execution_failed"
        message = (
            str(exc)[:400]
            if isinstance(exc, (ProviderError, ValueError))
            else f"执行失败（{type(exc).__name__}），请查看执行记录并重试"
        )
        with Session.begin() as db:
            task = db.get(Task, task_id, with_for_update=True)
            if task and task.lease == lease and task.status == "running":
                task.status = "awaiting_credentials" if code == "credentials" else "failed"
                task.result = {"code": code, "error": message}
                task.lease, task.lease_until, task.updated = None, None, now()
                conv_id = payload.get("conversation_id")
                if conv_id and (conv := db.get(Conversation, conv_id, with_for_update=True)):
                    previous = db.get(Task, payload.get("previous_draft_task_id")) if payload.get("previous_draft_task_id") else None
                    if conv.state.get("task_id") == task.id and previous and previous.status == "waiting_choice":
                        conv.state = {**conv.state, "task_id": previous.id}
                    conv.version += 1
                    conv.updated = now()
                    db.add(Message(conversation_id=conv_id, owner=task.owner, request_key="error:" + task.id,
                                   role="assistant", content=message + ("。上一份草稿已保留，可继续修改。" if previous else "。请重试。"),
                                   meta={"task_id": task.id, "status": task.status}))
        event(task_id, "error", code=code, error=message)
    finally:
        stop.set()
        event(task_id, "worker_stopped", lease=lease)


@celery.task(name="travel.index")
def index_document(doc_id):
    import redis

    client = redis.Redis.from_url(settings.redis_url)
    # redis lock is a scheduling guard, DB visibility determines retrieval access.
    lock = client.lock("doc-index:" + doc_id, timeout=900, blocking_timeout=0)
    if lock.acquire(blocking=False):
        try:
            knowledge.index_document(doc_id)
        finally:
            try:
                lock.release()
            except redis.RedisError:
                pass


def dispatch_pending():
    from pathlib import Path

    if (Path(settings.data_dir) / "maintenance").exists():
        return
    with Session() as db:
        task_ids = db.scalars(
            select(Task.id)
            .where((Task.status == "queued") | ((Task.status == "running") & (Task.lease_until < now())))
            .limit(50)
        ).all()
        docs = db.scalars(
            select(Document.id).where(Document.status.in_(["queued", "indexing"])).limit(10)
        ).all()
    for task_id in task_ids:
        execute.apply_async(args=[task_id], retry=False)
    for doc_id in docs:
        index_document.apply_async(args=[doc_id], retry=False)
