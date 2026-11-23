"""Durable Attachment-backed note jobs, fenced leases and per-source checkpoints."""

import hashlib
import io
import json
import time
import uuid
from copy import deepcopy
from datetime import timedelta
from pathlib import Path

from PIL import Image
from sqlalchemy import and_, or_, select

from ..config import settings
from ..db import Attachment, Session, User, now
from ..parsers.screenshot import validate_image
from . import extract, source

MAX_IMAGES = 20
MAX_TOTAL_BYTES = 50 * 1024 * 1024
MAX_BODY_CHARS = 200_000
LEASE_SECONDS = 900
JOB_BUDGET_SECONDS = 1800
QUEUE = "note_imports"


def directory(owner, ident):
    if not owner.isalnum() or not ident.isalnum():
        raise ValueError("无效资料编号")
    return Path(settings.data_dir) / "note-imports" / owner / ident


def view(row):
    data = deepcopy(row.parsed)
    data.pop("lease", None)
    data.pop("lease_until", None)
    for image in data.get("images", []):
        image.pop("file", None)
    return {"id": row.id, "name": row.name, "kind": row.kind, "parsed": data, "suggestion": row.suggestion}


def save_file(owner, ident, raw):
    validate_image(raw)
    with Image.open(io.BytesIO(raw)) as image:
        if image.width * image.height > extract.MAX_PIXELS:
            raise ValueError("图片像素过大，请拆分后导入")
        image.verify()
    name = hashlib.sha256(raw).hexdigest()
    folder = directory(owner, ident)
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / name
    if not path.exists():
        path.write_bytes(raw)
        path.chmod(0o600)
    return name


def queued(data):
    data.update(status="queued", lease="", lease_until="", queued_at=now().isoformat(), error="")
    return data


def dispatch(ident):
    from .worker import process_note

    with Session.begin() as db:
        row = db.get(Attachment, ident, with_for_update=True)
        if not row or row.parsed.get("status") not in {"queued", "running"}:
            return
        if row.parsed.get("dispatch_attempt", "") > (now() - timedelta(seconds=30)).isoformat():
            return
        row.parsed = {**row.parsed, "dispatch_attempt": now().isoformat()}
    try:
        process_note.apply_async(args=[ident], queue=QUEUE, retry=False)
    except Exception:
        pass  # SQL remains queued; API dispatcher redelivers. Never run OCR on an API thread.


def dispatch_pending():
    with Session() as db:
        rows = db.scalars(
            select(Attachment)
            .where(
                Attachment.kind == "travel_note",
                or_(
                    Attachment.parsed["status"].as_string() == "queued",
                    and_(
                        Attachment.parsed["status"].as_string() == "running",
                        Attachment.parsed["lease_until"].as_string() < now().isoformat(),
                    ),
                ),
            )
            .order_by(Attachment.created)
            .limit(20)
        ).all()
        ids = [
            row.id
            for row in rows
            if row.parsed.get("status") == "queued"
            or (
                row.parsed.get("status") == "running"
                and row.parsed.get("lease_until", "") < now().isoformat()
            )
        ]
    for ident in ids[:20]:
        dispatch(ident)


