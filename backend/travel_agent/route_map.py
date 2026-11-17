"""真实行程地图：把行程里的真实经纬度与 polyline 交给高德静态图渲染。

路书预览与 PDF 导出共用同一张图，保证「页面上看到的」和「下载到的」是同一份
真实地图路线，而不是 SVG 插画示意图。没有配置 Key 或网络失败时返回 None，
调用方必须如实降级提示，不得用假坐标画一张示意图冒充地图。
"""
from __future__ import annotations

import json
import threading
import time
import urllib.parse
import urllib.request

from .config import settings

# 与路书页面 DAY 配色一致
DAY_COLORS = ["0xEA6E4E", "0x2E9E82", "0x7B8BD8", "0xE8A93C", "0xB98CD8"]
MARKER_LABELS = "123456789ABCDEFGH"

_CACHE: dict[str, tuple[float, bytes | None]] = {}
_LOCK = threading.Lock()
_TTL = 300.0


def _cache_key(ident: str, version: int, size: str) -> str:
    return f"{ident}:{version}:{size}"


def _valid_point(value) -> bool:
    if not isinstance(value, (list, tuple)) or len(value) < 2:
        return False
    lon, lat = value[0], value[1]
    try:
        lon, lat = float(lon), float(lat)
    except (TypeError, ValueError):
        return False
    return -180 <= lon <= 180 and -90 <= lat <= 90


def _fmt(points: list[tuple[float, float]]) -> str:
    return ";".join(f"{lon:.6f},{lat:.6f}" for lon, lat in points)


def _sample(points: list[tuple[float, float]], limit: int = 80):
    """静态图 URL 有长度上限；保留首尾，等距抽稀，不改变路线形状。"""
    if len(points) <= limit:
        return points
    step = (len(points) - 1) / (limit - 1)
    picked = [points[round(i * step)] for i in range(limit)]
    picked[0], picked[-1] = points[0], points[-1]
    return picked


def _collect(plan: dict):
    """按天汇总真实站点坐标与真实路线折线。"""
    marker_groups: list[str] = []
    path_groups: list[str] = []
    for index, day in enumerate(plan.get("days", [])):
        color = DAY_COLORS[index % len(DAY_COLORS)]
        label = MARKER_LABELS[index % len(MARKER_LABELS)]
        coords: list[tuple[float, float]] = []
        for stop in day.get("stops", []):
            point = (stop.get("lon"), stop.get("lat"))
            if _valid_point(point):
                coords.append((float(point[0]), float(point[1])))
        if coords:
            marker_groups.append(f"large,{color},{label}:{_fmt(coords)}")

        for route in day.get("routes", []):
            raw = route.get("polyline") or []
            line = [
                (float(p[0]), float(p[1]))
                for p in raw
                if _valid_point(p)
            ]
            if len(line) >= 2:
                path_groups.append(f"8,{color},1,,:{_fmt(_sample(line))}")
        # 没有 polyline 时，用真实站点坐标连一段，避免路线整段缺失。
        if not day.get("routes") and len(coords) >= 2:
            path_groups.append(f"8,{color},1,,:{_fmt(coords)}")
    return marker_groups, path_groups


def build(plan: dict, *, size: str = "640*900") -> bytes | None:
    """请求高德静态图；返回 PNG bytes，失败返回 None。"""
    if not settings.amap_key:
        return None
    marker_groups, path_groups = _collect(plan)
    if not marker_groups and not path_groups:
        return None
    params = {"size": size, "scale": "2", "key": settings.amap_key}
    if marker_groups:
        params["markers"] = "|".join(marker_groups)
    if path_groups:
        params["paths"] = "|".join(path_groups)
    url = "https://restapi.amap.com/v3/staticmap?" + urllib.parse.urlencode(params)
    try:
        request = urllib.request.Request(url, headers={"User-Agent": "Tripal/1.0"})
        with urllib.request.urlopen(request, timeout=15) as response:
            if response.status != 200:
                return None
            data = response.read()
        if not data.startswith(b"\x89PNG"):
            return None
        return data
    except Exception:
        return None


def route_map_png(plan: dict, *, ident: str = "", version: int = 0, size: str = "640*900"):
    """带进程内缓存的取图入口。缓存键包含行程版本，改行程后自动失效。"""
    key = _cache_key(ident, version, size) if ident else _cache_key(json.dumps(plan, sort_keys=True)[:64], 0, size)
    now = time.time()
    with _LOCK:
        hit = _CACHE.get(key)
        if hit and now - hit[0] < _TTL:
            return hit[1]
    png = build(plan, size=size)
    with _LOCK:
        _CACHE[key] = (now, png)
        if len(_CACHE) > 64:
            for stale in sorted(_CACHE, key=lambda k: _CACHE[k][0])[: len(_CACHE) - 32]:
                _CACHE.pop(stale, None)
    return png


def budget_notice(plan: dict) -> str:
    """真实地图不可用时给前端/PDF 的诚实说明。"""
    if not settings.amap_key:
        return "未配置高德 Web 服务 Key，暂无法展示真实底图"
    return "地图服务暂不可用，请稍后重试"
