"""GPX 轨迹解析：从 .gpx 提取轨迹点、总距离、起终点与途经点（纯标准库）。"""

import math
import xml.etree.ElementTree as ET


def haversine(lon1, lat1, lon2, lat2):
    radius = 6371000.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return 2 * radius * math.asin(min(1.0, math.sqrt(a)))


def _local(tag):
    return tag.split("}")[-1]


def parse_gpx(raw_bytes):
    text = raw_bytes.decode("utf-8", errors="ignore")
    try:
        root = ET.fromstring(text)
    except ET.ParseError as exc:
        raise ValueError(f"GPX 解析失败：{exc}") from exc
    points = []
    for element in root.iter():
        if _local(element.tag) in {"trkpt", "wpt", "rtept"}:
            lat = element.get("lat")
            lon = element.get("lon")
            if lat and lon:
                try:
                    points.append((float(lon), float(lat)))
                except ValueError:
                    continue
    if len(points) < 2:
        raise ValueError("GPX 未包含足够的轨迹或途经点")
    total = sum(
        haversine(points[i][0], points[i][1], points[i + 1][0], points[i + 1][1])
        for i in range(len(points) - 1)
    )
    names = []
    for element in root.iter():
        if _local(element.tag) == "wpt":
            nm = element.findtext("name")
            if nm:
                names.append(nm.strip())
    return {
        "point_count": len(points),
        "distance_meters": round(total),
        "start": {"lon": points[0][0], "lat": points[0][1]},
        "end": {"lon": points[-1][0], "lat": points[-1][1]},
        "waypoints": names[:20],
    }
