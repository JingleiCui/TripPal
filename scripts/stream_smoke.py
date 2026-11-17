"""Real local provider streaming check; independent evaluation DB, never cloud billing.

This checks transport/event persistence, not itinerary quality or Gemini compatibility.
Edit the small configuration block below in the IDE.
"""

from pathlib import Path
import json
import os
import sys
import time
from datetime import timedelta

ROOT = Path(__file__).resolve().parents[1]
MODEL = "qwen3.5:9b"
BASE_URL = "http://127.0.0.1:11434/v1"
EVAL_DATABASE = "mysql+pymysql://travel:travel_local_only@127.0.0.1:13316/travel_agent_eval?charset=utf8mb4"
os.environ["TRAVEL_DATABASE_URL"] = EVAL_DATABASE
sys.path.insert(0, str(ROOT / "backend"))

from sqlalchemy import select
from langchain_core.messages import SystemMessage, HumanMessage
from travel_agent.db import Session, Base, engine, User, Trip, Task, Event, uid, now
from travel_agent.config import settings
from travel_agent.agent.harness import Harness


def main():
    settings.model_provider, settings.model_base_url = "openai", BASE_URL
    settings.model_api_key, settings.model_enabled, settings.model_name = "ollama", True, MODEL
    settings.model_reasoning_effort = "none"
    Base.metadata.create_all(engine)
    with Session.begin() as db:
        user = User(name="stream-eval-" + uid(), password="NO_LOGIN_EVALUATION_ACCOUNT")
        db.add(user)
        db.flush()
        trip = Trip(owner=user.id, title="合成流式验证")
        db.add(trip)
        db.flush()
        task = Task(
            owner=user.id,
            trip_id=trip.id,
            request_key=uid(),
            request_hash="smoke",
            payload={},
            status="running",
            lease=uid(),
            lease_until=now() + timedelta(minutes=5),
        )
        db.add(task)
        db.flush()
        ident, lease = task.id, task.lease
    harness = Harness(ident, lease)
    rows = []
    for label in ["A", "B"]:
        started = time.perf_counter()
        text = harness.stream_reply(
            [
                SystemMessage(
                    content="只用中文，一句话回答，不超过40字。明确这是合成行程建议，不代表已预订。"
                ),
                HumanMessage(content=f"方案{label}：上午博物馆、下午公园。请提醒用户核实开放时间。"),
            ],
            label,
        )
        with Session() as db:
            chunks = [
                e.data["delta"]
                for e in db.scalars(
                    select(Event)
                    .where(Event.task_id == ident, Event.kind == "assistant_token")
                    .order_by(Event.id)
                )
                if e.data.get("variant") == label
            ]
        assert "".join(chunks) == text and len(chunks) > 1
        rows.append(
            {
                "variant": label,
                "text": text,
                "chunks": len(chunks),
                "seconds": round(time.perf_counter() - started, 3),
            }
        )
    with Session.begin() as db:
        task = db.get(Task, ident)
        task.status, task.lease_until, task.lease = "completed", None, None
        task.result = {"kind": "stream_transport_smoke_only"}
    report = {
        "model": MODEL,
        "task_id": ident,
        "rows": rows,
        "scope": "real local model stream; not planning quality",
    }
    target = ROOT / "reports/stream-smoke.json"
    target.write_text(json.dumps(report, ensure_ascii=False, indent=2))
    print(json.dumps(report, ensure_ascii=False))


if __name__ == "__main__":
    main()
