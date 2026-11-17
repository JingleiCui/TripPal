"""Stop only this project's launcher; does not stop Docker or other projects."""

from pathlib import Path
import json
import os
import signal
import subprocess
import time

ROOT = Path(__file__).resolve().parent
PIDFILE = ROOT / "data/run.json"
STOP_TIMEOUT_SECONDS = 15
if not PIDFILE.exists():
    raise SystemExit("未找到本项目启动记录。若从 IDE 启动，请用对应的 Stop 按钮停止。")
data = json.loads(PIDFILE.read_text())
pid = int(data["launcher"])
try:
    cwd = subprocess.check_output(["lsof", "-a", "-p", str(pid), "-d", "cwd", "-Fn"], text=True)
    command = subprocess.check_output(["ps", "-o", "command=", "-p", str(pid)], text=True)
except subprocess.CalledProcessError:
    raise SystemExit("原启动进程已退出，未停止任何其他进程。")
if f"n{ROOT}\n" not in cwd or "run_project.py" not in command:
    raise SystemExit("进程身份与本项目不匹配，未结束任何进程。")
os.kill(pid, signal.SIGTERM)
deadline = time.monotonic() + STOP_TIMEOUT_SECONDS
children = [int(value) for value in data.get("children", [])]
while time.monotonic() < deadline:
    active = []
    for child in children:
        status = subprocess.run(["ps", "-o", "stat=", "-p", str(child)], capture_output=True, text=True)
        if status.returncode == 0 and status.stdout.strip() and not status.stdout.strip().startswith("Z"):
            active.append(child)
    if not active:
        print("TripPal 已停止；Docker 数据和其他项目保留。")
        break
    time.sleep(0.2)
else:
    print("已请求停止，子服务仍在退出；请等待后再启动，未强制结束其他进程。")
