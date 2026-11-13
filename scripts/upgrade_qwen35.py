"""Run once from PyCharm or in the background; no Codex/LLM polling is needed.

Downloads resume across restarts. Only local model probes are made. Old models are
deleted only after all readiness checks, streaming and service restart succeed.
"""

from pathlib import Path
from datetime import datetime, timezone
import ast
import fcntl
import json
import os
import pprint
import shutil
import socket
import subprocess
import sys
import time
import urllib.request

# ==================== 可直接修改的配置 ====================
ROOT = Path(__file__).resolve().parents[1]
MEDICAL_ROOT = Path("/Users/cuijinglei/PycharmProjects/medicalProject")
MODEL = "qwen3.5:9b"
OLD_MODELS = ("qwen3:4b", "qwen3:4b-instruct", "qwen3:8b")
CONTEXT_TOKENS = 8192
DOWNLOAD_ATTEMPTS = 120
DOWNLOAD_RETRY_SECONDS = 30
MODEL_TIMEOUT_SECONDS = 120
RESTART_TRAVEL_SERVICE = True
DELETE_OLD_MODELS = True
RUN_PLANNING_SMOKE = True  # 使用独立评测库；合成资料 + 真实本地模型
STATE_DIR = ROOT / "data/upgrade-qwen35"
PYTHON = ROOT / ".venv/bin/python"
STATUS_PATH = STATE_DIR / "status.json"
LOG_PATH = STATE_DIR / "upgrade.log"


def status(stage, **extra):
    data = {"stage": stage, "time_utc": datetime.now(timezone.utc).isoformat(), **extra}
    tmp = STATUS_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2))
    tmp.replace(STATUS_PATH)
    print(data["time_utc"], stage, flush=True)


def run(*args, timeout=None, check=True, env=None):
    result = subprocess.run(
        [str(arg) for arg in args], cwd=ROOT, timeout=timeout, env=env,
        stdout=sys.stdout, stderr=sys.stderr,
    )
    if check and result.returncode:
        raise RuntimeError(f"Step failed: {Path(str(args[0])).name}, exit={result.returncode}")
    return result.returncode


def local_json(path, body=None, timeout=10):
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    req = urllib.request.Request(
        "http://127.0.0.1:11434" + path,
        data=json.dumps(body).encode() if body is not None else None,
        headers={"Content-Type": "application/json"},
    )
    with opener.open(req, timeout=timeout) as response:
        return json.load(response)


def backup_file(source, name, folder):
    target = folder / name
    shutil.copy2(source, target)
    os.chmod(target, 0o600)
    return target


def update_medical():
    path = MEDICAL_ROOT / "llm_config.py"
    source = path.read_text()
    tree = ast.parse(source)
    lines = source.splitlines(keepends=True)
    replacements = []
    for node in tree.body:
        if not isinstance(node, ast.Assign) or not isinstance(node.targets[0], ast.Name):
            continue
        name = node.targets[0].id
        if name == "ACTIVE_MODEL":
            text = 'ACTIVE_MODEL = "ollama_qwen35_9b"  # gemini / ollama_qwen35_9b\n'
        elif name == "MODEL_CONFIGS":
            if not isinstance(node.value, ast.Dict):
                raise ValueError("MODEL_CONFIGS must be a literal dictionary")
            entries = []
            for key, value in zip(node.value.keys, node.value.values):
                profile = ast.literal_eval(key)
                if not profile.startswith("ollama_qwen"):
                    # Preserve the user's existing Gemini key/source without logging it.
                    entries.append(f"{profile!r}: {ast.get_source_segment(source, value)}")
            profile = {
                "provider": "ollama", "model": MODEL,
                "base_url": "http://localhost:11434", "temperature": 0.2,
                "reasoning": False, "num_ctx": CONTEXT_TOKENS,
            }
            entries.append("'ollama_qwen35_9b': " + pprint.pformat(profile, sort_dicts=False))
            text = "MODEL_CONFIGS = {\n" + ",\n".join(entries) + "\n}\n"
        else:
            continue
        replacements.append((node.lineno - 1, node.end_lineno, text))
    if len(replacements) != 2:
        raise ValueError("Expected ACTIVE_MODEL and MODEL_CONFIGS assignments")
    for start, end, text in sorted(replacements, reverse=True):
        lines[start:end] = [text]
    source = "".join(lines)
    if 'num_ctx=config["num_ctx"]' not in source:
        marker = 'reasoning=config["reasoning"],'
        if source.count(marker) != 1:
            raise ValueError("Cannot safely add the native Ollama context setting")
        source = source.replace(marker, marker + '\n            num_ctx=config["num_ctx"],')
    compile(source, str(path), "exec")
    path.write_text(source)
    os.chmod(path, 0o600)


