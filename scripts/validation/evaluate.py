"""Edit MODE here, then Run. CLI override is optional. Evaluation DB is isolated."""

from pathlib import Path
import os
import sys
import json
import hashlib
import time
import argparse

MODE = "regression"  # regression / local-model-smoke / cloud-heldout
LOCAL_MODEL = "qwen3.5:9b"
ROOT = Path(__file__).resolve().parents[2]
os.environ["TRAVEL_DATABASE_URL"] = (
    "mysql+pymysql://travel:travel_local_only@127.0.0.1:13316/travel_agent_eval?charset=utf8mb4"
)
os.environ["TRAVEL_CHECKPOINT_URL"] = "mysql://travel:travel_local_only@127.0.0.1:13316/travel_agent_eval"
sys.path.insert(0, str(ROOT / "backend"))
from travel_agent.config import settings
from travel_agent.db import Base, engine, Session, User, Trip, Task, Event, uid
from travel_agent.worker import execute
from langgraph.checkpoint.mysql.pymysql import PyMySQLSaver
from sqlalchemy import select


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", default=MODE, choices=["regression", "local-model-smoke", "cloud-heldout"])
    mode = parser.parse_args().mode
    model_run = mode != "regression"
    if mode == "local-model-smoke":
        settings.model_provider = "ollama"
        settings.model_enabled = True
        settings.model_api_key = "ollama"
        settings.model_base_url = os.getenv("TRIPAL_OLLAMA_URL", "http://127.0.0.1:11434").rstrip("/") + "/v1"
        settings.model_name = LOCAL_MODEL
        settings.model_timeout = 120
        settings.model_reasoning_effort = "none"
    if mode == "cloud-heldout" and not (settings.model_enabled and settings.model_api_key):
        raise SystemExit("云端模型未配置；未执行保留集，也没有生成替代分数。")
    Base.metadata.create_all(engine)
    with PyMySQLSaver.from_conn_string(settings.checkpoint_url) as saver:
        saver.setup()
    raw = (ROOT / "eval/cases.json").read_bytes()
    cases = json.loads(raw)
    if mode == "local-model-smoke":
        cases = cases[:1]
    if mode == "cloud-heldout":
        cases = [c for c in cases if c["split"] == "heldout"]
    run_id = uid()
    with Session.begin() as db:
        user = User(name="evaluation-" + run_id, password="NO_LOGIN_EVALUATION_ACCOUNT")
        db.add(user)
        db.flush()
        owner = user.id
    rows = []
    strategies = ["pure", "single", "multi"] if model_run else ["multi"]
    for case in cases:
        for strategy in strategies:
            with Session.begin() as db:
                trip = Trip(
                    owner=owner,
                    title="评测 " + case["id"],
                    version=1 if case["family"] == "version_conflict" else 0,
                )
                db.add(trip)
                db.flush()
                payload = {
                    "requirements": case["requirements"],
                    "message": case["message"],
                    "fixture": True,
                    "fixture_model": model_run,
                    "strategy": strategy,
                    "base_version": 0,
                    "request_key": uid(),
                }
                task = Task(
                    owner=owner,
                    trip_id=trip.id,
                    request_key=payload["request_key"],
                    request_hash=hashlib.sha256(json.dumps(payload).encode()).hexdigest(),
                    payload=payload,
                )
                db.add(task)
                db.flush()
                ident = task.id
            started = time.perf_counter()
            execute(ident)
            elapsed = time.perf_counter() - started
            with Session() as db:
                task = db.get(Task, ident)
                trip = db.get(Trip, task.trip_id)
                events = db.scalars(select(Event).where(Event.task_id == ident).order_by(Event.id)).all()
                model_events = [e for e in events if e.kind == "model_end"]
                row = {
                    "case": case["id"],
                    "split": case["split"],
                    "strategy": strategy,
                    "task_id": ident,
                    "status": task.status,
                    "expected_status": case["expected_status"],
                    "status_matches": task.status == case["expected_status"],
                    "elapsed_seconds": round(elapsed, 3),
                    "model_calls": sum(e.kind == "model_start" for e in events),
                    "tool_calls": sum(e.kind == "tool_start" for e in events),
                    "usage": [e.data.get("usage", {}) for e in model_events],
                    "error": task.result.get("error"),
                    "plan": trip.plan,
                    "trace": [{"kind": e.kind, "data": e.data} for e in events],
                }
            rows.append(row)
            print(case["id"], strategy, row["status"], row["elapsed_seconds"], flush=True)
    report = {
        "run_id": run_id,
        "mode": mode,
        "dataset_sha256": hashlib.sha256(raw).hexdigest(),
        "model": settings.model_name if model_run else None,
        "synthetic_provider_data": True,
        "semantic_quality_evaluated": False,
        "review_note": "状态匹配是工程指标，不是行程质量；纯模型文本不能按同一结构计总分。语义、引用支持和用户体验仍需逐例评阅。",
        "rows": rows,
        "status_matches": sum(r["status_matches"] for r in rows),
        "total": len(rows),
    }
    folder = ROOT / "reports"
    folder.mkdir(exist_ok=True)
    target = folder / (mode + "-" + run_id + ".json")
    target.write_text(json.dumps(report, ensure_ascii=False, indent=2))
    print("report:", target, "status_matches:", report["status_matches"], "/", len(rows), flush=True)
    if report["status_matches"] != len(rows):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
