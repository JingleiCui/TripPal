"""旅行截图解析：校验图片 → 调用视觉通道 → 生成面向对话 Agent 的建议文本。

只输出「候选事实」，不推断、不把截图文字当成平台事实；解析结果带 status，
前端据此决定是否允许「把识别结果交给助手」。
"""

from __future__ import annotations

from .. import vision

MAX_IMAGE_BYTES = 5 * 1024 * 1024


def detect_mime(raw: bytes):
    """按文件头判断图片类型，拒绝把任意字节交给视觉服务。"""
    if raw.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if raw.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if raw[:4] == b"RIFF" and raw[8:12] == b"WEBP":
        return "image/webp"
    return None


def validate_image(raw: bytes):
    if not raw:
        raise ValueError("截图内容为空")
    if len(raw) > MAX_IMAGE_BYTES:
        raise ValueError("截图超过 5 MB，请压缩后重试")
    mime = detect_mime(raw)
    if not mime:
        raise ValueError("文件不是可识别的图片格式（支持 PNG / JPEG / WebP）")
    return mime


def _describe(name, parsed):
    fields = parsed.get("fields") or {}
    lines = [
        f"我上传了一张旅行截图「{name}」，以下是从图中识别出的候选信息"
        f"（来源：{'合成演示数据' if parsed.get('synthetic') else '视觉模型识别'}，"
        "尚未核实，不能当作平台的开放时间或价格）："
    ]
    labels = (
        ("cities", "目的地"),
        ("dates", "日期"),
        ("places", "想去的地方"),
        ("days", "天数"),
        ("budget_text", "预算 / 价格"),
        ("notes", "备注"),
    )
    for key, label in labels:
        value = fields.get(key)
        if isinstance(value, list):
            value = "、".join(value) if value else ""
        if value:
            lines.append(f"{label}：{value}")
    raw_text = (fields.get("raw_text") or "").strip()
    if raw_text:
        lines.append("图中文字摘录：" + raw_text[:120])
    unknowns = parsed.get("unknowns") or []
    if unknowns:
        lines.append("未识别到：" + "、".join(unknowns) + "（请继续追问，不要替我假设）")
    lines.append("请按这些条件继续规划；如果缺少目的地或天数，先向我确认。")
    return "\n".join(lines)[:1200]


def _gap(name, parsed):
    if parsed.get("status") == "error":
        reason = parsed.get("error") or "识别服务未完成请求"
        return f"截图「{name}」识别失败：{reason}。截图内容没有被读取，请手动录入关键信息。"
    return (
        f"截图「{name}」未能识别：{parsed.get('note') or '截图识别不可用'} "
        "截图内容没有被读取，请手动录入关键信息。"
    )


def parse_screenshot(raw_bytes, reader=None):
    """返回 (mime, parsed)。reader 可注入，便于单测与未来接入其他 OCR provider。"""
    mime = validate_image(raw_bytes)
    read = reader or vision.read_screenshot
    try:
        parsed = read(raw_bytes, mime)
    except Exception as exc:  # 视觉通道任何异常都表现为明确缺口，不落到猜测内容
        parsed = {
            "status": "error",
            "fields": {},
            "unknowns": [],
            "requires_confirmation": True,
            "synthetic": False,
            "source": {"provider": "none"},
            "error": f"截图识别异常：{type(exc).__name__}",
        }
    if not isinstance(parsed, dict):
        parsed = {
            "status": "error",
            "fields": {},
            "unknowns": [],
            "requires_confirmation": True,
            "synthetic": False,
            "source": {"provider": "none"},
            "error": "截图识别返回结构不符合约定",
        }
    parsed.setdefault("status", "error")
    parsed.setdefault("requires_confirmation", True)
    return mime, parsed


def screenshot_suggestion(name, parsed):
    if parsed.get("status") in {"ok", "synthetic"}:
        return _describe(name, parsed)
    return _gap(name, parsed)
