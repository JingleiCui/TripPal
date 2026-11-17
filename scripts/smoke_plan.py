"""端到端规划冒烟：跑一次真实（非 fixture）任务，验证完整 LangGraph 链路。

在独立测试库执行，不触碰业务数据；需要本地 MySQL/Redis/ES 与已就绪的模型供应商。
    .venv/bin/python scripts/smoke_plan.py
    TRAVEL_ACTIVE_MODEL_PROFILE=openrouter_free .venv/bin/python scripts/smoke_plan.py

退出码 0 = 任务 completed；1 = 失败/待补凭证；结果如实打印，不把失败写成通过。
"""

from __future__ import annotations

import json
import os
import sys
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

# 与 backend/tests/conftest.py 一致的隔离配置，避免污染业务库。
os.environ.setdefault(
    "TRAVEL_DATABASE_URL",
    "mysql+pymysql://travel:travel_local_only@127.0.0.1:13316/travel_agent_test?charset=utf8mb4",
)
os.environ.setdefault("TRAVEL_CHECKPOINT_URL", "mysql://travel:travel_local_only@127.0.0.1:13316/travel_agent_test")
os.environ.setdefault("TRAVEL_ELASTIC_INDEX", "travel-agent-test-chunks")
os.environ.setdefault("TRAVEL_SEMANTIC_CACHE_INDEX", "travel-agent-test-research-cache")
os.environ.setdefault("TRAVEL_DATA_DIR", "/tmp/travel-agent-test-uploads")
os.environ.setdefault("TRAVEL_REDIS_URL", "redis://127.0.0.1:16389/10")
os.environ.setdefault("TRAVEL_BROKER_URL", "redis://127.0.0.1:16389/11")


def main():
    import redis
    from fastapi.testclient import TestClient
    from langgraph.checkpoint.mysql.pymysql import PyMySQLSaver
    from travel_agent.api import app
    from travel_agent.config import settings
    from travel_agent.db import Base, engine
    from travel_agent.models.registry import status
    from travel_agent.worker import execute

    Base.metadata.create_all(engine)
    with PyMySQLSaver.from_conn_string(settings.checkpoint_url) as saver:
        saver.setup()

    chat = status()["slots"]["chat"]
    print(f"模型供应商: {chat.get('provider')} / {chat.get('model')} / {chat.get('status')}")
    if not settings.amap_key:
        print("高德 Key 未配置，真实规划会停在 awaiting_credentials。")

    client = TestClient(app)
    redis.Redis.from_url(settings.redis_url).flushdb()  # 仅测试库专用 db 10
    registered = client.post(
        "/api/v1/auth/register",
        json={"name": "smoke-" + uuid.uuid4().hex[:10], "password": "smoke-password-123"},
    )
    if registered.status_code != 200:
        print("注册失败：", registered.status_code, registered.text[:300])
        return 1
    client.headers["X-CSRF-Token"] = registered.json()["csrf"]

    body = {
        "request_key": uuid.uuid4().hex,
        "message": "请安排北京一日轻松行程",
        "fixture": False,
        "requirements": {
            "city": "北京",
            "days": 1,
            "origin": "北京站",
            "start_date": "2027-05-01",
        },
    }
    created = client.post("/api/v1/tasks", json=body)
    if created.status_code != 202:
        print("创建任务失败：", created.status_code, created.text[:300])
        return 1
    task_id = created.json()["id"]
    print(f"任务已创建: {task_id}（真实模式，开始执行…）")
    requirements = body["requirements"]

    # LangGraph 的 interrupt 会停在人工确认点；这里自动用同一份条件 resume，最多 3 轮。
    for round_no in range(1, 4):
        try:
            execute(task_id)
        except Exception as exc:
            print(f"  第 {round_no} 轮执行抛出异常: {type(exc).__name__}: {str(exc)[:300]}")
        result = client.get(f"/api/v1/tasks/{task_id}").json()
        state = result.get("status")
        print(f"  第 {round_no} 轮状态: {state}")
        if state != "waiting_input":
            break
        resumed = client.post(
            f"/api/v1/tasks/{task_id}/resume", json={"requirements": requirements}
        )
        if resumed.status_code != 202:
            print("  自动推进失败：", resumed.status_code, resumed.text[:200])
            break

    summary = {
        "status": result.get("status"),
        "error": result.get("error"),
        "trip_id": result.get("trip_id"),
        "result": str(result.get("result", ""))[:300],
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    if result.get("status") == "completed":
        trip = client.get(f"/api/v1/trips/{result['trip_id']}").json()
        print(f"行程版本: {trip.get('version')} / 标题: {str(trip.get('plan', {}).get('title', ''))[:60]}")
        return 0
    if result.get("status") == "waiting_input":
        print("结论：链路已执行到人工确认中断点（interrupt），模型调用已发生；未走到 completed。")
        return 0
    print("结论：真实规划未通过（失败或缺少凭证）。")
    return 1


if __name__ == "__main__":
    sys.exit(main())
