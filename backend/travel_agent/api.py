import asyncio
import hashlib
import json
import secrets
import threading
from contextlib import asynccontextmanager
from datetime import timedelta
from pathlib import Path
from urllib.parse import urlparse
import httpx
import redis
from fastapi import FastAPI, Depends, HTTPException, Request, Response, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, StreamingResponse
from sqlalchemy import select, text, or_
from sqlalchemy.exc import IntegrityError
from .config import settings, ROOT
from .db import Session, User, Trip, Task, Event, Revision, Document, Share, LoginSession, TripMember, now
from .access import get_trip, role_for, safe_plan
from .security import require_user, password_hash, password_valid, new_session, hash_token
from .schemas import Credentials, RunRequest, ResumeRequest, TripPatch
from .worker import dispatch_pending
from . import knowledge, exports
from .social_api import router as social_router
from .db import AccountProfile, DailyDetailSnapshot
from .mailer import queue_token, deliver_pending
from .lifecycle_api import router as lifecycle_router
from .hotel_api import router as hotel_router
from .discovery_api import router as discovery_router
from .booking_api import router as booking_router
from .services_api import router as services_router
from .budget_api import router as budget_router
from .budgeting import calculate_budget, compatible_snapshot


def owned(db, model, ident, owner):
    if model is Trip:
        return get_trip(db, ident, owner)
    obj = db.get(model, ident)
    if not obj or obj.owner != owner:
        raise HTTPException(404, "记录不存在")
    return obj


def task_view(task):
    return {
        "id": task.id,
        "trip_id": task.trip_id,
        "status": task.status,
        "result": task.result,
        "requirements": task.payload["requirements"],
        "message": task.payload["message"],
        "fixture": task.payload["fixture"],
        "created": task.created.isoformat(),
        "updated": task.updated.isoformat(),
    }


def trip_view(trip, role="owner"):
    return {
        "id": trip.id,
        "title": trip.title,
        "version": trip.version,
        "plan": safe_plan(trip.plan, role == "owner"),
        "role": role,
        "updated": trip.updated.isoformat(),
    }


def dispatcher(stop):
    while not stop.wait(10):
        try:
            dispatch_pending()
        except Exception:
            # SQL remains the outbox: next tick retries undispatched queued jobs.
            pass
        try:
            deliver_pending()
            from .privacy_cleanup import process_pending

            process_pending()
        except Exception:
            pass


@asynccontextmanager
async def lifespan(app):
    stop = threading.Event()
    thread = threading.Thread(target=dispatcher, args=(stop,), daemon=True)
    thread.start()
    yield
    stop.set()


app = FastAPI(title="travel_agent", version="0.1.0", lifespan=lifespan)


@app.middleware("http")
async def security_headers(request, call_next):
    if (
        request.method not in {"GET", "HEAD", "OPTIONS"}
        and (Path(settings.data_dir) / "maintenance").exists()
    ):
        return Response("正在备份维护，请稍后再试", 503)
    origin = request.headers.get("origin")
    if request.method not in {"GET", "HEAD", "OPTIONS"} and origin:
        origin_host = urlparse(origin).netloc
        host = request.headers.get("host", "")
        if origin_host not in {host, "127.0.0.1:8809", "localhost:8809"}:
            return Response("不允许的请求来源", 403)
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Cache-Control"] = (
        "no-store" if request.url.path.startswith(("/api", "/s/")) else "no-cache"
    )
    return response


@app.get("/api/v1/health")
def health():
    services = {}
    try:
        with Session() as db:
            db.execute(text("SELECT 1"))
        services["mysql"] = "ready"
    except Exception:
        services["mysql"] = "unavailable"
    try:
        redis.Redis.from_url(settings.redis_url, socket_timeout=2).ping()
        services["redis"] = "ready"
    except Exception:
        services["redis"] = "unavailable"
    try:
        with httpx.Client(timeout=2, trust_env=False) as client:
            services["elasticsearch"] = (
                "ready" if client.get(settings.elastic_url).status_code == 200 else "unavailable"
            )
    except Exception:
        services["elasticsearch"] = "unavailable"
    return {
        "application": "travel_agent",
        "services": services,
        "providers": {
            "model": "configured_not_verified"
            if settings.model_enabled and settings.model_api_key
            else "needs_key",
            "amap": "configured_not_verified" if settings.amap_key else "needs_key",
            "meituan": "configured_not_verified" if settings.meituan_enabled else "disabled",
        },
        "fixture_enabled": settings.fixture_enabled,
        "voice_enabled": settings.voice_enabled,
    }


