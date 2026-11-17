"""预订意图：只把用户 / Agent 的预订诉求结构化，绝不执行支付或下单。

这是与「真实预订/支付」之间的刻意边界——Agent 可以帮用户整理要订什么、
在哪、几人、预算，但不可越权完成交易。意图可在前端呈现为待办卡片。
"""

from .base import timestamp

ALLOWED_KINDS = ("hotel", "ticket", "transport", "dining", "other")


def build_intent(kind, name, city, date="", party=1, budget=""):
    if kind not in ALLOWED_KINDS:
        raise ValueError("kind 必须是 hotel/ticket/transport/dining/other 之一")
    if not str(name).strip():
        raise ValueError("预订对象名称不能为空")
    try:
        party_int = int(party)
    except (TypeError, ValueError):
        party_int = 1
    return {
        "kind": kind,
        "name": str(name).strip()[:120],
        "city": str(city).strip()[:40],
        "date": str(date).strip()[:40],
        "party": max(1, min(12, party_int)),
        "budget_note": str(budget).strip()[:200],
        "status": "意图已记录，未预订",
        "source": {"provider": "本地意图", "retrieved_at": timestamp()},
    }
