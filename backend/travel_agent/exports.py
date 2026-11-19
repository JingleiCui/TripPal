from html import escape
from io import BytesIO


def markdown(plan):
    lines = [
        "# " + plan["title"],
        "",
        "合成测试流程，不可用于实际出游。"
        if plan.get("fixture")
        else "旅行草案；开放、预约与最终成交价格需在出行前确认。",
        "",
        plan.get("rationale", ""),
    ]
    for day in plan.get("days", []):
        lines.extend(["", f"## 第 {day['day']} 天 · {day.get('date') or '日期未确认'}"])
        detail = day.get("daily_details", {})
        timeline = detail.get("timeline") or [
            {
                "kind": "place",
                "label": "游览",
                "start": p["planned_start"],
                "end": p["planned_end"],
                "place": p,
            }
            for p in day["stops"]
        ]
        for index, entry in enumerate(timeline):
            for leg in detail.get("legs", []):
                if leg.get("before_index") == index:
                    lines.append(
                        f"  交通：{leg['from_name']} → {leg['to_name']}，{str(leg.get('minutes')) + ' 分钟' if leg.get('minutes') is not None else '耗时待核实'}"
                    )
                    for step in leg.get("instructions", []):
                        lines.append("    " + step)
            p = entry["place"]
            source = p.get("source", {})
            lines.extend(
                [
                    f"- {entry['start']}—{entry['end']} {entry['label']} · {p['name']}",
                    f"  {p.get('address', '')}；营业或开放：{p.get('opening_text') or '待核实'}",
                    f"  参考消费：{p.get('price_text') or '未提供'}；联系：{p.get('phone') or '未提供'}",
                    f"  来源：{source.get('url') or source.get('provider')}，获取于 {source.get('retrieved_at', '未知')}",
                ]
            )
        if detail.get("stay") and detail.get("hotel"):
            stay = detail["stay"]
            lines.append(
                f"  住宿日期：{stay.get('checkin') or '待定'} 至 {stay.get('checkout') or '待定'}，{stay['nights']} 晚；尚未预订。"
            )
    lines.extend(
        [
            "",
            "## 待确认事项",
            *["- " + w for w in plan.get("warnings", [])],
            *["- " + w for w in plan.get("budget", {}).get("unknown_items", [])],
        ]
    )
    ledger = plan.get("expense_ledger")
    if ledger:
        total = ledger["trip"]
        lines.extend(
            [
                "",
                "## 吃住行费用核算",
                f"已计参考小计：¥{total['priced_subtotal_cny']:.2f}；总预算：{total['limit_cny'] if total['limit_cny'] is not None else '未设置'}；仍有 {total['unpriced_count']} 项未计价。",
            ]
        )
        if total["status"] == "over_budget":
            lines.append(f"按已计参考费用已超出总预算 ¥{total['overrun_cny']:.2f}，尚未计价的项目还需补充。")
        elif not total["is_complete"]:
            lines.append("金额尚未核齐，不能据此判断未超预算。")
        for day in ledger["days"]:
            lines.append(
                f"### 第 {day['day']} 天：已计 ¥{day['priced_subtotal_cny']:.2f}，未计 {day['unpriced_count']} 项"
            )
            for row in day["rows"]:
                price = (
                    f"¥{row['subtotal_cny']:.2f}"
                    if row["subtotal_cny"] is not None
                    else "待核实（不按 0 元计）"
                )
                lines.append(f"- {row['category_name']} · {row['label']}：{price}")
        lines.append(ledger["notice"])
    lodging = plan.get("lodging", {}).get("raw_text")
    if lodging:
        lines.extend(["", "## 美团查询原文", lodging])
    return "\n".join(lines)


