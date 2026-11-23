"""Account, privacy and optional analytics. Mail stays in local SMTP by default."""

import io
import json
import zipfile
from datetime import timedelta
from pathlib import Path
import httpx
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import select, delete, update
from langgraph.checkpoint.mysql.pymysql import PyMySQLSaver
from .db import (
    Session,
    SavedPlace,
    DailyDetailSnapshot,
    TravelBooking,
    PrivacyCleanup,
    User,
    AccountProfile,
    AuthToken,
    MailOutbox,
    LoginSession,
    Trip,
    TripMember,
    Task,
    Event,
    Document,
    Conversation,
    Message,
    Signal,
    Share,
    Revision,
    now,
)
from .security import require_user, hash_token, password_hash, password_valid
from .mailer import queue_token
from .config import settings

router = APIRouter(prefix="/api/v1")


class EmailInput(BaseModel):
    email: EmailStr


class TokenInput(BaseModel):
    token: str = Field(min_length=20, max_length=256)


class ResetInput(TokenInput):
    password: str = Field(min_length=6, max_length=100)


def valid_token(db, value, purpose):
    token = db.get(AuthToken, hash_token(value), with_for_update=True)
    if not token or token.purpose != purpose or token.consumed or token.expires < now():
        raise HTTPException(400, "链接已过期、无效或已经使用")
    return token


@router.post("/auth/verify-email")
def verify_email(body: TokenInput):
    with Session.begin() as db:
        token = valid_token(db, body.token, "verify")
        profile = db.get(AccountProfile, token.owner, with_for_update=True)
        if not profile:
            raise HTTPException(400, "账户不存在")
        profile.email_verified = 1
        db.execute(
            update(AuthToken)
            .where(AuthToken.owner == token.owner, AuthToken.purpose == "verify")
            .values(consumed=1)
        )
    return {"ok": True, "message": "邮箱已验证，可以返回工作台"}


@router.post("/auth/resend-verification")
def resend(request: Request, actor=Depends(require_user)):
    from .api import throttle_login

    throttle_login(request)
    with Session.begin() as db:
        profile = db.get(AccountProfile, actor)
        if not profile or not profile.email:
            raise HTTPException(409, "当前账户未填写邮箱")
        if not profile.email_verified:
            queue_token(db, actor, "verify")
    return {"ok": True, "message": "验证邮件已进入投递队列；本机开发请打开本地收件箱"}


@router.post("/auth/forgot-password")
def forgot_password(body: EmailInput, request: Request):
    from .api import throttle_login

    throttle_login(request)
    with Session.begin() as db:
        profile = db.scalar(select(AccountProfile).where(AccountProfile.email == str(body.email).lower()))
        if profile:
            queue_token(db, profile.owner, "reset")
    return {"ok": True, "message": "如果该邮箱对应账户，重置链接已进入邮件投递队列"}


@router.post("/auth/reset-password")
def reset_password(body: ResetInput):
    with Session.begin() as db:
        token = valid_token(db, body.token, "reset")
        user = db.get(User, token.owner, with_for_update=True)
        if not user:
            raise HTTPException(400, "账户不存在")
        user.password = password_hash(body.password)
        db.execute(
            update(AuthToken)
            .where(AuthToken.owner == token.owner, AuthToken.purpose == "reset")
            .values(consumed=1)
        )
        db.execute(delete(LoginSession).where(LoginSession.owner == token.owner))
    return {"ok": True, "message": "密码已更新，所有旧登录已失效，请重新登录"}


class ConsentInput(BaseModel):
    analytics: bool


@router.put("/privacy/consent")
def consent(body: ConsentInput, actor=Depends(require_user)):
    with Session.begin() as db:
        profile = db.get(AccountProfile, actor)
        if not profile:
            profile = AccountProfile(owner=actor)
            db.add(profile)
        profile.consent = {"decided": True, "analytics": body.analytics, "updated": now().isoformat()}
    return {"ok": True, "analytics": body.analytics}


def analytics_config(actor):
    with Session() as db:
        profile = db.get(AccountProfile, actor)
        allowed = bool(profile and profile.consent.get("analytics") is True and settings.posthog_key)
    return {
        "enabled": allowed,
        "notice": "只有明确同意并配置项目 write key 才发送统计；未满足时不加载 SDK、不发请求",
    }


@router.get("/privacy/analytics")
def analytics_status(actor=Depends(require_user)):
    return analytics_config(actor)


