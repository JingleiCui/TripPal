"""附件解析入口：按扩展名/内容选择解析器，返回 (kind, parsed, suggestion)。"""

from __future__ import annotations

import os

from .gpx import parse_gpx
from .order import parse_order
from .screenshot import parse_screenshot, screenshot_suggestion


def analyze(name: str, raw_bytes: bytes, vision_reader=None):
    """vision_reader 可注入，便于单测；None 时使用真实视觉通道。"""
    ext = os.path.splitext(name or "")[1].lower()
    if ext == ".gpx":
        try:
            parsed = parse_gpx(raw_bytes)
            return "gpx", parsed, _gpx_suggestion(parsed)
        except ValueError as exc:
            return "unknown", {"error": str(exc)}, "无法解析该 GPX 文件，请确认文件格式。"
    if ext in {".txt", ".md", ".csv", ".json"}:
        text = raw_bytes.decode("utf-8", errors="ignore")
        if text.strip():
            parsed = parse_order(text)
            return "order", parsed, _order_suggestion(parsed)
        return "unknown", {}, "文件为空或无法解码为文本。"
    if ext in {".png", ".jpg", ".jpeg", ".webp"}:
        try:
            mime, parsed = parse_screenshot(raw_bytes, reader=vision_reader)
        except ValueError as exc:
            parsed = {
                "status": "error",
                "fields": {},
                "unknowns": [],
                "requires_confirmation": True,
                "synthetic": False,
                "source": {"provider": "none"},
                "error": str(exc),
            }
            return "screenshot", parsed, screenshot_suggestion(name, parsed)
        parsed["mime"] = mime
        return "screenshot", parsed, screenshot_suggestion(name, parsed)
    return "unknown", {}, "暂不支持自动解析该类型，可手动录入。"


def _gpx_suggestion(parsed):
    km = parsed.get("distance_meters", 0) / 1000
    return (
        f"检测到约 {km:.1f} 公里轨迹，共 {parsed.get('point_count', 0)} 个轨迹点。"
        "可将起点、终点或关键途经点作为当天兴趣点加入行程。"
    )


def _order_suggestion(parsed):
    cities = parsed.get("cities") or []
    dates = parsed.get("dates") or []
    venues = parsed.get("venues") or []
    if not cities and not dates and not venues:
        return "未能从文本中识别到明确的城市 / 日期 / 场所，请手动补充。"
    parts = []
    if cities:
        parts.append("城市 " + "、".join(cities))
    if dates:
        parts.append("日期 " + "、".join(dates))
    if venues:
        parts.append("场所 " + "、".join(venues[:3]))
    return "从订单中识别到：" + "；".join(parts) + "。建议据此核对或新增行程项。"