def pdf(plan, map_png=None):
    """设计版路书 PDF：高密度两栏、Logo 与标题同行、右侧嵌入真实地图路线。

    后端只产出 PDF，绝不把 HTML 当成路书交付。任何绘制异常都回退到纯文本 PDF，
    保证下载物始终是合法的 application/pdf。
    """
    from reportlab.pdfgen import canvas
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.cidfonts import UnicodeCIDFont
    from reportlab.lib.colors import HexColor
    from reportlab.lib.utils import ImageReader

    pdfmetrics.registerFont(UnicodeCIDFont("STSong-Light"))
    buf = BytesIO()
    c = canvas.Canvas(buf, pagesize=(595, 842))
    c.setTitle(plan.get("title", "TripPal 路书"))

    CREAM = HexColor("#FFF7F1")
    CORAL = HexColor("#FF8A6B")
    CORAL_DEEP = HexColor("#EA6E4E")
    MINT = HexColor("#2E9E82")
    INK = HexColor("#3B3432")
    MUTED = HexColor("#988D87")
    BUTTER = HexColor("#FFCE73")
    LINE = HexColor("#F0E3D9")
    WHITE = HexColor("#FFFFFF")
    DAY_HEX = ["#EA6E4E", "#2E9E82", "#7B8BD8", "#E8A93C", "#B98CD8"]
    font = "STSong-Light"
    W, H = 595, 842
    LEFT, RIGHT = 30, 565
    PAGE_W = RIGHT - LEFT
    COL_L, GAP = 318, 14
    COL_R = PAGE_W - COL_L - GAP
    RX = LEFT + COL_L + GAP

    def txt(x, y, value, size=8, color=INK, width=None):
        """单行文本，超出宽度时按字符截断并加省略号。"""
        c.setFont(font, size)
        c.setFillColor(color)
        s = str(value if value is not None else "")
        if width:
            if pdfmetrics.stringWidth(s, font, size) > width:
                while s and pdfmetrics.stringWidth(s + "…", font, size) > width:
                    s = s[:-1]
                s += "…"
        c.drawString(x, y, s)

    def right_txt(x, y, value, size=8, color=INK):
        c.setFont(font, size)
        c.setFillColor(color)
        c.drawRightString(x, y, str(value if value is not None else ""))

    def money(value):
        return "待核实" if value is None else "¥" + f"{value:,.0f}"

    def card(x, y, w, h, radius=8):
        c.setFillColor(WHITE)
        c.roundRect(x, y, w, h, radius, fill=1, stroke=0)

    def logo(x, y, s=1.0):
        """与前端 TripalMark 同构：方中带软的箱体 + 居中五官 + 黄色四角星光。"""
        def X(v):
            return x + v * s
        def Y(v):
            return y + v * s
        # 奶油白底托，让珊瑚箱体在珊瑚页眉上清晰可辨
        c.setFillColor(WHITE)
        c.roundRect(X(0), Y(0), 56 * s, 54 * s, 10 * s, fill=1, stroke=0)
        # 提手
        c.setStrokeColor(CORAL_DEEP)
        c.setLineWidth(6 * s)
        c.setLineCap(1)
        p = c.beginPath()
        p.moveTo(X(20), Y(37))
        p.lineTo(X(20), Y(30))
        p.curveTo(X(20), Y(48), X(40), Y(48), X(40), Y(30))
        p.lineTo(X(40), Y(37))
        c.drawPath(p, stroke=1, fill=0)
        # 箱体
        c.setFillColor(CORAL)
        c.roundRect(X(6), Y(4), 44 * s, 34 * s, 11 * s, fill=1, stroke=0)
        # 腮红 / 眼睛 / 微笑
        c.setFillColor(HexColor("#FFC2AD"))
        c.ellipse(X(12), Y(13), X(18), Y(16), fill=1, stroke=0)
        c.ellipse(X(38), Y(13), X(44), Y(16), fill=1, stroke=0)
        c.setFillColor(INK)
        c.ellipse(X(19), Y(19), X(23), Y(24), fill=1, stroke=0)
        c.ellipse(X(33), Y(19), X(37), Y(24), fill=1, stroke=0)
        c.setStrokeColor(INK)
        c.setLineWidth(1.6 * s)
        q = c.beginPath()
        q.moveTo(X(25), Y(13))
        q.curveTo(X(27), Y(9), X(29), Y(9), X(31), Y(13))
        c.drawPath(q, stroke=1, fill=0)
        # 黄色四角星光（必须是 #FFCE73）
        cx, cy, r = X(48), Y(48), 9 * s
        c.setFillColor(BUTTER)
        star = c.beginPath()
        star.moveTo(cx, cy + r)
        star.lineTo(cx + r * 0.26, cy + r * 0.26)
        star.lineTo(cx + r, cy)
        star.lineTo(cx + r * 0.26, cy - r * 0.26)
        star.lineTo(cx, cy - r)
        star.lineTo(cx - r * 0.26, cy - r * 0.26)
        star.lineTo(cx - r, cy)
        star.lineTo(cx - r * 0.26, cy + r * 0.26)
        star.close()
        c.drawPath(star, fill=1, stroke=0)

    def page_header(first):
        c.setFillColor(CREAM)
        c.rect(0, 0, W, H, fill=1, stroke=0)
        if first:
            # 高密度页眉：Logo 与右侧标题/元信息同一行，不额外占一整行
            c.setFillColor(CORAL)
            c.rect(0, H - 74, W, 74, fill=1, stroke=0)
            logo(LEFT, H - 62, 0.62)
            tx = LEFT + 44
            txt(tx, H - 24, plan.get("title", "行程路书"), 15, WHITE, 430)
            txt(tx, H - 42, "TripPal 旅伴 · ROUTE BOOK / 路书", 7.5, HexColor("#FFE4DA"), 430)
            days = plan.get("days", [])
            stops = sum(len(d.get("stops", [])) for d in days)
            start = (plan.get("requirements") or {}).get("start_date") or "日期待定"
            txt(tx, H - 57, f"{start} · 由 TripPal AI 生成 · {len(days)} 天 {stops} 站", 7.5, HexColor("#FFE4DA"), 430)
        else:
            c.setFillColor(CORAL)
            c.rect(0, H - 28, W, 28, fill=1, stroke=0)
            txt(LEFT, H - 19, "TripPal 旅伴 · " + plan.get("title", "路书"), 8.5, WHITE, 430)
        return H - (90 if first else 40)

    def weather(date):
        casts = [
            cast
            for f in (plan.get("weather") or {}).get("forecasts", [])
            for cast in (f.get("casts") or [])
        ]
        if not date:
            return None
        short = str(date)[5:]
        hit = next(
            (x for x in casts if x.get("date") == date or str(x.get("date", "")).endswith(short)),
            None,
        )
        if not hit:
            return None
        return (hit.get("dayweather") or "天气") + (
            " " + hit["daytemp"] + "°" if hit.get("daytemp") else ""
        )

    def footer():
        c.setStrokeColor(LINE)
        c.setLineWidth(0.6)
        c.line(LEFT, 38, RIGHT, 38)
        txt(LEFT, 26, "TripPal 旅伴 · 一句话，安排好下一程。", 7, MUTED, 250)
        right_txt(RIGHT, 26, "由 TripPal AI 生成 · 出行前请核实营业、预约与价格", 7, MUTED)

    try:
        y = page_header(first=True)
        days = plan.get("days", [])
        known_stops = sum(len(d.get("stops", [])) for d in days)
        walk_km = sum(d.get("known_route_walking_meters", 0) or 0 for d in days) / 1000
        ledger = plan.get("expense_ledger") or {}
        budget_by_day = {d.get("day"): d for d in ledger.get("days", [])}

        # ---- 统计条 ----
        card(LEFT, y - 40, PAGE_W, 40)
        stats = [
            (f"{len(days)} 天", "行程天数", CORAL_DEEP),
            (f"{known_stops} 站", "地点数量", MINT),
            (f"{walk_km:.1f} km", "已知路段步行", HexColor("#E8A93C")),
            (money((plan.get("budget") or {}).get("known_subtotal_cny")), "已计参考费用", HexColor("#7B8BD8")),
        ]
        cell = PAGE_W / 4
        for i, (value, label, color) in enumerate(stats):
            cx = LEFT + i * cell + cell / 2
            c.setFillColor(color)
            c.setFont(font, 12)
            c.drawCentredString(cx, y - 16, value)
            c.setFillColor(MUTED)
            c.setFont(font, 7)
            c.drawCentredString(cx, y - 29, label)
        y -= 54

        top_y = y
        # ---- 右栏：真实地图（高德静态图，含真实坐标与 polyline 路线） ----
        map_h = 0
        if map_png:
            try:
                img = ImageReader(BytesIO(map_png))
                iw, ih = img.getSize()
                map_h = min(300, ih / iw * COL_R)
                card(RX - 6, top_y - map_h - 34, COL_R + 12, map_h + 42)
                txt(RX, top_y - 14, "全程路线 / REAL ROUTE MAP", 8, INK, COL_R)
                c.drawImage(img, RX, top_y - map_h - 20, width=COL_R, height=map_h, mask="auto")
                txt(RX, top_y - map_h - 30, "高德地图 · GCJ-02 · 真实地点与路线", 6.5, MUTED, COL_R)
            except Exception:
                map_png = None
                map_h = 0
        if not map_png:
            from . import route_map
            map_h = 66
            card(RX - 6, top_y - map_h - 34, COL_R + 12, map_h + 42)
            txt(RX, top_y - 14, "全程路线 / REAL ROUTE MAP", 8, INK, COL_R)
            txt(RX, top_y - 34, route_map.budget_notice(plan), 7, MUTED, COL_R)
            txt(RX, top_y - 48, "真实坐标与路线数据仍保留在行程中", 7, MUTED, COL_R)

        ry = top_y - map_h - 48
        card(RX - 6, ry - 92, COL_R + 12, 96)
        txt(RX, ry - 14, "路线图例 / DAYS", 8, INK, COL_R)
        for i, day in enumerate(days[:5]):
            c.setFillColor(HexColor(DAY_HEX[i % len(DAY_HEX)]))
            c.circle(RX + 4, ry - 30 - i * 13, 3, fill=1, stroke=0)
            txt(RX + 12, ry - 33 - i * 13, f"DAY {day.get('day', i + 1):02d} · {day.get('city', '')}", 7, INK, COL_R - 16)

        ry -= 104
        card(RX - 6, ry - 66, COL_R + 12, 70)
        txt(RX, ry - 14, "打包清单 / PACKING", 8, INK, COL_R)
        txt(RX, ry - 30, "身份证件 · 充电宝 · 舒适步行鞋", 7, MUTED, COL_R)
        txt(RX, ry - 44, "雨具 · 常用药 · 纸巾", 7, MUTED, COL_R)
        txt(RX, ry - 58, "出行前核实营业、预约与价格", 6.5, MUTED, COL_R)

        # ---- 左栏：每日行程（天气与花费都在当天块内） ----
        lx, ly = LEFT, top_y
        txt(lx, ly - 12, "每日行程 / DAY BY DAY", 9, INK, COL_L)
        ly -= 24
        for i, day in enumerate(days):
            stops = day.get("stops", [])
            card_h = 46 + len(stops) * 14
            if ly - card_h < 64:
                c.showPage()
                ly = page_header(first=False)
                txt(lx, ly - 12, "每日行程 / DAY BY DAY（续）", 9, INK, COL_L)
                ly -= 24
            color = HexColor(DAY_HEX[i % 3])
            card(lx - 6, ly - card_h, COL_L + 12, card_h + 4)
            txt(lx, ly - 14, f"DAY {day.get('day', i + 1):02d}  {str(day.get('date') or '日期待定')[5:]}  {day.get('city', '')}", 8.5, color, COL_L)
            bg = ["#FFF3EC", "#ECF8F4", "#F0F2FC"][i % 3]
            c.setFillColor(HexColor(bg))
            c.roundRect(lx, ly - 32, COL_L, 16, 4, fill=1, stroke=0)
            txt(lx + 5, ly - 27, weather(day.get("date")) or "天气待核实 / 出行前请查询预报", 7, INK, 165)
            b = budget_by_day.get(day.get("day")) or {}
            right_txt(lx + COL_L - 5, ly - 27, "当日已知花费 " + money(b.get("priced_subtotal_cny")), 7, color)
            for j, stop in enumerate(stops):
                sy = ly - 46 - j * 14
                txt(lx + 2, sy, str(stop.get("planned_start") or "")[:5], 7, color, 34)
                txt(lx + 38, sy, stop.get("name") or "地点", 8, INK, 188)
                right_txt(lx + COL_L - 4, sy, str(stop.get("price_text") or "待核实")[:10], 7, MINT)
            ly -= card_h + 10

        note = str(plan.get("rationale") or "行程由 AI 依据条件生成。")
        if ly - 76 < 64:
            c.showPage()
            ly = page_header(first=False)
        c.setFillColor(HexColor("#FFF4DE"))
        c.roundRect(lx - 6, ly - 72, COL_L + 12, 74, 8, fill=1, stroke=0)
        txt(lx, ly - 14, "AI 备注 / NOTES", 8, HexColor("#8A6E2E"), COL_L)
        txt(lx, ly - 30, note[:34], 7, HexColor("#7A6540"), COL_L - 8)
        txt(lx, ly - 44, note[34:68], 7, HexColor("#7A6540"), COL_L - 8)
        txt(lx, ly - 60, "营业、预约与最终价格以官方为准；未查到不计为零。", 7, HexColor("#7A6540"), COL_L - 8)

        ly -= 84
        for d in days[:4]:
            if ly < 56:
                c.showPage()
                ly = page_header(first=False)
            txt(lx, ly, f"DAY {d.get('day')}：{d.get('walking_note') or '已知路段步行待核实'}", 7, MUTED, COL_L)
            ly -= 11

        footer()
        c.save()
        return buf.getvalue()
    except Exception:
        return _plain_pdf(plan)