def throttle_login(request):
    try:
        client = redis.Redis.from_url(settings.redis_url, socket_timeout=2)
        key = "login:" + hash_token(request.client.host) + ":" + str(int(now().timestamp()) // 300)
        count = client.incr(key)
        client.expire(key, 310)
        if count > 30:
            raise HTTPException(429, "尝试次数过多，请稍后再试")
    except redis.RedisError:
        raise HTTPException(503, "登录限流服务暂不可用，请稍后重试")


@app.post("/api/v1/auth/register")
def register(body: Credentials, request: Request, response: Response):
    throttle_login(request)
    if settings.email_required and not body.email:
        raise HTTPException(422, "请填写邮箱以便验证和找回密码")
    try:
        with Session.begin() as db:
            user = User(name=body.name, password=password_hash(body.password))
            db.add(user)
            db.flush()
            db.add(AccountProfile(owner=user.id, email=str(body.email).lower() if body.email else None))
            db.flush()
            if body.email:
                queue_token(db, user.id, "verify")
            token, csrf = new_session(db, user, settings.session_days)
            result = {
                "name": user.name,
                "csrf": csrf,
                "preferences": {},
                "email": body.email,
                "email_verified": False,
            }
    except IntegrityError:
        raise HTTPException(409, "该用户名已被使用")
    response.set_cookie(
        "travel_session",
        token,
        httponly=True,
        samesite="lax",
        secure=settings.cookie_secure,
        max_age=settings.session_days * 86400,
    )
    return result


@app.post("/api/v1/auth/login")
def login(body: Credentials, request: Request, response: Response):
    throttle_login(request)
    with Session.begin() as db:
        user = db.scalar(select(User).where(User.name == body.name))
        if not user or not password_valid(body.password, user.password):
            raise HTTPException(401, "用户名或密码错误")
        token, csrf = new_session(db, user, settings.session_days)
        result = {"name": user.name, "csrf": csrf, "preferences": user.preferences}
    response.set_cookie(
        "travel_session",
        token,
        httponly=True,
        samesite="lax",
        secure=settings.cookie_secure,
        max_age=settings.session_days * 86400,
    )
    return result


@app.get("/api/v1/auth/me")
def me(request: Request, owner=Depends(require_user)):
    with Session() as db:
        user = db.get(User, owner)
        session = db.get(LoginSession, hash_token(request.cookies["travel_session"]))
        profile = db.get(AccountProfile, owner)
        return {
            "name": user.name,
            "csrf": session.csrf,
            "preferences": user.preferences,
            "email": profile.email if profile else None,
            "email_verified": bool(profile and profile.email_verified),
            "consent": profile.consent if profile else {},
        }


@app.post("/api/v1/auth/logout")
def logout(request: Request, response: Response, owner=Depends(require_user)):
    with Session.begin() as db:
        db.delete(db.get(LoginSession, hash_token(request.cookies["travel_session"])))
    response.delete_cookie("travel_session")
    return {"ok": True}


@app.put("/api/v1/preferences")
def preferences(body: dict, owner=Depends(require_user)):
    allowed = {
        k: str(v)[:300]
        for k, v in body.items()
        if k in {"travel_style", "accessibility", "pace", "food", "default_city", "default_days"}
    }
    if allowed.get("default_days") and (
        not allowed["default_days"].isdigit() or not 1 <= int(allowed["default_days"]) <= 14
    ):
        raise HTTPException(422, "默认天数须为 1—14")
    with Session.begin() as db:
        user = db.get(User, owner)
        user.preferences = allowed
    return {"preferences": allowed}


@app.get("/api/v1/trips")
def trips(owner=Depends(require_user)):
    with Session() as db:
        return [
            trip_view(t, role_for(db, t, owner))
            for t in db.scalars(
                select(Trip)
                .where(
                    or_(
                        Trip.owner == owner,
                        Trip.id.in_(select(TripMember.trip_id).where(TripMember.user_id == owner)),
                    )
                )
                .order_by(Trip.updated.desc())
                .limit(100)
            )
        ]


@app.get("/api/v1/trips/{ident}")
def trip(ident: str, owner=Depends(require_user)):
    with Session() as db:
        value = get_trip(db, ident, owner)
        return trip_view(value, role_for(db, value, owner))


@app.post("/api/v1/tasks", status_code=202)
def create_task(body: RunRequest, owner=Depends(require_user)):
    if body.fixture and not settings.fixture_enabled:
        raise HTTPException(403, "当前环境禁用合成数据")
    canonical = body.model_dump(mode="json")
    digest = hash_token(json.dumps(canonical, sort_keys=True, ensure_ascii=False))
    try:
        with Session.begin() as db:
            old = db.scalar(select(Task).where(Task.owner == owner, Task.request_key == body.request_key))
            if old:
                if old.request_hash != digest:
                    raise HTTPException(409, "相同幂等键不能提交不同内容")
                return task_view(old)
            if body.trip_id:
                trip = get_trip(db, body.trip_id, owner, edit=True)
                if trip.version != body.base_version:
                    raise HTTPException(409, "行程版本已变化，请刷新后修改")
                if trip.plan.get("fixture", False) != body.fixture:
                    raise HTTPException(409, "合成行程和真实行程不能混合修改，请新建行程")
                locks = trip.plan.get("requirements", {}).get("locked_ids", [])
                canonical["requirements"]["locked_ids"] = list(
                    dict.fromkeys(locks + body.requirements.locked_ids)
                )
            else:
                if body.base_version != 0:
                    raise HTTPException(409, "新行程版本应为零")
                user = db.get(User, owner)
                trip = Trip(
                    owner=owner,
                    title=body.requirements.city + " · 规划中",
                    context={"confirmed_preferences": user.preferences},
                )
                db.add(trip)
                db.flush()
            # Avoid unbounded pending jobs per account.
            pending = db.scalars(
                select(Task.id).where(Task.owner == owner, Task.status.in_(["queued", "running"]))
            ).all()
            if len(pending) >= 3:
                raise HTTPException(429, "最多同时保留三个执行中任务")
            task = Task(
                owner=owner,
                trip_id=trip.id,
                request_key=body.request_key,
                request_hash=digest,
                payload=canonical,
            )
            db.add(task)
            db.flush()
            result = task_view(task)
    except IntegrityError:
        with Session() as db:
            old = db.scalar(select(Task).where(Task.owner == owner, Task.request_key == body.request_key))
            if not old or old.request_hash != digest:
                raise HTTPException(409, "请求内容冲突")
            return task_view(old)
    # Durable queued row is dispatched by the scheduler, even if broker is currently down.
    return result


@app.get("/api/v1/tasks")
def tasks(owner=Depends(require_user)):
    with Session() as db:
        return [
            task_view(t)
            for t in db.scalars(
                select(Task).where(Task.owner == owner).order_by(Task.created.desc()).limit(100)
            )
        ]


@app.get("/api/v1/tasks/{ident}")
def task(ident: str, owner=Depends(require_user)):
    with Session() as db:
        return task_view(owned(db, Task, ident, owner))


@app.get("/api/v1/tasks/{ident}/events")
async def events(ident: str, request: Request, owner=Depends(require_user)):
    with Session() as db:
        owned(db, Task, ident, owner)
    try:
        after = max(0, int(request.headers.get("last-event-id", "0")))
    except ValueError:
        after = 0

    async def stream():
        cursor = after
        while not await request.is_disconnected():
            with Session() as db:
                rows = db.scalars(
                    select(Event)
                    .where(Event.task_id == ident, Event.id > cursor)
                    .order_by(Event.id)
                    .limit(50)
                ).all()
                status = db.get(Task, ident).status
            for row in rows:
                cursor = row.id
                payload = {"kind": row.kind, "data": row.data, "created": row.created.isoformat()}
                yield f"id: {row.id}\nevent: trace\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"
            if status not in {"queued", "running"} and len(rows) < 50:
                yield f"event: status\ndata: {json.dumps({'status': status})}\n\n"
                return
            yield ": keepalive\n\n"
            await asyncio.sleep(1)

    return StreamingResponse(stream(), media_type="text/event-stream", headers={"X-Accel-Buffering": "no"})


@app.post("/api/v1/tasks/{ident}/resume", status_code=202)
def resume(ident: str, body: ResumeRequest, owner=Depends(require_user)):
    with Session.begin() as db:
        task = owned(db, Task, ident, owner)
        task = db.get(Task, ident, with_for_update=True)
        if task.status != "waiting_input":
            raise HTTPException(409, "任务当前不等待补充信息")
        task.payload = {**task.payload, "resume": body.requirements.model_dump(mode="json")}
        task.payload = {**task.payload, "requirements": body.requirements.model_dump(mode="json")}
        task.status, task.updated = "queued", now()
        return task_view(task)


@app.post("/api/v1/tasks/{ident}/retry", status_code=202)
def retry_task(ident: str, owner=Depends(require_user)):
    with Session.begin() as db:
        task = owned(db, Task, ident, owner)
        task = db.get(Task, ident, with_for_update=True)
        if task.status not in {"failed", "awaiting_credentials"}:
            raise HTTPException(409, "当前任务不允许重试；版本冲突请创建新任务")
        task.status, task.result, task.updated = "queued", {}, now()
        return task_view(task)


@app.post("/api/v1/tasks/{ident}/cancel")
def cancel(ident: str, owner=Depends(require_user)):
    with Session.begin() as db:
        task = owned(db, Task, ident, owner)
        task = db.get(Task, ident, with_for_update=True)
        if task.status in {"queued", "running", "waiting_input", "awaiting_credentials", "failed"}:
            task.status, task.lease, task.updated = "cancelled", None, now()
        return task_view(task)


@app.get("/api/v1/trips/{ident}/revisions")
def revisions(ident: str, owner=Depends(require_user)):
    with Session() as db:
        owned(db, Trip, ident, owner)
        return [
            {"version": r.version, "message": r.message, "created": r.created.isoformat(), "plan": r.plan}
            for r in db.scalars(
                select(Revision).where(Revision.trip_id == ident).order_by(Revision.version.desc())
            )
        ]


@app.put("/api/v1/trips/{ident}/locks")
def locks(ident: str, body: TripPatch, owner=Depends(require_user)):
    with Session.begin() as db:
        get_trip(db, ident, owner, edit=True)
        trip = db.get(Trip, ident, with_for_update=True)
        if trip.version != body.version:
            raise HTTPException(409, "版本冲突，请刷新")
        valid = {s["id"] for day in trip.plan.get("days", []) for s in day["stops"]}
        if set(body.locked_ids) - valid:
            raise HTTPException(422, "锁定地点必须属于当前行程")
        plan = json.loads(json.dumps(trip.plan))
        plan["requirements"]["locked_ids"] = body.locked_ids
        for day in plan["days"]:
            for stop in day["stops"]:
                stop["locked"] = stop["id"] in body.locked_ids
        trip.version += 1
        trip.plan, trip.updated = plan, now()
        db.add(Revision(trip_id=ident, version=trip.version, plan=plan, message="更新锁定安排"))
        return trip_view(trip)


@app.post("/api/v1/trips/{ident}/restore/{version}")
def restore(ident: str, version: int, body: dict, owner=Depends(require_user)):
    with Session.begin() as db:
        get_trip(db, ident, owner, edit=True)
        trip = db.get(Trip, ident, with_for_update=True)
        if body.get("base_version") != trip.version:
            raise HTTPException(409, "版本冲突，请刷新")
        revision = db.scalar(select(Revision).where(Revision.trip_id == ident, Revision.version == version))
        if not revision:
            raise HTTPException(404, "历史版本不存在")
        trip.plan, trip.version, trip.updated = revision.plan, trip.version + 1, now()
        db.add(
            Revision(trip_id=ident, version=trip.version, plan=trip.plan, message=f"恢复历史版本 {version}")
        )
        return trip_view(trip)


@app.get("/api/v1/trips/{ident}/export/{kind}")
def export(ident: str, kind: str, owner=Depends(require_user)):
    with Session() as db:
        trip = owned(db, Trip, ident, owner)
        plan = json.loads(json.dumps(trip.plan))
        snapshots = db.scalars(
            select(DailyDetailSnapshot)
            .where(DailyDetailSnapshot.trip_id == ident)
            .order_by(DailyDetailSnapshot.created.desc())
        ).all()
        for day in plan.get("days", []):
            mode = day.get("transport_mode") or plan["requirements"]["transport"]
            snapshot = next((s for s in snapshots if compatible_snapshot(plan, day, s)), None)
            if snapshot:
                day["daily_details"] = snapshot.data
        if plan.get("days"):
            plan["expense_ledger"] = calculate_budget(plan, snapshots)
    if not plan:
        raise HTTPException(409, "尚无可导出的行程")
    if kind == "md":
        return Response(
            exports.markdown(plan),
            media_type="text/markdown",
            headers={"Content-Disposition": 'attachment; filename="travel-roadbook.md"'},
        )
    if kind == "pdf":
        return Response(
            exports.pdf(plan),
            media_type="application/pdf",
            headers={"Content-Disposition": 'attachment; filename="travel-roadbook.pdf"'},
        )
    raise HTTPException(404, "不支持的格式")


@app.post("/api/v1/trips/{ident}/shares")
def share(ident: str, owner=Depends(require_user)):
    with Session.begin() as db:
        trip = get_trip(db, ident, owner, owner_only=True)
        if not trip.plan:
            raise HTTPException(409, "尚无可分享的行程")
        token = secrets.token_urlsafe(32)
        db.add(
            Share(
                token=hash_token(token),
                owner=owner,
                trip_id=ident,
                version=trip.version,
                expires=now() + timedelta(days=settings.share_days),
            )
        )
    return {
        "path": "/s/" + token,
        "id": hash_token(token),
        "days": settings.share_days,
        "notice": "本机地址仅本机可见；公开分享需部署 HTTPS",
    }


@app.delete("/api/v1/shares/{ident}")
def revoke(ident: str, owner=Depends(require_user)):
    with Session.begin() as db:
        owned(db, Share, ident, owner).revoked = 1
    return {"ok": True}


@app.get("/s/{token}", response_class=HTMLResponse)
def shared(token: str):
    with Session() as db:
        share = db.get(Share, hash_token(token))
        if not share or share.revoked or share.expires < now():
            raise HTTPException(404, "分享不存在或已过期")
        rev = db.scalar(
            select(Revision).where(Revision.trip_id == share.trip_id, Revision.version == share.version)
        )
        plan = json.loads(json.dumps(rev.plan))
    # Omit user preferences, private documents, dialogue and research text.
    plan["rationale"] = ""
    plan["lodging"] = {}
    return exports.shared_html(plan)


@app.post("/api/v1/documents", status_code=202)
async def upload(file: UploadFile, owner=Depends(require_user)):
    name = Path(file.filename or "资料").name[:180]
    if Path(name).suffix.lower() not in {".txt", ".md", ".pdf", ".docx"}:
        raise HTTPException(415, "支持 TXT、MD、PDF、DOCX；图片内容暂不进入索引")
    content = await file.read(settings.max_upload_bytes + 1)
    if not content or len(content) > settings.max_upload_bytes:
        raise HTTPException(413, "文件为空或超过 5 MB")
    digest = hashlib.sha256(content).hexdigest()
    with Session.begin() as db:
        old = db.scalar(
            select(Document).where(
                Document.owner == owner, Document.digest == digest, Document.status != "deleted"
            )
        )
        if old:
            return {"id": old.id, "duplicate": True, "status": old.status}
        doc = Document(owner=owner, name=name, digest=digest)
        db.add(doc)
        db.flush()
        target = Path(settings.data_dir) / "uploads" / doc.id
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
        return {"id": doc.id, "status": "queued"}


@app.get("/api/v1/documents")
def documents(owner=Depends(require_user)):
    with Session() as db:
        return [
            {"id": d.id, "name": d.name, "status": d.status, "version": d.version, "info": d.info}
            for d in db.scalars(
                select(Document)
                .where(Document.owner == owner, Document.status != "deleted")
                .order_by(Document.created.desc())
            )
        ]


@app.get("/api/v1/documents/{ident}/original")
def original(ident: str, owner=Depends(require_user)):
    with Session() as db:
        doc = owned(db, Document, ident, owner)
        if doc.status == "deleted":
            raise HTTPException(404, "文档已移除")
        return FileResponse(
            Path(settings.data_dir) / "uploads" / doc.id,
            filename=doc.name,
            media_type="application/octet-stream",
        )


@app.post("/api/v1/documents/{ident}/reindex")
def reindex(ident: str, owner=Depends(require_user)):
    with Session.begin() as db:
        doc = owned(db, Document, ident, owner)
        if doc.status in {"deleted", "indexing", "queued"}:
            raise HTTPException(409, "当前状态不能重新索引")
        doc.status = "queued"
    return {"status": "queued"}


@app.delete("/api/v1/documents/{ident}")
def delete_document(ident: str, owner=Depends(require_user)):
    with Session.begin() as db:
        doc = owned(db, Document, ident, owner)
        doc.status = "deleted"
    # Logical visibility is revoked before best-effort derived-index cleanup.
    try:
        knowledge.es(
            "POST",
            "/" + settings.elastic_index + "/_delete_by_query?refresh=true",
            json={"query": {"term": {"doc_id": ident}}},
        )
    except Exception:
        pass
    return {"ok": True}


@app.post("/api/v1/knowledge/search")
def search(body: dict, owner=Depends(require_user)):
    query = str(body.get("query", "")).strip()
    if not query or len(query) > 500:
        raise HTTPException(422, "请输入 1—500 字查询")
    try:
        return knowledge.search(owner, query)
    except Exception:
        raise HTTPException(503, "检索服务暂不可用，请检查 Elasticsearch 和本地 Embedding 模型")


@app.get("/api/v1/map-config")
def map_config(owner=Depends(require_user)):
    return {"key": settings.amap_js_key, "serviceHost": "/_AMapService"}


@app.post("/api/v1/voice/asr")
async def voice_asr(file: UploadFile, owner=Depends(require_user)):
    from .voice import transcribe
    from .providers.base import ProviderError

    raw = await file.read(5 * 1024 * 1024 + 1)
    try:
        return await asyncio.to_thread(transcribe, raw)
    except (ValueError, ProviderError) as exc:
        raise HTTPException(422, str(exc))
    except Exception:
        raise HTTPException(503, "语音服务暂不可用，识别内容没有被提交为行程修改")


@app.post("/api/v1/voice/tts")
def voice_tts(body: dict, owner=Depends(require_user)):
    from .voice import synthesize
    from .providers.base import ProviderError

    try:
        return Response(synthesize(str(body.get("text", ""))), media_type="audio/wav")
    except (ValueError, ProviderError) as exc:
        raise HTTPException(422, str(exc))
    except Exception:
        raise HTTPException(503, "语音合成暂不可用，请稍后再试")


@app.get("/_AMapService/{path:path}")
async def amap_proxy(path: str, request: Request, owner=Depends(require_user)):
    if not settings.amap_security_code:
        raise HTTPException(503, "尚未配置 JS 安全码")
    if ".." in path or not path.startswith(("v3/", "v4/", "v5/")) or ":" in path:
        raise HTTPException(400, "不支持的地图请求")
    params = dict(request.query_params)
    params.update(jscode=settings.amap_security_code)
    async with httpx.AsyncClient(timeout=15, follow_redirects=False) as client:
        response = await client.get("https://restapi.amap.com/" + path, params=params)
    return Response(
        response.content,
        status_code=response.status_code,
        media_type=response.headers.get("content-type", "application/json"),
    )


app.include_router(social_router)
app.include_router(lifecycle_router)
app.include_router(hotel_router)
app.include_router(discovery_router)
app.include_router(booking_router)
app.include_router(services_router)
app.include_router(budget_router)


@app.get("/{path:path}")
def frontend(path: str):
    if path.startswith(("api/", "_AMapService/")):
        raise HTTPException(404, "接口不存在")
    root = (ROOT / "frontend/dist").resolve()
    file = (root / path).resolve()
    if not file.is_relative_to(root):
        raise HTTPException(404, "资源不存在")
    if file.is_file():
        return FileResponse(file)
    if (root / "index.html").exists():
        return FileResponse(root / "index.html")
    return HTMLResponse(
        "<meta charset='utf-8'><h1>travel_agent</h1><p>前端尚未构建，请运行 run_project.py。</p>",
        status_code=503,
    )
