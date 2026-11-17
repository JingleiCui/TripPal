"""中文槽位提取与确定性的防循环提问门控。

提取只给出候选事实；下一步提问由确定性策略决定。
可选槽位只问一次，必填槽位不做静默默认值填充。
"""

import re
from datetime import date, timedelta
from typing import Literal
from pydantic import BaseModel, Field
from langchain_core.messages import SystemMessage, HumanMessage
from .interview import _merge_user_details, _next_question
from .agent.structured import generate
from .models.registry import chat_ready
from .schemas import Requirements, CityStay


class SlotUpdate(BaseModel):
    city_stays: list[CityStay] | None = Field(default=None, description="用户明确指定的每城天数；不自行分配")
    destination: str | None = Field(default=None, description="明确的目的地，没说则留空，不能默认北京")
    duration: str | None = Field(default=None, description="明确旅行总天数，例如 3 days；不能默认")
    start_location: str | None = None
    needs_accommodation: bool | None = None
    interests: str | None = None
    travel_dates: str | None = Field(default=None, description="明确的 YYYY-MM-DD；不确定则留空")
    num_travelers: int | None = Field(default=None, ge=1, le=12)
    budget_cny: int | None = Field(default=None, ge=1, le=1000000)
    transport: Literal["public_transit", "walk", "drive"] | None = None


QUESTIONS = {
    "destination": "你想去哪个城市或目的地？",
    "duration": "这次打算玩几天？",
    "accommodation": "这次需要推荐住宿，还是已经安排好了？可以回答“跳过”。",
    "intent": "这次更想体验什么，比如历史文化、美食或自然？可以跳过。",
    "origin": "准备从哪里出发？不想提供也可以跳过。",
}
CN_NUM = {
    "一": 1,
    "二": 2,
    "两": 2,
    "三": 3,
    "四": 4,
    "五": 5,
    "六": 6,
    "七": 7,
    "八": 8,
    "九": 9,
    "十": 10,
    "十一": 11,
    "十二": 12,
    "十三": 13,
    "十四": 14,
}


def parsed_days(value):
    if not value:
        return None
    match = re.search(
        r"(\d+|十一|十二|十三|十四|[一二两三四五六七八九十])\s*(?:天|日|days?|晚)", str(value), re.I
    )
    if not match:
        return None
    number = match.group(1)
    return int(number) if number.isdigit() else CN_NUM.get(number)


_WD = {"一": 0, "二": 1, "三": 2, "四": 3, "五": 4, "六": 5, "日": 6, "天": 6}
_WD_RE = r"(?:下个?周|下周|本周|这周|星期|周|礼拜)\s*([一二三四五六日天])"


def _resolve_weekday(base, wd, next_week):
    """计算某个星期几的日期；next_week 为真时取下周（严格下一周）。"""
    days = (wd - base.weekday()) % 7
    if days == 0:
        days = 7
    resolved = base + timedelta(days=days)
    if next_week:
        resolved += timedelta(days=7)
    return resolved


def parse_relative_dates(text):
    """解析「下周三」「下周三-下周五」「本周五」等相对日期与区间。

    返回 (travel_dates, duration_days)：travel_dates 为区间起点 ISO 日期，
    duration_days 为区间天数（含首尾）。无法识别时返回 (None, None)。
    """
    base = date.today()
    matches = list(re.finditer(_WD_RE, text))
    dates = []
    for m in matches:
        prefix = text[max(0, m.start() - 2) : m.start()]
        dates.append(_resolve_weekday(base, _WD[m.group(1)], "下" in prefix))
    explicit = re.findall(r"20\d\d-\d\d-\d\d", text)
    if len(explicit) >= 2:
        try:
            a, b = date.fromisoformat(explicit[0]), date.fromisoformat(explicit[1])
            if b < a:
                a, b = b, a
            return a.isoformat(), (b - a).days + 1
        except ValueError:
            pass
    if len(dates) >= 2:
        a, b = dates[0], dates[-1]
        if b < a:
            b += timedelta(days=7)
        return a.isoformat(), (b - a).days + 1
    if len(dates) == 1:
        return dates[0].isoformat(), None
    return None, None


