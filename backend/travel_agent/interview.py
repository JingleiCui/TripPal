"""对话槽位合并与确定性提问门控的纯函数。"""

MAX_INTERVIEW_TURNS = 6


def _origin_pending(details):
    return not bool(str(details.get("start_location") or "").strip())


def _slot_empty(value) -> bool:
    """A slot carries no answer: None, a blank string, or an empty list/dict. False is a real
    tri-state answer (e.g. needs_accommodation), so it is NOT empty."""
    if value is None:
        return True
    if isinstance(value, str):
        return value.strip() == ""
    if isinstance(value, list | dict):
        return len(value) == 0
    return False


def _merge_user_details(prior: dict | None, fresh: dict) -> dict:
    """Merge freshly-extracted slots over the prior turn's, so a slot answered earlier survives an
    extraction that drops it. A non-empty fresh value always wins (a genuine change or correction);
    an empty fresh value falls back to the prior non-empty one. This is what keeps the interview
    from re-asking something the user already answered (the duration/origin re-ask bug)."""
    if not prior:
        return fresh
    merged = dict(fresh)
    for key, prior_value in prior.items():
        if _slot_empty(merged.get(key)) and not _slot_empty(prior_value):
            merged[key] = prior_value
    return merged


def _has(user_details: dict, key: str) -> bool:
    return bool((user_details.get(key) or "").strip())


def _intent_vague(user_details: dict) -> bool:
    """True when the user has not said what they want to do, so we ask one targeted question.
    The schema default 'General Sightseeing' counts as vague (it means 'unspecified')."""
    interests = (user_details.get("interests") or "").strip().lower()
    return interests in ("", "unknown", "general sightseeing")


def _next_question(
    user_details: dict, user_turns: int, force_ready: bool = False, asked: set[str] | None = None
) -> str | None:
    """The next slot to ask for, or None when there's enough to plan. Pure; this is the anti-loop
    gate, decided in code, not by the LLM.

    destination and duration are always required, so we never silently plan without them. The soft
    slots (accommodation, intent, origin) are asked only while we're under the turn budget and only
    once each: `asked` holds the soft slots already put to the user, so an unanswered one (e.g. an
    ignored origin) is not nagged again. Past the budget we plan and let _finalize_details fill the
    rest, so the interview always terminates. force_ready (the user asked to start planning) skips
    the soft slots but never the hard ones.
    """
    asked = asked or set()
    if not _has(user_details, "destination"):
        return "destination"
    if not _has(user_details, "duration"):
        return "duration"
    # 日期影响每周闭馆/开放规则，与目的地、天数一样是硬条件，不能跳过。
    if not _has(user_details, "travel_dates") or user_details.get("travel_dates") == "declined":
        return "travel_dates"
    if force_ready or user_turns >= MAX_INTERVIEW_TURNS:
        return None
    if user_details.get("needs_accommodation") is None and "accommodation" not in asked:
        return "accommodation"
    if _intent_vague(user_details) and "intent" not in asked:
        return "intent"
    # Lowest priority, and naturally skipped for in-destination trips (start_location is already set
    # to the destination) or once the user has stated or declined an origin.
    if _origin_pending(user_details) and "origin" not in asked:
        return "origin"
    return None
