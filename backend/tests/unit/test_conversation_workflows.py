from travel_agent.conversation import extract, gate, parsed_travelers, to_requirements
from travel_agent.interview import _merge_user_details, _next_question


def test_explicit_headcount_is_extracted():
    assert parsed_travelers("两个人，去杭州，4天") == 2
    assert parsed_travelers("一共5人去杭州") == 5
    assert parsed_travelers("2位成人1位儿童") == 3
    assert parsed_travelers("两大一小") == 3
    assert parsed_travelers("4天预算2000") is None
    slots, _, _, _ = extract("两个人，去杭州，4天", {}, fixture=True)
    assert slots["num_travelers"] == 2


def test_travel_date_is_required_even_when_user_tries_to_skip():
    base = {"destination": "北京", "duration": "2 days", "travel_dates": ""}
    slots, _, _, _ = extract("跳过", base, last_question="travel_dates", fixture=True)
    assert not slots.get("travel_dates")
    assert gate(slots, 4, ["travel_dates"], "跳过")[0] == "travel_dates"
    assert to_requirements({**slots, "destination": "北京", "duration": "2 days"}).start_date is None


def test_merge_keeps_false_and_known_slots():
    assert _merge_user_details(
        {"destination": "北京", "needs_accommodation": False},
        {"destination": "", "needs_accommodation": None},
    ) == {"destination": "北京", "needs_accommodation": False}
    assert _next_question({"destination": "北京", "duration": "2 days"}, 6) == "travel_dates"
    assert (
        _next_question(
            {"destination": "北京", "duration": "2 days", "travel_dates": "2027-05-01"}, 6
        )
        is None
    )


def test_chinese_single_question_gate_without_guessing():
    slots, _, _, _ = extract("想旅游", {}, fixture=True)
    assert gate(slots, 1, [], "想旅游")[0] == "destination"
    slots, _, _, _ = extract("去北京", slots, fixture=True)
    assert gate(slots, 2, ["destination"], "去北京")[0] == "duration"
    slots, _, _, _ = extract("三天", slots, fixture=True)
    assert slots["destination"] == "北京"
    assert gate(slots, 3, [], "直接规划")[0] == "travel_dates"
    slots, _, _, _ = extract("跳过", slots, last_question="travel_dates", fixture=True)
    assert gate(slots, 4, ["travel_dates"], "跳过")[0] == "travel_dates"
    slots, _, _, _ = extract("2027-05-01，直接规划", slots, last_question="travel_dates", fixture=True)
    assert slots["travel_dates"] == "2027-05-01"
    assert gate(slots, 5, ["travel_dates"], "直接规划")[0] is None
