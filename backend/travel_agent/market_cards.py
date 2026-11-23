"""Extract display cards from provider Markdown without interpreting masked prices."""

import re
from urllib.parse import urlparse
from .providers.base import safe_url

MARKET_LINK = re.compile(r"(?<!!)\[([^\]]+)\]\((https?://[^\s)]+)\)")
MARKET_PHOTO = re.compile(r"!\[[^\]]*\]\((https?://[^\s)]+)\)")
MASKED_PRICE = re.compile(r"[xX*×～~—–\-]|[〇零]")
PRICE_NUMBER = re.compile(r"(?:[￥¥]\s*)?(\d+(?:,\d{3})*(?:\.\d{1,2})?)\s*(?:元)?")


def reference_price(text):
    """Parse an unmasked single price into a reference number, never a confirmed amount."""
    value = str(text or "").strip()
    if not value or MASKED_PRICE.search(value):
        return None
    match = PRICE_NUMBER.search(value)
    if not match:
        return None
    number = float(match.group(1).replace(",", ""))
    return number if 0 <= number <= 10000000 else None


def price_basis(text):
    value = str(text or "")
    if "人均" in value:
        return "人均"
    if "起" in value:
        return "起价"
    if "/晚" in value or "每晚" in value or "一晚" in value:
        return "每晚"
    return "参考"


def market_url(value):
    parsed = urlparse(value)
    if parsed.scheme == "http" and (
        parsed.hostname == "dpurl.cn" or (parsed.hostname or "").endswith(".meituan.net")
    ):
        value = "https://" + value[len("http://") :]
    return safe_url(value)


def cards_from_markdown(text):
    items = []
    links = list(MARKET_LINK.finditer(text))
    photos = list(MARKET_PHOTO.finditer(text))
    for index, link in enumerate(links):
        if not market_url(link.group(2)):
            continue
        start = text.rfind("\n", 0, link.start()) + 1
        end = text.find("\n", link.end())
        end = end if end >= 0 else len(text)
        line = text[start:end]
        next_link = links[index + 1].start() if index + 1 < len(links) else len(text)
        following = text[end:next_link]
        price = re.search(r"\*\*([^*\n]*[￥¥][^*\n]*)\*\*", line)
        if not price:
            price = re.search(r"((?:\d+晚共)?[￥¥]\s*\d[\d.,Xx*×～~\-]*(?:元)?(?:起)?)", line)
        if not price and re.search(r"房|床|㎡|人入住|车次|机票", line):
            boundary = min([p.start() for p in photos if link.end() < p.start() < next_link] or [next_link])
            nearby = text[link.end() : min(boundary, link.end() + 400)]
            price = re.search(r"\*\*([^*\n]*[￥¥][^*\n]*)\*\*", nearby)
        if not price:
            # A general merchant/homepage link is not a priced product.
            continue
        previous_photos = [
            p
            for p in photos
            if p.end() <= link.start()
            and link.start() - p.end() < 600
            and (index == 0 or p.start() > links[index - 1].end())
        ]
        photo = previous_photos[-1] if previous_photos else None
        specification = line.replace(link.group(0), "").replace("**", "").strip()
        specification = specification.replace(price.group(1), "").strip()
        details = []
        for detail_line in following.splitlines():
            value = detail_line.strip()
            if value.startswith("🌟"):
                details.append(value.lstrip("🌟 ·"))
                break
            if value and (value.startswith("#") or value.startswith("![") or value.startswith("🔍")):
                break
        items.append(
            {
                "title": link.group(1).replace("**", ""),
                "url": market_url(link.group(2)),
                "photo": market_url(photo.group(1)) if photo else None,
                "price_text": price.group(1).strip(),
                "reference_price_cny": reference_price(price.group(1).strip()),
                "price_basis": price_basis(price.group(1).strip()),
                "specification": specification[:500],
                "details": "\n".join(details)[:1200],
            }
        )
    return items


def merchant_facts_from_markdown(text):
    fields = []
    allowed = "商家地址|参考人均|营业时间|联系电话|电话|特色服务|推荐菜|招牌菜|菜品"
    for match in re.finditer(r"(?m)^(?:[-*]\s*)?\*\*(" + allowed + r")\*\*\s*[:：]\s*([^\n]+)", text):
        fields.append({"label": match.group(1), "value": match.group(2).replace("**", "").strip()[:500]})
    if fields:
        merchant = MARKET_LINK.search(text)
        if merchant:
            fields.insert(0, {"label": "平台门店", "value": merchant.group(1).replace("**", "")})
    return fields
