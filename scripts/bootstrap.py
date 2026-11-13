"""Run once with Python 3.11; installs only this project's dependencies."""

from pathlib import Path
import subprocess
import sys
import venv

ROOT = Path(__file__).resolve().parents[1]
if sys.version_info[:2] != (3, 11):
    raise SystemExit("请用 Python 3.11 运行；不要使用系统默认 Python 3.15。")
venv.EnvBuilder(with_pip=True).create(ROOT / ".venv")
python = ROOT / ".venv/bin/python"
lock = ROOT / "requirements.lock.txt"
subprocess.run(
    [str(python), "-m", "pip", "install", "-r", str(lock if lock.exists() else ROOT / "requirements.txt")],
    check=True,
)
subprocess.run([str(python), "-m", "pip", "install", "-e", str(ROOT), "--no-deps"], check=True)
subprocess.run(["npm", "ci", "--prefix", str(ROOT / "frontend")], check=True)
subprocess.run(["npm", "ci", "--prefix", str(ROOT / "integrations")], check=True)
local = ROOT / "config.local.json"
if not local.exists():
    local.write_text((ROOT / "config.example.json").read_text())
    local.chmod(0o600)
print("独立环境已准备好。在 PyCharm 选择 .venv/bin/python，运行 run_project.py。")
