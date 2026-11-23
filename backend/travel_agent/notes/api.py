"""Owner-scoped async note imports, source supplementation, review and POI selection."""

import asyncio
import hashlib
import shutil
import uuid
from copy import deepcopy

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from ..db import Attachment, Session, User, now
from ..parsers.screenshot import detect_mime, validate_image
from ..security import require_user
from . import jobs, source

router = APIRouter(prefix="/api/v1/note-imports")


def owned(db, ident, actor, lock=False):
    row = db.get(Attachment, ident, with_for_update=lock)
    if not row or row.owner != actor or row.kind != "travel_note":
        raise HTTPException(404, "攻略不存在")
    return row


async def uploads(files):
    if len(files) > jobs.MAX_IMAGES:
        raise HTTPException(413, "每篇最多 20 张图片，请分批导入")
    result, total = [], 0
    for file in files:
        raw = await file.read(source.MAX_IMAGE_BYTES + 1)
        total += len(raw)
        try:
            validate_image(raw)
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
        if total > jobs.MAX_TOTAL_BYTES:
            raise HTTPException(413, "图片总量不能超过 50 MB")
        result.append(raw)
    return result


def image_rows(actor, ident, raws, data):
    current = deepcopy(data.get("images", []))
    existing = {v.get("file") for v in current}
    for raw in raws:
        digest = hashlib.sha256(raw).hexdigest()
        if digest in existing:
            continue
        current.append({"id": uuid.uuid4().hex, "file": digest, "status": "pending", "tiles": []})
        existing.add(digest)
    if len(current) > jobs.MAX_IMAGES:
        raise HTTPException(413, "累计图片超过 20 张，请另建一篇攻略")
    used = sum(
        (jobs.directory(actor, ident) / v["file"]).stat().st_size
        for v in data.get("images", [])
        if v.get("file")
    )
    additions = {
        hashlib.sha256(raw).hexdigest(): raw
        for raw in raws
        if hashlib.sha256(raw).hexdigest() not in {v.get("file") for v in data.get("images", [])}
    }
    if used + sum(len(v) for v in additions.values()) > jobs.MAX_TOTAL_BYTES:
        raise HTTPException(413, "累计图片不能超过 50 MB")
    for raw in additions.values():
        try:
            jobs.save_file(actor, ident, raw)
        except (ValueError, OSError) as exc:
            raise HTTPException(422, "图片无法解码或像素超限") from exc
    return current


@router.post("", status_code=202)
async def create(
    share_text: str = Form("", max_length=10000),
    body_text: str = Form("", max_length=200000),
    files: list[UploadFile] = File(default=[]),
    actor=Depends(require_user),
):
    url = source.extract_url(share_text)
    if not url and not body_text.strip() and not files:
        raise HTTPException(422, "请粘贴小红书链接，或补充正文/图片；分享文案不等于笔记正文")
    raws = await uploads(files)
    # Exact imports are reusable. Metadata alone is never proof that the note was read.
    digest = hashlib.sha256(
        (url + "\0" + body_text + "\0" + "".join(hashlib.sha256(r).hexdigest() for r in raws)).encode()
    ).hexdigest()
    with Session() as db:
        candidates = db.scalars(
            select(Attachment).where(Attachment.owner == actor, Attachment.kind == "travel_note")
        ).all()
        for row in candidates:
            if row.parsed.get("input_digest") == digest:
                return jobs.view(row)
    ident = hashlib.sha256((actor + digest).encode()).hexdigest()[:32]
    with Session() as db:
        existing = db.get(Attachment, ident)
        if existing:
            if existing.owner != actor:
                raise HTTPException(404, "攻略不存在")
            return jobs.view(existing)
    data = jobs.queued(
        {
            "url": url,
            "share_text": share_text,
            "manual_body": body_text,
            "link_body": "",
            "link_status": "pending" if url else "not_supplied",
            "images": [],
            "facts": [],
            "selected_fact_ids": [],
            "input_digest": digest,
            "title": "小红书攻略",
            "created_at": now().isoformat(),
        }
    )
    try:
        with Session.begin() as db:
            if not db.get(User, actor, with_for_update=True):
                raise HTTPException(401, "登录状态已失效")
            data["images"] = image_rows(actor, ident, raws, data)
            row = Attachment(
                id=ident, owner=actor, name="小红书攻略", ext=".note", kind="travel_note", parsed=data
            )
            db.add(row)
            db.flush()
            result = jobs.view(row)
    except IntegrityError:
        with Session() as db:
            existing = db.get(Attachment, ident)
            if existing and existing.owner == actor:
                return jobs.view(existing)
        shutil.rmtree(jobs.directory(actor, ident), ignore_errors=True)
        raise
    except BaseException:
        with Session() as db:
            exists = db.get(Attachment, ident) is not None
        if not exists:
            shutil.rmtree(jobs.directory(actor, ident), ignore_errors=True)
        raise
    await asyncio.to_thread(jobs.dispatch, ident)
    return result