def port_open():
    with socket.socket() as client:
        client.settimeout(1)
        return client.connect_ex(("127.0.0.1", 8808)) == 0


def restart_services(env):
    if port_open():
        # The project stop script checks process identity before terminating anything.
        run(PYTHON, ROOT / "stop_project.py", timeout=40, env=env)
        deadline = time.monotonic() + 30
        while port_open() and time.monotonic() < deadline:
            time.sleep(1)
        if port_open():
            raise RuntimeError("Port 8808 is still occupied; no unrelated process was killed")
    with (STATE_DIR / "service.log").open("ab", buffering=0) as log:
        process = subprocess.Popen(
            [str(PYTHON), "-u", str(ROOT / "run_project.py")], cwd=ROOT, env=env,
            stdin=subprocess.DEVNULL, stdout=log, stderr=log, start_new_session=True,
        )
    (STATE_DIR / "service.pid").write_text(str(process.pid))
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    deadline = time.monotonic() + 120
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError("Project launcher exited; see service.log")
        try:
            with opener.open("http://127.0.0.1:8808/api/v1/health", timeout=5) as response:
                health = json.load(response)
            if (
                health.get("application") == "travel_agent"
                and health.get("providers", {}).get("model") == "configured_not_verified"
                and all(v == "ready" for v in health.get("services", {}).values())
            ):
                break
        except Exception:
            pass
        time.sleep(2)
    else:
        raise RuntimeError("Restarted API did not become healthy")
    result = subprocess.run(
        [str(PYTHON), "-m", "celery", "-A", "travel_agent.worker:celery",
         "inspect", "ping", "--timeout=10", "--json"],
        cwd=ROOT, env={**env, "PYTHONPATH": str(ROOT / "backend")},
        capture_output=True, text=True, timeout=25,
    )
    # Save no environment values or credentials, only this worker's ping response.
    (STATE_DIR / "worker-ping.log").write_text(result.stdout)
    replies = json.loads(result.stdout) if result.returncode == 0 else {}
    if not any(name.startswith("travel-agent@") and value.get("ok") == "pong"
               for name, value in replies.items()):
        raise RuntimeError("Worker did not answer ping after restart")