class AnalyticsInput(BaseModel):
    event: str = Field(
        pattern="^(conversation_started|plan_requested|plan_selected|trip_opened|roadbook_exported)$"
    )


@router.post("/privacy/analytics")
def analytics_event(body: AnalyticsInput, actor=Depends(require_user)):
    if not analytics_config(actor)["enabled"]:
        return {"sent": False, "reason": "consent_or_key_missing"}
    if settings.posthog_host not in {"https://us.i.posthog.com", "https://eu.i.posthog.com"}:
        raise HTTPException(503, "统计服务地址未获准")
    # No email, query, document, itinerary, location or message content is sent.
    try:
        with httpx.Client(timeout=3) as client:
            result = client.post(
                settings.posthog_host + "/capture/",
                json={
                    "api_key": settings.posthog_key,
                    "event": body.event,
                    "properties": {
                        "distinct_id": hash_token(actor + settings.posthog_key),
                        "source": "travel_agent",
                    },
                },
            )
        return {"sent": result.is_success}
    except httpx.HTTPError:
        return {"sent": False, "reason": "temporarily_unavailable"}


@router.get("/privacy/export")
def export_personal_data(actor=Depends(require_user)):
    with Session() as db:
        user = db.get(User, actor)
        profile = db.get(AccountProfile, actor)
        trips = db.scalars(select(Trip).where(Trip.owner == actor)).all()
        sessions = db.scalars(select(Conversation).where(Conversation.owner == actor)).all()
        messages = db.scalars(select(Message).where(Message.owner == actor)).all()
        docs = db.scalars(select(Document).where(Document.owner == actor, Document.status != "deleted")).all()
        tasks = db.scalars(select(Task).where(Task.owner == actor)).all()
        signals = db.scalars(select(Signal).where(Signal.owner == actor)).all()
        data = {
            "schema": "travel_agent.personal-export.v1",
            "exported_at": now().isoformat(),
            "account": {
                "username": user.name,
                "email": profile.email if profile else None,
                "preferences": user.preferences,
                "consent": profile.consent if profile else {},
            },
            "daily_details": [
                row.data
                for row in db.scalars(
                    select(DailyDetailSnapshot).where(DailyDetailSnapshot.trip_id.in_([t.id for t in trips]))
                )
            ],
            "bookings": [
                {"id": row.id, "trip_id": row.trip_id, **row.details}
                for row in db.scalars(select(TravelBooking).where(TravelBooking.owner == actor))
            ],
            "saved_places": [
                {"id": row.id, "place": row.place, "collection": row.collection, "note": row.note}
                for row in db.scalars(select(SavedPlace).where(SavedPlace.owner == actor))
            ],
            "trips": [{"id": t.id, "title": t.title, "version": t.version, "plan": t.plan} for t in trips],
            "revisions": [
                {"trip_id": r.trip_id, "version": r.version, "plan": r.plan}
                for r in db.scalars(select(Revision).where(Revision.trip_id.in_([t.id for t in trips])))
            ],
            "conversations": [
                {"id": c.id, "slots": c.slots, "state": c.state, "trip_id": c.trip_id} for c in sessions
            ],
            "messages": [
                {
                    "conversation_id": m.conversation_id,
                    "role": m.role,
                    "content": m.content,
                    "created": m.created.isoformat(),
                }
                for m in messages
            ],
            "tasks": [
                {"id": t.id, "status": t.status, "payload": t.payload, "result": t.result} for t in tasks
            ],
            "signals": [
                {"event_type": s.event_type, "payload": s.payload, "created": s.created.isoformat()}
                for s in signals
            ],
            "documents": [
                {"id": d.id, "name": d.name, "digest": d.digest, "version": d.version} for d in docs
            ],
        }
        from .db import Attachment
        notes = db.scalars(select(Attachment).where(Attachment.owner == actor, Attachment.kind == "travel_note")).all()
        data["note_imports"] = [{"id": n.id, "name": n.name, "parsed": n.parsed} for n in notes]
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            archive.writestr("personal-data.json", json.dumps(data, ensure_ascii=False, indent=2))
            from .notes.jobs import directory
            for note in notes:
                for image in note.parsed.get("images", []):
                    if image.get("file"):
                        image_path = directory(actor, note.id) / image["file"]
                        if image_path.is_file():
                            archive.write(image_path, arcname=f"notes/{note.id}/{image['id']}")
            for doc in docs:
                path = Path(settings.data_dir) / "uploads" / doc.id
                if path.is_file():
                    archive.write(path, arcname="documents/" + doc.id + "/" + Path(doc.name).name)
    return Response(
        buf.getvalue(),
        media_type="application/zip",
        headers={"Content-Disposition": 'attachment; filename="travel-agent-personal-data.zip"'},
    )