@router.get("")
def listing(actor=Depends(require_user)):
    with Session() as db:
        return [
            {"id": r.id, "name": r.name, "status": r.parsed.get("status")}
            for r in db.scalars(
                select(Attachment)
                .where(Attachment.owner == actor, Attachment.kind == "travel_note")
                .order_by(Attachment.created.desc())
                .limit(50)
            )
        ]


@router.get("/{ident}")
def detail(ident: str, actor=Depends(require_user)):
    with Session() as db:
        return jobs.view(owned(db, ident, actor))


@router.post("/{ident}/sources", status_code=202)
async def supplement(
    ident: str,
    body_text: str = Form("", max_length=200000),
    files: list[UploadFile] = File(default=[]),
    actor=Depends(require_user),
):
    raws = await uploads(files)
    if not body_text.strip() and not raws:
        raise HTTPException(422, "请补充正文或图片")
    with Session.begin() as db:
        row = owned(db, ident, actor, True)
        data = deepcopy(row.parsed)
        if data["status"] in {"queued", "running"}:
            raise HTTPException(409, "正在处理，请完成后补充资料")
        data["images"] = image_rows(actor, ident, raws, data)
        if body_text.strip() and body_text != data.get("manual_body"):
            data["manual_body"] = body_text
            jobs.invalidate_source(data, "manual_body:")
        # Confirmations must be made against the new revision, not silently carried forward.
        data["selected_fact_ids"] = []
        data.pop("confirmed_at", None)
        data.pop("input_digest", None)
        row.parsed = jobs.queued(data)
        result = jobs.view(row)
    await asyncio.to_thread(jobs.dispatch, ident)
    return result


class Retry(BaseModel):
    image_id: str | None = None
    retry_link: bool = False
    force_ocr: bool = False


@router.post("/{ident}/retry", status_code=202)
def retry(ident: str, body: Retry, actor=Depends(require_user)):
    with Session.begin() as db:
        row = owned(db, ident, actor, True)
        data = deepcopy(row.parsed)
        if data["status"] in {"queued", "running"}:
            raise HTTPException(409, "任务已在处理中")
        if body.image_id and body.image_id not in {v["id"] for v in data["images"]}:
            raise HTTPException(404, "图片不存在")
        # Successful image/tile checkpoints are reused by the worker.
        if body.image_id:
            for image in data["images"]:
                if image["id"] == body.image_id:
                    image["status"] = "pending"
                    jobs.invalidate_source(data, "image:" + image["id"] + ":")
                    if body.force_ocr:
                        image.update(
                            classification="", force_ocr=True, user_requested_text=True, tiles=[], text=""
                        )
        if body.retry_link:
            data["link_status"] = "pending" if data.get("url") else "not_supplied"
        data["selected_fact_ids"] = []
        data.pop("confirmed_at", None)
        row.parsed = jobs.queued(data)
        result = jobs.view(row)
    jobs.dispatch(ident)
    return result


class Review(BaseModel):
    selected_fact_ids: list[str] = Field(default_factory=list, max_length=200)
    edits: dict[str, str] = Field(default_factory=dict)
    auto: bool = False


@router.post("/{ident}/confirm")
def confirm(ident: str, body: Review, actor=Depends(require_user)):
    with Session.begin() as db:
        row = owned(db, ident, actor, True)
        data = deepcopy(row.parsed)
        if data["status"] not in {"ready", "partial", "error"}:
            raise HTTPException(409, "请等待解析完成后核对")
        facts = {f["id"]: f for f in data["facts"]}
        if not set(body.selected_fact_ids) <= facts.keys() or not set(body.edits) <= facts.keys():
            raise HTTPException(422, "只能选择本篇攻略的候选信息")
        body_text = str(data.get("manual_body") or data.get("link_body") or "").strip()
        if not body.selected_fact_ids and not body_text:
            raise HTTPException(422, "请至少选择一条攻略信息或提供笔记正文")
        for key, value in body.edits.items():
            if not value.strip() or len(value) > 1200:
                raise HTTPException(422, "修改内容必须为 1–1200 字")
            facts[key].setdefault("original_text", facts[key]["text"])
            facts[key].update(text=value, edited=True, candidates=[], place=None, match_attempted=False)
        data.update(
            selected_fact_ids=list(dict.fromkeys(body.selected_fact_ids)), confirmed_at=now().isoformat()
        )
        if body.auto:
            data["auto_adopted_at"] = now().isoformat()
        row.parsed = data
        return jobs.view(row)


