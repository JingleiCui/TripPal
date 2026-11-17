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


def pdf(plan):
    from reportlab.pdfgen import canvas
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.cidfonts import UnicodeCIDFont

    pdfmetrics.registerFont(UnicodeCIDFont("STSong-Light"))
    buf = BytesIO()
    c = canvas.Canvas(buf, pagesize=(595, 842))
    c.setTitle(plan["title"])
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