def main():
    STATE_DIR.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(STATE_DIR, 0o700)
    with (STATE_DIR / "upgrade.lock").open("w") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            print("已有升级进程运行，不重复启动。", flush=True)
            return
        (STATE_DIR / "upgrade.pid").write_text(str(os.getpid()))
        env = dict(os.environ)
        # A PyCharm environment override must not silently select Gemini again.
        for name in ("MODEL_PROVIDER", "MODEL_NAME", "MODEL_BASE_URL", "MODEL_API_KEY",
                     "MODEL_ENABLED", "MODEL_TIMEOUT", "MODEL_REASONING_EFFORT"):
            env.pop("TRAVEL_" + name, None)
        backups = None
        configured = False
        try:
            local_json("/api/version")
            for attempt in range(1, DOWNLOAD_ATTEMPTS + 1):
                status("downloading", attempt=attempt, log=str(LOG_PATH))
                code = run(PYTHON, "-u", ROOT / "scripts/download_qwen35_artifacts.py", check=False)
                if code == 0:
                    break
                time.sleep(DOWNLOAD_RETRY_SECONDS)
            else:
                raise RuntimeError("Download retry budget exhausted; cached parts are retained")

            status("setting_context")
            run("ollama", "create", MODEL, "-f", ROOT / "scripts/models/qwen3.5-9b.Modelfile")
            details = local_json("/api/show", {"model": MODEL})
            if "8192" not in details.get("parameters", ""):
                raise RuntimeError("8K model parameter was not saved")
            warmup = local_json("/api/chat", {
                "model": MODEL, "messages": [{"role": "user", "content": "只回答：好"}],
                "think": False, "stream": False,
                "options": {"num_ctx": CONTEXT_TOKENS, "num_predict": 64},
            }, timeout=MODEL_TIMEOUT_SECONDS)
            if "好" not in warmup.get("message", {}).get("content", ""):
                raise RuntimeError("Native model warmup did not produce the expected answer")

            status("configuring")
            backups = ROOT / "data/private-backups" / datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ-auto-qwen35")
            backups.mkdir(parents=True, mode=0o700)
            backup_file(ROOT / "config.local.json", "travel-config.local.json", backups)
            backup_file(MEDICAL_ROOT / "llm_config.py", "medical-llm_config.py", backups)
            configured = True
            path = ROOT / "config.local.json"
            values = json.loads(path.read_text())
            values.update({
                "model_provider": "openai", "model_name": MODEL,
                "model_base_url": "http://127.0.0.1:11434/v1", "model_api_key": "ollama",
                "model_enabled": True, "model_timeout": MODEL_TIMEOUT_SECONDS,
                "model_reasoning_effort": "none",
            })
            path.write_text(json.dumps(values, ensure_ascii=False, indent=2) + "\n")
            os.chmod(path, 0o600)
            update_medical()

            status("verifying_local_model")
            run(PYTHON, ROOT / "scripts/check_local_model.py", timeout=900, env=env)
            run(PYTHON, ROOT / "scripts/atlas_stream_smoke.py", timeout=600, env=env)
            medical_probe = (
                "from llm_config import build_model; "
                "m=build_model(); r=m.invoke('只回答：好'); "
                "assert m.model=='qwen3.5:9b' and '好' in r.text; "
                "print('medicalProject local model OK')"
            )
            subprocess.run(
                [str(MEDICAL_ROOT / ".venv/bin/python"), "-c", medical_probe],
                cwd=MEDICAL_ROOT, check=True, timeout=180,
            )
            planning_code = None
            if RUN_PLANNING_SMOKE:
                status("planning_smoke")
                try:
                    planning_code = run(
                        PYTHON, ROOT / "scripts/evaluate.py", "--mode", "local-model-smoke",
                        timeout=2100, check=False, env=env,
                    )
                except subprocess.TimeoutExpired:
                    planning_code = "timeout"
                # Planning quality failures stay in reports; they are not replaced by templates.

            if RESTART_TRAVEL_SERVICE:
                status("restarting_services")
                restart_services(env)

            if DELETE_OLD_MODELS:
                status("removing_old_models")
                installed = {m["name"] for m in local_json("/api/tags")["models"]}
                for name in OLD_MODELS:
                    if name in installed:
                        run("ollama", "stop", name, check=False)
                        run("ollama", "rm", name)
                installed = {m["name"] for m in local_json("/api/tags")["models"]}
                if MODEL not in installed or any(name in installed for name in OLD_MODELS):
                    raise RuntimeError("Final model inventory does not match the upgrade")
            status("completed", model=MODEL, context_tokens=CONTEXT_TOKENS,
                   planning_smoke_exit=planning_code, backup=str(backups),
                   readiness_report=str(ROOT / "reports/qwen35-readiness.json"),
                   note="Planning smoke is not complete live travel quality acceptance.")
        except Exception as exc:
            # Download/probe failures must not cause old model deletion.
            # If a deletion itself fails, keep the verified new configuration instead of
            # restoring a configuration that may reference an already deleted model.
            stage = json.loads(STATUS_PATH.read_text()).get("stage") if STATUS_PATH.exists() else "startup"
            rolled_back = False
            if configured and backups and stage != "removing_old_models":
                shutil.copy2(backups / "travel-config.local.json", ROOT / "config.local.json")
                shutil.copy2(backups / "medical-llm_config.py", MEDICAL_ROOT / "llm_config.py")
                rolled_back = True
                if stage == "restarting_services":
                    try:
                        restart_services(env)
                    except Exception:
                        pass
            status("failed", failed_stage=stage, error_type=type(exc).__name__,
                   configurations_restored=rolled_back, old_models_preserved=stage != "removing_old_models")
            print("升级未完成；检查本日志和 status.json，重新运行可继续下载。", flush=True)
            raise SystemExit(1)


if __name__ == "__main__":
    main()
