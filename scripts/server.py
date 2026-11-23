"""Container entrypoint. Server environment must supply independent credentials."""

import os
import subprocess
import sys
import time

ROLE = os.getenv("SERVICE_ROLE", "api")
if ROLE == "api":
    subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"], check=True)
    from travel_agent.config import settings
    from langgraph.checkpoint.mysql.pymysql import PyMySQLSaver

    with PyMySQLSaver.from_conn_string(settings.checkpoint_url) as saver:
        saver.setup()
    os.execv(
        sys.executable,
        [sys.executable, "-m", "uvicorn", "travel_agent.api:app", "--host", "0.0.0.0", "--port", "8808"],
    )
else:
    import httpx

    for _ in range(60):
        try:
            response = httpx.get("http://api:8808/api/v1/health", timeout=3)
            if response.status_code == 200:
                break
        except httpx.HTTPError:
            pass
        time.sleep(2)
    os.execv(
        sys.executable,
        [
            sys.executable,
            "-m",
            "celery",
            "-A",
            "travel_agent.notes.worker:celery" if ROLE == "notes" else "travel_agent.worker:celery",
            "worker",
            "-Q",
            "note_imports" if ROLE == "notes" else "celery",
            "--pool=solo",
            "--concurrency=1",
            "--loglevel=WARNING",
        ],
    )
