"""Real local model + actual provider pipeline, separate evaluation DB; no canned answers."""

from pathlib import Path
import os
import sys
import json
import time

ROOT = Path(__file__).resolve().parents[1]
MODEL = "qwen3.5:9b"
REPETITIONS = 3
SCENARIOS = ["single_city", "multi_city", "locked_edit"]
REPORT_NAME = "schema-model-verification.json"
os.environ["TRAVEL_DATABASE_URL"] = (
    "mysql+pymysql://travel:travel_local_only@127.0.0.1:13316/travel_agent_eval?charset=utf8mb4"
)
os.environ["TRAVEL_CHECKPOINT_URL"] = "mysql://travel:travel_local_only@127.0.0.1:13316/travel_agent_eval"
sys.path.insert(0, str(ROOT / "backend"))
from travel_agent.db import Base, engine, Session, User, Trip, Task, Event, uid
from travel_agent.config import settings
from travel_agent.worker import execute
from travel_agent.providers import amap
from travel_agent.schemas import Requirements
from travel_agent.planning import build_plan
from travel_agent.security import password_hash
from sqlalchemy import select
from langgraph.checkpoint.mysql.pymysql import PyMySQLSaver


def main():
    assert settings.model_name == MODEL, "Do not silently substitute model"
    Base.metadata.create_all(engine)
    with PyMySQLSaver.from_conn_string(settings.checkpoint_url) as saver:
        saver.setup()
    with Session.begin() as db:
        u = User(name="schema-eval-" + uid(), password=password_hash(uid()))
        db.add(u)
        db.flush()
        owner = u.id
    locked = amap.search_places("北京", "颐和园")[0]
    rows = []
    for scenario in SCENARIOS:
        for repetition in range(REPETITIONS):
            req = Requirements(
                city="北京",
                days=2 if scenario == "multi_city" else 1,
                origin="北京站",
                start_date="2026-12-01",
                needs_accommodation=False,
                city_stays=[{"city": "北京", "days": 1}, {"city": "上海", "days": 1}]
                if scenario == "multi_city"
                else [],
                locked_ids=[locked["id"]] if scenario == "locked_edit" else [],
            )
            old = {}
            if scenario == "locked_edit":
                origin = amap.resolve_origin(req.city, req.origin)
                old = build_plan(
                    [[locked["id"]]],
                    [locked],
                    req,
                    lambda a, b, mode, city: amap.route_between(a, b, mode, city),
                    origin=origin,
                )
            with Session.begin() as db:
                trip = Trip(owner=owner, title="真实模型验证 " + scenario, version=1 if old else 0, plan=old)
                db.add(trip)
                db.flush()
                task = Task(
                    owner=owner,
                    trip_id=trip.id,
                    request_key=uid(),
                    request_hash="eval",
                    payload={
                        "requirements": req.model_dump(mode="json"),
                        "message": "每天仅安排两个景点，保留已锁定地点，不需要住宿；只用有来源的地点。",
                        "fixture": False,
                        "strategy": "multi",
                        "base_version": trip.version,
                    },
                )
                db.add(task)
                db.flush()
                ident = task.id
            start = time.perf_counter()
            execute(ident)
            with Session() as db:
                t = db.get(Task, ident)
                events = db.scalars(select(Event).where(Event.task_id == ident).order_by(Event.id)).all()
                row = {
                    "scenario": scenario,
                    "repetition": repetition + 1,
                    "task_id": ident,
                    "status": t.status,
                    "result": t.result,
                    "seconds": round(time.perf_counter() - start, 3),
                    "models": sum(e.kind == "model_start" for e in events),
                    "tools": sum(e.kind == "tool_start" for e in events),
                    "diagnostics": [e.data for e in events if e.kind in ["schema_validation", "error"]],
                }
            rows.append(row)
            (ROOT / "reports" / REPORT_NAME).write_text(
                json.dumps({"model": MODEL, "fixture": False, "rows": rows}, ensure_ascii=False, indent=2)
            )
            print(scenario, repetition + 1, row["status"], row["seconds"], flush=True)
    print("Report: reports/schema-model-verification.json", flush=True)


if __name__ == "__main__":
    main()
