"""PyCharm: choose .venv/bin/python, then Run this file. Ctrl+C stops owned processes."""

from pathlib import Path
import os
import signal
import socket
import subprocess
import sys
import time
import json
import urllib.request

# 用户常用配置：无需命令行参数。
START_CONTAINERS = True
BUILD_FRONTEND = True
START_WORKER = True
PORT = 8808
ROOT = Path(__file__).resolve().parent
PYTHON = ROOT / ".venv/bin/python"


def run(*args):
    subprocess.run(args, cwd=ROOT, check=True)


def main():
    if not PYTHON.exists():
        raise SystemExit("独立环境尚未安装，请先用 Python 3.11 运行 scripts/bootstrap.py")
    os.chdir(ROOT)
    probe = socket.socket()
    occupied = probe.connect_ex(("127.0.0.1", PORT)) == 0
    probe.close()
    if occupied:
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{PORT}/api/v1/health", timeout=2) as response:
                data = json.load(response)
            if data.get("application") == "travel_agent":
                print(
                    f"travel_agent 已经运行：http://127.0.0.1:{PORT}。若刚修改密钥，先运行 stop_project.py，再重新运行本文件。"
                )
                return
        except Exception:
            pass
        raise SystemExit(f"端口 {PORT} 被其他程序占用。请修改配置或自行检查；本程序不会结束其他进程。")
    if START_CONTAINERS:
        run("docker", "info", "--format", "{{.ServerVersion}}")
        run("docker", "compose", "up", "-d")
    env = {
        **os.environ,
        "PYTHONPATH": str(ROOT / "backend"),
        "TOKENIZERS_PARALLELISM": "false",
        "OMP_NUM_THREADS": "2",
        "TRAVEL_PORT": str(PORT),
    }
    # Wait only for the database used by migrations; failures remain visible.
    for attempt in range(40):
        result = subprocess.run(
            [str(PYTHON), "-c", "from travel_agent.db import engine; c=engine.connect(); c.close()"],
            env=env,
            capture_output=True,
            cwd=ROOT,
        )
        if result.returncode == 0:
            break
        time.sleep(2)
    else:
        raise SystemExit("MySQL 未就绪，请检查 docker compose logs mysql")
    subprocess.run([str(PYTHON), "-m", "alembic", "upgrade", "head"], cwd=ROOT, env=env, check=True)
    subprocess.run(
        [
            str(PYTHON),
            "-c",
            "from travel_agent.config import settings; from langgraph.checkpoint.mysql.pymysql import PyMySQLSaver;\nwith PyMySQLSaver.from_conn_string(settings.checkpoint_url) as saver: saver.setup()",
        ],
        cwd=ROOT,
        env=env,
        check=True,
    )
    if BUILD_FRONTEND:
        if not (ROOT / "frontend/node_modules").exists():
            run("npm", "ci", "--prefix", "frontend")
        built = ROOT / "frontend/dist/index.html"
        modified = max(p.stat().st_mtime for p in (ROOT / "frontend/src").rglob("*") if p.is_file())
        if not built.exists() or modified > built.stat().st_mtime:
            run("npm", "run", "build", "--prefix", "frontend")
    children = []
    pidfile = ROOT / "data/run.json"
    pidfile.parent.mkdir(exist_ok=True)

    def stop(*_):
        for process in reversed(children):
            process.terminate()
        for process in children:
            try:
                process.wait(timeout=8)
            except subprocess.TimeoutExpired:
                process.kill()
        sys.exit(0)

    signal.signal(signal.SIGINT, stop)
    signal.signal(signal.SIGTERM, stop)
    try:
        if START_WORKER:
            children.append(
                subprocess.Popen(
                    [
                        str(PYTHON),
                        "-m",
                        "celery",
                        "-A",
                        "travel_agent.worker:celery",
                        "worker",
                        "--pool=solo",
                        "--concurrency=1",
                        "--loglevel=WARNING",
                        "--hostname=travel-agent@%h",
                        "--without-gossip",
                        "--without-mingle",
                    ],
                    env=env,
                    cwd=ROOT,
                )
            )
        children.append(
            subprocess.Popen(
                [
                    str(PYTHON),
                    "-m",
                    "uvicorn",
                    "travel_agent.api:app",
                    "--host",
                    "127.0.0.1",
                    "--port",
                    str(PORT),
                ],
                env=env,
                cwd=ROOT,
            )
        )
        pidfile.write_text(
            json.dumps({"launcher": os.getpid(), "children": [p.pid for p in children], "root": str(ROOT)})
        )
        print(f"\ntravel_agent：http://127.0.0.1:{PORT}\n接口文档：http://127.0.0.1:{PORT}/docs\n")
        while all(p.poll() is None for p in children):
            time.sleep(1)
        raise RuntimeError("某个子服务已退出，请检查上面的错误信息")
    finally:
        for child in children:
            if child.poll() is None:
                child.terminate()
        if pidfile.exists():
            try:
                if json.loads(pidfile.read_text()).get("launcher") == os.getpid():
                    pidfile.unlink()
            except (ValueError, OSError):
                pass


if __name__ == "__main__":
    try:
        main()
    except subprocess.CalledProcessError as exc:
        raise SystemExit(f"启动步骤失败：{exc.cmd[0]}。请查看上方输出；未结束其他项目服务。")
