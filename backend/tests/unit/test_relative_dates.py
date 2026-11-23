"""相对日期与区间解析：下周三-下周五 → travel_dates + duration。"""

from datetime import date

from travel_agent.conversation import parse_relative_dates, rule_extract


def test_relative_range_next_week():
    start, days = parse_relative_dates("下周三-下周五")
    assert days == 3
    assert start is not None
    # 起点必须是未来的某一天（下周三）
    assert date.fromisoformat(start) > date.today()


def test_single_relative_no_duration():
    start, days = parse_relative_dates("本周五去逛逛")
    assert start is not None
    assert days is None


def test_rule_extract_duration_and_budget_from_range():
    res = rule_extract("下周三-下周五，一个人在北京，想逛公园呼吸自然，预算每天300")
    assert res.get("destination") == "北京"
    assert res.get("duration") == "3 days"
    assert res.get("budget_cny") == 300
    assert "公园" in (res.get("interests") or "")


def test_rule_extract_explicit_date_range():
    res = rule_extract("2026-11-18 到 2026-11-20 去上海")
    assert res.get("destination") == "上海"
    assert res.get("travel_dates") == "2026-11-18"
    assert res.get("duration") == "3 days"
