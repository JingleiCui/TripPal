"""订单 / 行程单文本解析：从粘贴的订单或行程单文本中提取城市、日期、金额与场所。

仅做结构化抽取，不推断缺失信息；未识别到的字段留空，交给用户或 Agent 补全。
"""

import re


_CITY_HINT = re.compile(r"([\u4e00-\u9fa5]{2,8}?(?:市|省|区|县|自治州))")
_MUNICIPAL = re.compile(
    r"(上海|北京|天津|重庆|广州|深圳|杭州|成都|武汉|西安|南京|苏州|青岛|厦门|长沙|昆明|三亚|大连|宁波|无锡|福州|合肥|郑州|济南|哈尔滨|沈阳|南昌|南宁|贵阳|兰州|海口|常州|温州|佛山|东莞|珠海|桂林|丽江|拉萨|乌鲁木齐|呼和浩特|石家庄|太原|洛阳|徐州|潍坊|南通|烟台|泉州|嘉兴|绍兴|昆山|义乌|张家界|黄山|婺源|敦煌|大理|三亚)"
)
_DATE_HINT = re.compile(r"\d{4}-\d{2}-\d{2}")
_AMOUNT_HINT = re.compile(r"[¥￥]\s?([\d,]+(?:\.\d+)?)")
_VENUE_HINT = re.compile(r"酒店|宾馆|民宿|客栈|公寓|航班|车次|高铁|机票|火车|船票")
_ORDER_NO_HINT = re.compile(r"(?:订单号|订单编号|No\.?|编号|单号)[:：]?\s*([A-Za-z0-9\-]{6,})")


def parse_order(text):
    cities = [c for c in _CITY_HINT.findall(text)] + _MUNICIPAL.findall(text)
    dates = _DATE_HINT.findall(text)
    amounts = [a.replace(",", "") for a in _AMOUNT_HINT.findall(text)]
    order_nos = _ORDER_NO_HINT.findall(text)
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    venues = [line[:80] for line in lines if _VENUE_HINT.search(line)]
    return {
        "cities": list(dict.fromkeys(cities))[:5],
        "dates": list(dict.fromkeys(dates))[:5],
        "amounts": amounts[:10],
        "order_no": order_nos[:3],
        "venues": venues[:10],
        "line_count": len(lines),
    }


def looks_like_travel(text):
    return bool(_VENUE_HINT.search(text) or _CITY_HINT.search(text) or _DATE_HINT.search(text))