def process(ident):
    token = uuid.uuid4().hex
    started = time.monotonic()
    with Session.begin() as db:
        row = db.get(Attachment, ident, with_for_update=True)
        if not row or row.kind != "travel_note":
            return
        data = deepcopy(row.parsed)
        if data.get("status") not in {"queued", "running"}:
            return
        if data.get("status") == "running" and data.get("lease_until", "") > now().isoformat():
            return
        owner = row.owner
        data.update(
            status="running", lease=token, lease_until=(now() + timedelta(seconds=LEASE_SECONDS)).isoformat()
        )
        row.parsed = deepcopy(data)

    def checkpoint(stage):
        expired = time.monotonic() - started > JOB_BUDGET_SECONDS and data.get("status") == "running"
        if expired:
            data.update(
                status="partial", error="本轮处理达到时间上限，已完成内容已保存，可重试剩余内容", lease=""
            )
        data.update(stage=stage, lease_until=(now() + timedelta(seconds=LEASE_SECONDS)).isoformat())
        with Session.begin() as db:
            row = db.get(Attachment, ident, with_for_update=True)
            if not row or row.parsed.get("lease") != token:
                raise InterruptedError("导入已删除或已由另一个任务接管")
            row.name = data.get("title", "小红书攻略")[:200]
            row.parsed = deepcopy(data)
        if expired:
            raise InterruptedError("处理预算已达上限")

    try:
        if data.get("url") and data.get("link_status") == "pending":
            checkpoint("读取笔记正文与配图")
            try:
                note = source.read_note(data["url"])
                if len(note["body"]) > MAX_BODY_CHARS:
                    raise ValueError("笔记正文过长，请分篇导入")
                data.update(
                    title=note["title"],
                    resolved_url=note["url"],
                    link_body=note["body"],
                    body_source=note["body_source"],
                    link_status="ok" if note["complete"] else "partial",
                )
                data["remote_image_count"] = len(note["images"])
                for url in note["images"]:
                    if url in {v.get("url") for v in data["images"]}:
                        continue
                    if len(data["images"]) >= MAX_IMAGES:
                        data["limit_warning"] = (
                            "笔记超过 20 张图片；本次未处理的图片请另外分批上传，未视为完整读取"
                        )
                        break
                    data["images"].append(
                        {"id": uuid.uuid4().hex, "url": url, "status": "pending", "tiles": []}
                    )
                if not note["complete"]:
                    final_url = str(note.get("url") or "").lower()
                    needs_login = any(
                        marker in final_url
                        for marker in ["login", "website-login/error", "passport", "verify"]
                    )
                    data["link_error"] = (
                        "尚未完成小红书浏览器登录配置：请运行 node frontend/xhs-login-setup.mjs 登录一次，再点重试读取链接；登录态会持久保存。"
                        if needs_login
                        else "只读到网页预览，未确认完整笔记；请补充正文和配图"
                    )
            except Exception as exc:
                data.update(
                    link_status="error",
                    link_error=(
                        str(exc) if isinstance(exc, ValueError) else "链接未能读取，请粘贴正文并上传配图"
                    ),
                )
            checkpoint("笔记来源已检查")
        update_facts(data, checkpoint)
        match_places(data, checkpoint)
        for index, image in enumerate(data["images"]):
            if image.get("status") in {"ok", "skipped"}:
                continue
            checkpoint(f"读取图片 {index + 1}/{len(data['images'])}")
            try:
                if not image.get("file"):
                    _, raw = source.fetch(image["url"], image=True)
                    used = sum(
                        (directory(owner, ident) / v["file"]).stat().st_size
                        for v in data["images"]
                        if v.get("file")
                    )
                    if used + len(raw) > MAX_TOTAL_BYTES:
                        raise ValueError("图片总量超过 50 MB，请分批导入")
                    with Session.begin() as file_db:
                        if not file_db.get(User, owner, with_for_update=True):
                            raise InterruptedError("账号已删除")
                        live = file_db.get(Attachment, ident, with_for_update=True)
                        if not live or live.parsed.get("lease") != token:
                            raise InterruptedError("攻略已删除或任务已接管")
                        image["file"] = save_file(owner, ident, raw)
                raw = (directory(owner, ident) / image["file"]).read_bytes()
                invalidate_source(data, "image:" + image["id"] + ":")
                if not image.get("classification"):
                    image["classification"] = (
                        "text" if image.pop("force_ocr", False) else extract.classify_image(raw)
                    )
                if image["classification"] in {"photo", "watermark"}:
                    image.update(
                        status="skipped",
                        text="",
                        tiles=[],
                        skip_reason=(
                            "纯照片，无攻略文字"
                            if image["classification"] == "photo"
                            else "仅相机水印，无攻略文字"
                        ),
                    )
                    checkpoint(f"图片 {index + 1} 已跳过 · " + image["skip_reason"])
                    continue
                chunks = extract.tiles(raw)
                existing = {tuple(v["box"]): v for v in image.get("tiles", []) if not v.get("truncated")}
                image["tiles"] = []
                for tile_index, (box, tile_raw) in enumerate(chunks):
                    result = existing.get(tuple(box))
                    if result is None:
                        result = extract.transcribe_tile(tile_raw)
                        # A bounded correction: smaller subtiles replace truncated output, never append guessed text.
                        if result["truncated"]:
                            with Image.open(io.BytesIO(tile_raw)) as tile_image:
                                middle = tile_image.height // 2
                                corrections = []
                                for top, bottom in [
                                    (0, middle + 48),
                                    (max(0, middle - 48), tile_image.height),
                                ]:
                                    buf = io.BytesIO()
                                    tile_image.crop((0, top, tile_image.width, bottom)).save(buf, "PNG")
                                    corrections.append(extract.transcribe_tile(buf.getvalue()))
                            result = {
                                **result,
                                "text": extract.merge_tiles([r["text"] for r in corrections]),
                                "truncated": any(r["truncated"] for r in corrections),
                                "unclear": any(r["unclear"] for r in corrections),
                            }
                        result = {**result, "box": box}
                    image["tiles"].append(result)
                    image["text"] = extract.merge_tiles([v["text"] for v in image["tiles"]])
                    checkpoint(
                        f"图片 {index + 1}/{len(data['images'])} · 分块 {tile_index + 1}/{len(chunks)}"
                    )
                if image["tiles"] and all(
                    part["text"].strip() in {"[无文字]", "无文字"} for part in image["tiles"]
                ):
                    image.update(
                        status="skipped",
                        classification="photo",
                        text="",
                        tiles=[],
                        skip_reason="纯照片，无攻略文字",
                    )
                    checkpoint(f"图片 {index + 1} 已跳过 · 无攻略文字")
                    continue
                if not image.get("user_requested_text") and extract.camera_watermark_only(
                    image.get("text", "")
                ):
                    image.update(
                        status="skipped",
                        classification="watermark",
                        text="",
                        tiles=[],
                        skip_reason="仅相机水印，无攻略文字",
                    )
                    checkpoint(f"图片 {index + 1} 已跳过 · 仅相机水印")
                    continue
                image["status"] = (
                    "partial" if any(v.get("truncated") or v.get("unclear") for v in image["tiles"]) else "ok"
                )
                image["error"] = (
                    "存在不清晰或未完整转写的区域，请核对原图" if image["status"] == "partial" else ""
                )
            except InterruptedError:
                raise
            except Exception as exc:
                image.update(
                    status="error",
                    error=str(exc) if isinstance(exc, ValueError) else "该图片读取或识别失败，可单独重试",
                )
            checkpoint("图片文字已更新")
            update_facts(data, checkpoint, only_image=image["id"])
            match_places(data, checkpoint)
        update_facts(data, checkpoint)
        match_places(data, checkpoint)
        has_text = bool(
            data.get("manual_body") or data.get("link_body") or any(v.get("text") for v in data["images"])
        )
        incomplete = (
            (data.get("link_status") in {"error", "partial"} and not data.get("manual_body"))
            or any(v["status"] not in {"ok", "skipped"} for v in data["images"])
            or bool(data.get("limit_warning"))
            or bool(data.get("fact_errors"))
        )
        data["status"] = "needs_input" if not has_text else "partial" if incomplete else "ready"
        data.update(lease="", lease_until="", finished_at=now().isoformat())
        # Save completion before releasing the fence (checkpoint uses the persisted token).
        checkpoint("解析完成，等待核对" if has_text else "请补充正文或图片")
    except InterruptedError:
        return
    except Exception:
        data.update(status="error", error="解析中断，已完成的内容已保留，请重试")
        try:
            checkpoint("解析中断")
        except InterruptedError:
            pass


