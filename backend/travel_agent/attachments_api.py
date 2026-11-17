"""附件驱动工具触发：上传即解析并生成 Agent 建议动作。"""

import asyncio
import os
from fastapi import APIRouter, Depends, HTTPException, UploadFile
from sqlalchemy import select
from .config import settings
from .db import Session, Attachment
from .security import require_user
from .parsers import analyze

router = APIRouter(prefix="/api/v1")


@router.post("/attachments", status_code=201)
async def upload_attachment(file: UploadFile, owner=Depends(require_user)):
    name = (file.filename or "附件").rsplit("/", 1)[-1][:180]
    ext = os.path.splitext(name)[1].lower()
    if ext not in settings.allowed_attachment_extensions:
        raise HTTPException(415, "不支持的附件类型；允许：" + ", ".join(settings.allowed_attachment_extensions))
    content = await file.read(settings.max_upload_bytes + 1)
    if not content or len(content) > settings.max_upload_bytes:
        raise HTTPException(413, "文件为空或超过大小上限")
    # 截图识别会走网络与视觉模型，放到线程里避免阻塞事件循环。
    kind, parsed, suggestion = await asyncio.to_thread(analyze, name, content)
    with Session.begin() as db:
        att = Attachment(owner=owner, name=name, ext=ext, kind=kind, parsed=parsed, suggestion=suggestion)
        db.add(att)
        db.flush()
        return {
            "id": att.id,
            "name": name,
            "kind": kind,
            "parsed": parsed,
            "suggestion": suggestion,
        }


@router.get("/attachments")
def list_attachments(owner=Depends(require_user)):
    with Session() as db:
        return [
            {
                "id": a.id,
                "name": a.name,
                "kind": a.kind,
                "suggestion": a.suggestion,
                "created": a.created.isoformat(),
            }
            for a in db.scalars(
                select(Attachment).where(Attachment.owner == owner).order_by(Attachment.created.desc())
            )
        ]