def rule_extract(text, last_question=None):
    result = {}
    count = parsed_days(text)
    if count is not None:
        result["duration"] = f"{count} days"
    # Only known literal city mentions or an answer to a destination question are accepted offline.
    cities = re.findall(
        r"北京|上海|杭州|苏州|南京|成都|重庆|广州|深圳|西安|青岛|厦门|武汉|长沙|天津|昆明|大理|丽江|郑州|哈尔滨|济南|福州|宁波",
        text,
    )
    origin = re.search(r"从([^，。！？,\s]{2,20}?)(?:出发|去|到)", text)
    if origin:
        result["start_location"] = origin.group(1)
    destination = [city for city in dict.fromkeys(cities) if not origin or city not in origin.group(1)]
    if destination:
        result["destination"] = destination[0]
        if len(destination) > 1:
            result["unallocated_destinations"] = destination
    elif last_question == "destination" and re.fullmatch(r"[\u4e00-\u9fffA-Za-z\s]{2,25}", text.strip()):
        result["destination"] = text.strip()
    if last_question == "origin" and not origin and text.strip() not in {"跳过", "不知道", "暂不提供"}:
        result["start_location"] = text.strip()[:100]
    if re.search(
        "不需要住宿|不需要酒店|不用推荐酒店|不用推荐住宿|不要推荐酒店|无需住宿|订好酒店|已有酒店|住朋友家|已经安排|住宿安排好了",
        text,
    ):
        result["needs_accommodation"] = False
    elif re.search("需要住宿|需要酒店|推荐住宿|推荐酒店|帮我找酒店", text):
        result["needs_accommodation"] = True
    if last_question == "accommodation" and text.strip() in {"不需要", "不用", "安排好了"}:
        result["needs_accommodation"] = False
    if last_question == "accommodation" and text.strip() in {"需要", "要"}:
        result["needs_accommodation"] = True
    if last_question == "intent" and text.strip() != "跳过":
        result["interests"] = text.strip()[:500]
    explicit = [
        x for x in ["历史文化", "美食", "博物馆", "公园", "自然", "艺术", "徒步", "亲子"] if x in text
    ]
    if explicit:
        result["interests"] = "、".join(explicit)
    if "自驾" in text:
        result["transport"] = "drive"
    elif "公共交通" in text or "地铁" in text:
        result["transport"] = "public_transit"
    budget = re.search(r"预算\D*?(\d+)", text)
    if budget:
        result["budget_cny"] = int(budget.group(1))
    explicit = re.findall(r"20\d\d-\d\d-\d\d", text)
    if len(explicit) >= 2:
        try:
            a, b = date.fromisoformat(explicit[0]), date.fromisoformat(explicit[1])
            if b < a:
                a, b = b, a
            result["travel_dates"] = a.isoformat()
            if "duration" not in result:
                result["duration"] = f"{(b - a).days + 1} days"
        except ValueError:
            pass
    elif explicit:
        try:
            result["travel_dates"] = date.fromisoformat(explicit[0]).isoformat()
        except ValueError:
            pass
    # 相对日期与区间（如「下周三-下周五」）优先于模型提取，离线可预测。
    if "travel_dates" not in result:
        rel_start, rel_days = parse_relative_dates(text)
        if rel_start:
            result["travel_dates"] = rel_start
            if rel_days and "duration" not in result:
                result["duration"] = f"{rel_days} days"
    if text.strip() in {"跳过", "暂不提供"} and last_question == "origin":
        result["start_location"] = "declined"
    stays = re.findall(
        r"(北京|上海|杭州|苏州|南京|成都|重庆|广州|深圳|西安|青岛|厦门|武汉|长沙|天津|昆明|大理|丽江)\s*(?:玩|待|住|安排)?\s*(\d+|十一|十二|十三|十四|[一二两三四五六七八九十])\s*(?:天|日)",
        text,
    )
    if len(stays) > 1:
        result["city_stays"] = [
            {"city": city, "days": int(n) if n.isdigit() else CN_NUM[n]} for city, n in stays
        ]
        result["destination"] = stays[0][0]
        result["duration"] = str(sum(s["days"] for s in result["city_stays"])) + " days"
    return result


def extract(text, prior, last_question=None, fixture=False):
    fresh = rule_extract(text, last_question)
    source = "deterministic_literal_parser"
    if not fixture and chat_ready():
        response = generate(
            SlotUpdate,
            [
                SystemMessage(
                    content="提取用户本轮明确说出的旅行条件。未说的字段为 null，不能默认目的地或天数；既有条件仅用于理解。"
                ),
                HumanMessage(content=f"既有条件：{prior}\n上一问：{last_question}\n本轮：{text}"),
            ],
            "需求提取",
        )
        fresh = {**{k: v for k, v in response.model_dump().items() if v is not None}, **fresh}
        source = "model_structured_extraction"
    if parsed_days(fresh.get("duration")) is not None and not 1 <= parsed_days(fresh["duration"]) <= 14:
        fresh["duration"] = ""
        return (
            {**_merge_user_details(prior, fresh), "duration": ""},
            "duration",
            "目前支持 1—14 天，请确认这次的天数。",
            source,
        )
    if fresh.get("city_stays"):
        fresh["destination"] = fresh["city_stays"][0]["city"]
        fresh["duration"] = str(sum(x["days"] for x in fresh["city_stays"])) + " days"
        fresh["unallocated_destinations"] = []
    elif fresh.get("destination") and fresh["destination"] != prior.get("destination"):
        # Changing destination invalidates the old per-city allocation.
        prior = {k: v for k, v in prior.items() if k not in {"city_stays", "unallocated_destinations"}}
    slots = _merge_user_details(prior, fresh)
    return slots, None, None, source


def gate(slots, turns, asked, text, plan_now=False):
    if slots.get("unallocated_destinations") and not slots.get("city_stays"):
        return "city_allocation", "这些城市分别安排几天？例如“北京两天、上海两天”。"
    force = plan_now or any(
        word in text for word in ["开始规划", "直接规划", "就这些", "直接生成", "出方案", "开始安排"]
    )
    key = _next_question(slots, turns, force_ready=force, asked=set(asked))
    return key, QUESTIONS.get(key)


def seed_slots(preferences):
    slots = {}
    if preferences.get("default_city"):
        slots["destination"] = preferences["default_city"]
    if preferences.get("default_days"):
        slots["duration"] = str(preferences["default_days"]) + " days"
    if preferences.get("travel_style"):
        slots["interests"] = preferences["travel_style"]
    return slots


def to_requirements(slots):
    return Requirements(
        city=slots["destination"],
        days=parsed_days(slots.get("duration")) or 1,
        origin="" if slots.get("start_location") == "declined" else slots.get("start_location") or "",
        start_date=slots.get("travel_dates"),
        people=slots.get("num_travelers") or 1,
        budget=slots.get("budget_cny"),
        interests=slots.get("interests") or "目的地文化与休闲",
        transport=slots.get("transport") or "public_transit",
        needs_accommodation=slots.get("needs_accommodation"),
        city_stays=slots.get("city_stays") or [],
    )