def _plain_pdf(plan):
    """极简兜底：只画文本，不依赖图片与复杂图形。"""
    from reportlab.pdfgen import canvas
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.cidfonts import UnicodeCIDFont

    pdfmetrics.registerFont(UnicodeCIDFont("STSong-Light"))
    buf = BytesIO()
    c = canvas.Canvas(buf, pagesize=(595, 842))
    c.setTitle(plan.get("title", "TripPal 路书"))
    y = 800
    for line in markdown(plan).splitlines():
        for offset in range(0, max(1, len(line)), 45):
            if y < 50:
                c.showPage()
                y = 800
            c.setFont("STSong-Light", 10)
            c.drawString(38, y, line[offset : offset + 45])
            y -= 17
    c.save()
    return buf.getvalue()


def shared_html(plan):
    """Readable, escaped public snapshot; no private records or authenticated API calls."""
    from .providers.amap import place_photo_url
    from .providers.base import safe_url

    def place_card(place, label, time=""):
        photos = [url for photo in place.get("photos", []) if (url := place_photo_url(photo))]
        photo = (
            f'<img src="{escape(photos[0], quote=True)}" alt="{escape(place["name"], quote=True)}" loading="lazy" referrerpolicy="no-referrer">'
            if photos
            else ""
        )
        source = place.get("source", {})
        url = safe_url(source.get("url"))
        link = (
            f'<a href="{escape(url, quote=True)}" target="_blank" rel="noopener noreferrer">查看地点与导航 ↗</a>'
            if url
            else ""
        )
        return f'<article class="place">{photo}<div><small>{escape(label)} · {escape(time)}</small><h3>{escape(place["name"])}</h3><p>{escape(place.get("address", "地址待核实"))}</p><p>{escape(place.get("opening_text") or "营业或开放信息请向场所核实")}</p>{link}</div></article>'

    days = plan.get("days", [])
    tabs = "".join(f'<a href="#day-{d["day"]}">第 {d["day"]} 天</a>' for d in days)
    sections = []
    for day in days:
        cards = "".join(
            place_card(p, "游览", p.get("planned_start", "") + "—" + p.get("planned_end", ""))
            for p in day.get("stops", [])
        )
        meals = "".join(
            place_card(
                m["place"], {"breakfast": "早餐", "lunch": "午餐", "dinner": "晚餐"}.get(m["slot"], "用餐")
            )
            for m in day.get("meals", [])
        )
        sections.append(
            f'<section id="day-{day["day"]}"><header><span>第 {day["day"]} 天</span><h2>{escape(day.get("city") or plan["requirements"]["city"])}</h2><p>{escape(day.get("date") or "日期待定")}</p></header><div class="places">{cards}{meals}</div></section>'
        )
    hotels = "".join(place_card(h, "已选择住宿 · 未代表预订") for h in plan.get("hotels", []))
    hotel_section = (
        f'<section><header><h2>住宿安排</h2></header><div class="places">{hotels}</div></section>'
        if hotels
        else ""
    )
    warning = (
        "合成体验资料，不能用于实际出游。"
        if plan.get("fixture")
        else "只读行程快照。营业、预约和最终价格请在出行前核对。"
    )
    return f"""<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{escape(plan["title"])} · 漫游路书</title><style>
    *{{box-sizing:border-box}}body{{margin:0;background:#fff;color:#222;font:14px/1.8 -apple-system,BlinkMacSystemFont,"PingFang SC",sans-serif}}a{{color:inherit;text-decoration:none}}.shell{{max-width:1000px;margin:auto;padding:32px 24px 70px}}.brand{{font-size:25px;letter-spacing:-1px;font-weight:700;border-bottom:1px solid #eee;padding-bottom:22px}}.intro{{padding:40px 0 24px}}.intro small{{color:#999}}h1{{font-size:34px;line-height:1.4;letter-spacing:-1px;margin:12px 0 16px}}.intro p{{color:#888;font-size:12px}}nav{{display:flex;gap:9px;flex-wrap:wrap;border-bottom:1px solid #eee;padding-bottom:24px}}nav a{{border:1px solid #ddd;border-radius:30px;padding:7px 17px;font-size:12px}}nav a:hover{{background:#222;color:#fff}}section{{padding-top:30px;scroll-margin-top:20px}}section header{{display:flex;gap:15px;align-items:center;margin-bottom:17px}}section header span{{background:#222;color:#fff;padding:7px 13px;border-radius:25px;font-size:11px}}h2{{font-size:22px;margin:0}}header p{{margin:0 0 0 auto;color:#888;font-size:12px}}.places{{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:16px}}.place{{border:1px solid #e9e9e9;border-radius:16px;overflow:hidden;display:flex;min-width:0}}.place>img{{width:125px;object-fit:cover}}.place>div{{padding:20px;min-width:0}}.place small{{font-size:10px;color:#9b8765}}h3{{font-size:16px;margin:8px 0}}.place p{{font-size:11px;color:#888;margin:7px 0;overflow-wrap:anywhere}}.place a{{display:inline-block;font-size:11px;border-bottom:1px solid #aaa;margin-top:10px}}footer{{border-top:1px solid #eee;margin-top:45px;padding-top:22px;font-size:11px;color:#999}}@media(max-width:650px){{h1{{font-size:27px}}.shell{{padding:24px 18px 50px}}.places{{grid-template-columns:1fr}}.place>img{{width:110px}}section header{{gap:10px}}h2{{font-size:19px}}}}@media(prefers-reduced-motion:no-preference){{html{{scroll-behavior:smooth}}}}
    </style></head><body><main class="shell"><div class="brand">漫游。</div><div class="intro"><small>一起期待，下一次出发</small><h1>{escape(plan["title"])}</h1><p>{escape(warning)}</p></div><nav>{tabs}</nav>{"".join(sections)}{hotel_section}<footer>此页不包含私人对话、个人资料、订单确认号或凭证。已计参考小计不能代替完整费用核算；有缺价项目时，不能据此判断未超预算。</footer></main></body></html>"""
