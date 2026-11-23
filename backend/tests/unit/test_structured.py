from unittest.mock import patch

import pytest
from langchain_core.messages import AIMessage
from travel_agent.agent.structured import diagnostic, generate
from travel_agent.planning import validate_selection
from travel_agent.providers.base import ProviderError
from travel_agent.schemas import PlanSelection, Requirements


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


def test_planning_schema_encodes_exact_day_count_without_padding():
    from pydantic import ValidationError
    from travel_agent.schemas import plan_selection_schema

    schema = plan_selection_schema(2)
    days = schema.model_json_schema()["properties"]["days"]
    assert days["minItems"] == days["maxItems"] == 2
    with pytest.raises(ValidationError):
        schema(days=[["Beijing"]], rationale="missing Shanghai day")
    result = schema(days=[["Beijing"], ["Shanghai"]], rationale="two cities")
    assert result.days == [["Beijing"], ["Shanghai"]]
    assert plan_selection_schema(2) is schema