class DeleteAccountInput(BaseModel):
    password: str = Field(min_length=1, max_length=100)
    confirmation: str = Field(min_length=1, max_length=100)


@router.delete("/privacy/account")
def delete_account(body: DeleteAccountInput, response: Response, actor=Depends(require_user)):
    with Session.begin() as db:
        user = db.get(User, actor, with_for_update=True)
        if not user or not password_valid(body.password, user.password) or body.confirmation != user.name:
            raise HTTPException(403, "请输入正确密码和用户名确认注销")
        owned_trip_ids = db.scalars(select(Trip.id).where(Trip.owner == actor)).all()
        tasks = db.scalars(
            select(Task).where((Task.owner == actor) | (Task.trip_id.in_(owned_trip_ids)))
        ).all()
        for task in tasks:
            if task.status == "running":
                raise HTTPException(409, "仍有执行中任务，请先取消并等待执行器退出后再注销")
            if task.status == "cancelled" and task.updated > now() - timedelta(
                seconds=settings.task_budget_seconds
            ):
                started = db.scalar(
                    select(Event.id).where(Event.task_id == task.id, Event.kind == "model_start").limit(1)
                )
                stopped = db.scalar(
                    select(Event.id).where(Event.task_id == task.id, Event.kind == "worker_stopped").limit(1)
                )
                if started and not stopped:
                    raise HTTPException(409, "已取消任务的执行器仍在退出，请稍后再注销")
        task_ids = [t.id for t in tasks]
        docs = db.scalars(select(Document).where(Document.owner == actor)).all()
        doc_ids = [d.id for d in docs]
        conv_ids = db.scalars(
            select(Conversation.id).where(
                (Conversation.owner == actor) | (Conversation.trip_id.in_(owned_trip_ids))
            )
        ).all()
        # No active writer remains; checkpoints are removed before deleting business rows.
        with PyMySQLSaver.from_conn_string(settings.checkpoint_url) as saver:
            for ident in task_ids:
                saver.delete_thread(ident)
        db.execute(delete(Event).where(Event.task_id.in_(task_ids)))
        db.execute(delete(Task).where(Task.id.in_(task_ids)))
        db.execute(delete(Message).where((Message.owner == actor) | (Message.conversation_id.in_(conv_ids))))
        db.execute(delete(Conversation).where(Conversation.id.in_(conv_ids)))
        db.execute(delete(Revision).where(Revision.trip_id.in_(owned_trip_ids)))
        db.execute(
            delete(TripMember).where((TripMember.user_id == actor) | (TripMember.trip_id.in_(owned_trip_ids)))
        )
        db.execute(delete(Share).where((Share.owner == actor) | (Share.trip_id.in_(owned_trip_ids))))
        db.execute(delete(Signal).where((Signal.owner == actor) | (Signal.trip_id.in_(owned_trip_ids))))
        db.execute(delete(DailyDetailSnapshot).where(DailyDetailSnapshot.trip_id.in_(owned_trip_ids)))
        db.execute(delete(TravelBooking).where(TravelBooking.trip_id.in_(owned_trip_ids)))
        db.execute(delete(Trip).where(Trip.id.in_(owned_trip_ids)))
        for model in (SavedPlace, Document, LoginSession, AuthToken, MailOutbox, AccountProfile):
            db.execute(delete(model).where(model.owner == actor))
        cleanup = PrivacyCleanup(owner=actor, document_ids=doc_ids)
        db.add(cleanup)
        db.flush()
        cleanup_id = cleanup.id
        db.delete(user)
    from .privacy_cleanup import process_pending

    process_pending()
    with Session() as db:
        cleanup_pending = db.get(PrivacyCleanup, cleanup_id).status != "done"
    response.delete_cookie("travel_session")
    return {
        "deleted": True,
        "external_cleanup_pending": cleanup_pending,
        "notice": "已注销账户及业务数据；索引服务不可用时由持久队列继续清理。过往离线备份按独立保留策略处理，不会因注销自动改写备份文件",
    }


@router.delete("/preferences/portrait")
def clear_portrait(actor=Depends(require_user)):
    with Session.begin() as db:
        db.execute(delete(Signal).where(Signal.owner == actor))
    return {"ok": True}