def blocks(data, only_image=None):
    sources = []
    if only_image is None:
        for name in ["link_body", "manual_body"]:
            if data.get(name):
                sources.append((name, data[name]))
    for image in data["images"]:
        if image.get("text") and (only_image is None or image["id"] == only_image):
            sources.append(("image:" + image["id"], image["text"]))
    for source_id, text in sources:
        # Stable anchors and full raw text are retained even when a paragraph needs splitting.
        for index, start in enumerate(range(0, len(text), 2800)):
            yield f"{source_id}:{index + 1}", text[start : start + 3000]


def update_facts(data, checkpoint, only_image=None):
    completed = data.get("fact_blocks", {})
    if not isinstance(completed, dict):
        completed = {}
    errors = data.setdefault("fact_errors", {})
    facts = {f["id"]: f for f in data.get("facts", [])}
    for anchor, text in blocks(data, only_image):
        key = hashlib.sha256(("evidence-v2:" + anchor + text).encode()).hexdigest()
        if completed.get(anchor) == key:
            continue
        checkpoint("提取攻略要点 · " + anchor)
        try:
            extracted = extract.extract_facts(text)
            for fact in extracted:
                ident = hashlib.sha256(
                    json.dumps([fact["kind"], fact["text"], fact["city"]], ensure_ascii=False).encode()
                ).hexdigest()[:24]
                evidence = {"anchor": anchor, "quote": fact["evidence"]}
                if ident in facts:
                    if evidence not in facts[ident]["sources"]:
                        facts[ident]["sources"].append(evidence)
                else:
                    facts[ident] = {
                        "id": ident,
                        **fact,
                        "sources": [evidence],
                        "candidates": [],
                        "place": None,
                    }
            completed[anchor] = key
            errors.pop(anchor, None)
        except Exception:
            errors[anchor] = "该段要点提取失败；原文已保留，可重试或直接手动核对"
        data.update(facts=list(facts.values()), fact_blocks=dict(completed))
        checkpoint("攻略要点已更新")


def match_places(data, checkpoint):
    if not settings.amap_key:
        return
    from ..providers import amap

    cities = list(dict.fromkeys(f["text"] for f in data.get("facts", []) if f["kind"] == "city"))
    for fact in data.get("facts", []):
        if fact["kind"] != "place" or fact.get("place") or fact.get("match_attempted"):
            continue
        city = fact.get("city") or (cities[0] if len(cities) == 1 else "")
        if not city:
            continue
        checkpoint("匹配地图地点 · " + fact["text"])
        try:
            matches = amap.search_places(city, fact["text"])[:5]
            fact.update(candidates=matches, match_city=city, match_attempted=True)
            exact = [p for p in matches if p["name"] == fact["text"]]
            if len(exact) == 1:
                fact["place"] = exact[0]
        except Exception:
            fact["match_error"] = "地点匹配未完成，可指定城市后重试"
        checkpoint("地图地点已更新")


def invalidate_source(data, prefix):
    for fact in data.get("facts", []):
        fact["sources"] = [s for s in fact["sources"] if not s["anchor"].startswith(prefix)]
    data["facts"] = [f for f in data.get("facts", []) if f["sources"]]
    data["fact_blocks"] = {a: h for a, h in data.get("fact_blocks", {}).items() if not a.startswith(prefix)}
    data["fact_errors"] = {a: e for a, e in data.get("fact_errors", {}).items() if not a.startswith(prefix)}
