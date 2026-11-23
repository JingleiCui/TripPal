from unittest.mock import patch

from travel_agent.providers.base import ProviderError


def test_retry_resumes_checkpoint_without_repeating_research(account):
    import uuid

    from sqlalchemy import select
    from travel_agent.db import Event, Session, Task
    from travel_agent.worker import execute

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
        assert (
            len([e for e in events if e.kind == "tool_start" and e.data.get("name") == "fixture_places"])
            == before
        )
        assert {e.data.get("attempt") for e in events} == {1, 2}
