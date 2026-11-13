import pytest
from unittest.mock import patch
from langchain_core.messages import AIMessage
from travel_agent.agent.structured import generate, diagnostic
from travel_agent.schemas import PlanSelection, Requirements
from travel_agent.planning import validate_selection
from travel_agent.providers.base import ProviderError


def response(content="", parsed=None, error=None, finish="stop"):
    return {
        "raw": AIMessage(content=content, response_metadata={"finish_reason": finish}),
        "parsed": parsed,
        "parsing_error": error,
    }


@pytest.mark.parametrize(
    "content,finish,reason",
    [("普通说明", "stop", "missing_tool_call"), ("", "stop", "empty_output"), ("{", "length", "truncated")],
)
def test_diagnosis(content, finish, reason):
    assert diagnostic(response(content, finish=finish), "function_calling")["reason"] == reason


@pytest.mark.parametrize(
    "bad",
    [
        response("not json", error=ValueError("json")),
        response("{}", parsed={}),
        response("{}", parsed={"days": "bad", "rationale": "x"}),
        response("{", finish="length"),
    ],
)
def test_correct_once_and_validate(bad):
    good = response(parsed=PlanSelection(days=[["A"]], rationale="x"))
    with patch("travel_agent.agent.harness.model") as factory:
        factory.return_value.with_structured_output.return_value.invoke.side_effect = [bad, good]
        result = generate(PlanSelection, [], "test")
        assert result.days == [["A"]]
        assert factory.return_value.with_structured_output.return_value.invoke.call_count == 2


def test_no_unbounded_retry_or_defaults():
    with patch("travel_agent.agent.harness.model") as factory:
        factory.return_value.with_structured_output.return_value.invoke.return_value = response(
            "ordinary text"
        )
        with pytest.raises(ProviderError) as exc:
            generate(PlanSelection, [], "test")
        assert exc.value.code == "schema"
        assert factory.return_value.with_structured_output.return_value.invoke.call_count == 2


def test_business_errors_use_same_two_attempts():
    req = Requirements(days=1)
    valid = PlanSelection(days=[["A"]], rationale="valid")
    with patch("travel_agent.agent.harness.model") as factory:
        factory.return_value.with_structured_output.return_value.invoke.side_effect = [
            response(parsed=PlanSelection(days=[["X"]], rationale="bad")),
            response(parsed=valid),
        ]
        result = generate(
            PlanSelection,
            [],
            "test",
            validator=lambda x: validate_selection(x.days, [{"id": "A", "city": "北京"}], req),
        )
        assert result == valid


def test_diagnostics_never_log_raw_reasoning_or_keys():
    out = diagnostic(response("secret token, hidden thoughts", error=ValueError("secret")), "json_schema")
    assert "secret" not in str(out) and "thoughts" not in str(out)


def test_retry_resumes_checkpoint_without_repeating_research(account):
    import uuid
    from sqlalchemy import select
    from travel_agent.worker import execute
    from travel_agent.db import Session, Event, Task

    created = account.post(
        "/api/v1/tasks",
        json={
            "request_key": uuid.uuid4().hex,
            "message": "test",
            "fixture": True,
            "requirements": {"city": "北京", "days": 1, "origin": "北京站", "start_date": "2027-05-01"},
        },
    ).json()
    with patch(
        "travel_agent.agent.graph.build_plan", side_effect=ProviderError("schema", "injected failure")
    ):
        execute(created["id"])
    with Session() as db:
        assert db.get(Task, created["id"]).status == "failed"
        before = len(
            db.scalars(select(Event).where(Event.task_id == created["id"], Event.kind == "tool_start")).all()
        )
    assert account.post("/api/v1/tasks/" + created["id"] + "/retry").status_code == 202
    execute(created["id"])
    with Session() as db:
        assert db.get(Task, created["id"]).status == "completed"
        events = db.scalars(select(Event).where(Event.task_id == created["id"])).all()
        assert len([e for e in events if e.kind == "tool_start" and e.data.get("name") == "fixture_places"]) == before
        assert {e.data.get("attempt") for e in events} == {1, 2}