class Match(BaseModel):
    city: str = Field(min_length=1, max_length=80)
    candidate_id: str | None = None


@router.post("/{ident}/facts/{fact_id}/place")
def match(ident: str, fact_id: str, body: Match, actor=Depends(require_user)):
    from ..providers import amap

    with Session() as db:
        data = deepcopy(owned(db, ident, actor).parsed)
        fact = next((f for f in data["facts"] if f["id"] == fact_id and f["kind"] == "place"), None)
        if not fact:
            raise HTTPException(404, "地点信息不存在")
        if data["status"] in {"queued", "running"}:
            raise HTTPException(409, "请等待解析完成后匹配地点")
    from ..providers.base import ProviderError

    try:
        candidates = None if body.candidate_id else amap.search_places(body.city, fact["text"])[:5]
    except ProviderError as exc:
        raise HTTPException(503, str(exc)) from exc
    with Session.begin() as db:
        row = owned(db, ident, actor, True)
        current = deepcopy(row.parsed)
        if current != data:
            raise HTTPException(409, "攻略信息已变化，请刷新后重新匹配")
        target = next(f for f in current["facts"] if f["id"] == fact_id)
        if body.candidate_id:
            place = next((p for p in target["candidates"] if p["id"] == body.candidate_id), None)
            if not place or target.get("match_city") != body.city:
                raise HTTPException(422, "只能选择本次城市查询返回的地点")
            target["place"] = place
        else:
            target.update(candidates=candidates, match_city=body.city, place=None)
        row.parsed = current
        return jobs.view(row)


@router.get("/{ident}/images/{image_id}")
def image(ident: str, image_id: str, actor=Depends(require_user)):
    with Session() as db:
        row = owned(db, ident, actor)
        item = next((i for i in row.parsed["images"] if i["id"] == image_id), None)
        if not item or not item.get("file"):
            raise HTTPException(404, "原图尚未读取")
        path = jobs.directory(actor, ident) / item["file"]
        if not path.is_file():
            raise HTTPException(404, "原图不存在")
        mime = detect_mime(path.read_bytes()[:16])
        return FileResponse(path, media_type=mime, headers={"Cache-Control": "no-store"})


@router.delete("/{ident}", status_code=204)
def remove(ident: str, actor=Depends(require_user)):
    with Session.begin() as db:
        db.delete(owned(db, ident, actor, True))
        shutil.rmtree(jobs.directory(actor, ident), ignore_errors=True)


def confirmed_context(db, actor, identifiers):
    chunks = []
    for ident in identifiers:
        row = owned(db, ident, actor)
        data = row.parsed
        if not data.get("confirmed_at") or data.get("status") in {"queued", "running"}:
            raise HTTPException(422, "攻略需要先核对确认")
        selected = set(data.get("selected_fact_ids", []))
        chosen = [f for f in data["facts"] if f["id"] in selected]
        body = str(data.get("manual_body") or data.get("link_body") or "").strip()[:10000]
        image_texts = []
        image_budget = 6000
        for image in data.get("images", []):
            text = str(image.get("text") or "").strip()
            if not text or image_budget <= 0:
                continue
            part = text[: min(800, image_budget)]
            image_texts.append(part)
            image_budget -= len(part)
        chunks.append(
            {
                "attachment_id": ident,
                "url": data.get("url", ""),
                "title": str(data.get("title") or "小红书攻略")[:200],
                "body": body,
                "body_source": data.get("body_source", ""),
                "image_texts": image_texts[:20],
                "facts": [
                    {
                        "id": f["id"],
                        "kind": f["kind"],
                        "text": f["text"],
                        "sources": f["sources"],
                        "place": f.get("place"),
                        "edited": f.get("edited", False),
                    }
                    for f in chosen
                ],
            }
        )
    if sum(len(str(chunk)) for chunk in chunks) > 30000:
        raise HTTPException(422, "选择内容过多，请分批交给助手")
    return chunks
