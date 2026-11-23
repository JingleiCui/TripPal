"""Run from the IDE: prepare local models/services and validate the whole project.

Configuration lives below. Verified stages are cached by source/config/environment hashes.
No cloud model probes are allowed. Downloads reuse existing official artifacts.
"""

from datetime import datetime, timezone
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import time
from urllib.parse import urlparse
import urllib.request

# ==================== User-editable configuration ====================
ROOT = Path(__file__).resolve().parents[1]
PYTHON = ROOT / ".venv/bin/python"
MODEL = "qwen3.5:9b"
OLLAMA_URL = "http://127.0.0.1:11435"
EMBEDDING = "BAAI/bge-small-zh-v1.5"
RERANKER = "BAAI/bge-reranker-base"
ASR = "Systran/faster-whisper-small"
TTS_VOICE = "Tingting"
PROFILE = "local_complete"
RUN_BACKEND_TESTS = True
RUN_NOTE_IMPORT_CHECK = True
RUN_BROWSER_TESTS = True
RUN_REAL_PLANNING = True
RUN_MULTI_CITY_AND_EDIT = True
MODEL_SCENARIO_REPETITIONS = 1
REUSE_SUCCESSFUL_CHECKS = True
REPORT_DIR = ROOT / "reports/local-setup"
COMMAND_TIMEOUT = 1800
MODEL_DOWNLOAD_TIMEOUT = 7200
# ====================================================================
ENV = {
    **os.environ,
    "PYTHONPATH": str(ROOT / "backend"),
    "TOKENIZERS_PARALLELISM": "false",
    "OMP_NUM_THREADS": "2",
    "TRIPAL_OLLAMA_URL": OLLAMA_URL,
}
for _name in list(ENV):
    if _name.startswith(
        ("TRAVEL_MODEL_", "TRAVEL_VISION_", "TRAVEL_VOICE_", "TRAVEL_GEMINI_", "TRAVEL_STRUCTURED_")
    ):
        ENV.pop(_name)
for _name in ("TRAVEL_ASR_MODEL", "TRAVEL_TTS_MODEL"):
    ENV.pop(_name, None)
ENV["TRAVEL_ACTIVE_MODEL_PROFILE"] = PROFILE
REPORT = {"started_utc": datetime.now(timezone.utc).isoformat(), "stages": {}}
PREVIOUS = {}
OPEN_LOGS = []


def save():
    target = REPORT_DIR / "status.json"
    temp = target.with_suffix(".tmp")
    temp.write_text(json.dumps(REPORT, ensure_ascii=False, indent=2))
    temp.replace(target)


def run(name, args, *, env=None, timeout=COMMAND_TIMEOUT):
    reusable = name in {
        "model_readiness",
        "local_channels",
        "note_imports",
        "backend",
        "regression",
        "local_planning",
        "streaming",
        "live_planning",
        "live_scenarios",
        "frontend_build",
        "browser",
    }
    effective = env or ENV
    digest = hashlib.sha256(repr([str(a) for a in args]).encode())
    digest.update(
        json.dumps(
            {k: v for k, v in effective.items() if k.startswith(("TRAVEL_", "TRIPAL_", "HF_"))},
            sort_keys=True,
        ).encode()
    )
    sources = list((ROOT / "backend/travel_agent").rglob("*.py")) + [ROOT / "config.local.json"]
    sources += [ROOT / str(a) for a in args if str(a).endswith(".py") and (ROOT / str(a)).is_file()]
    if name == "backend":
        sources += list((ROOT / "backend/tests").rglob("*.py"))
    if name in {"frontend_build", "browser"}:
        sources += [p for d in ["frontend/src", "frontend/e2e"] for p in (ROOT / d).rglob("*") if p.is_file()]
        sources += [ROOT / "frontend/playwright.config.ts", ROOT / "frontend/package-lock.json"]
    for path in sorted(set(sources)):
        digest.update(str(path.relative_to(ROOT)).encode())
        digest.update(path.read_bytes())
    fingerprint = digest.hexdigest()
    prior = PREVIOUS.get(name, {})
    if (
        reusable
        and REUSE_SUCCESSFUL_CHECKS
        and prior.get("passed")
        and prior.get("fingerprint") == fingerprint
    ):
        REPORT["stages"][name] = {**prior, "reused": True}
        save()
        print(name, "reused verified result", flush=True)
        return
    REPORT["current_stage"] = name
    save()
    print(name, flush=True)
    started = time.monotonic()
    log = REPORT_DIR / (name + ".log")
    try:
        with log.open("w") as output:
            result = subprocess.run(
                [str(a) for a in args],
                cwd=ROOT,
                env=effective,
                stdout=output,
                stderr=subprocess.STDOUT,
                timeout=timeout,
            )
        code = result.returncode
    except subprocess.TimeoutExpired:
        code = -1
    REPORT["stages"][name] = {
        "passed": code == 0,
        "exit_code": code,
        "seconds": round(time.monotonic() - started, 2),
        "log": str(log),
        "fingerprint": fingerprint,
    }
    save()
    if code:
        raise RuntimeError(f"{name} failed; see {log}")


def port_open(port):
    with socket.socket() as client:
        client.settimeout(1)
        return client.connect_ex(("127.0.0.1", port)) == 0


def wait_port(port, timeout=120):
    start = time.monotonic()
    while time.monotonic() - start < timeout:
        if port_open(port):
            return
        time.sleep(1)
    raise RuntimeError(f"Port {port} did not become ready")


def spawn(name, args, env):
    output = (REPORT_DIR / (name + ".log")).open("a")
    OPEN_LOGS.append(output)
    return subprocess.Popen(
        [str(a) for a in args],
        cwd=ROOT,
        env=env,
        stdout=output,
        stderr=subprocess.STDOUT,
        start_new_session=True,
    )


def prepare_models():
    port = urlparse(OLLAMA_URL).port or 11434
    model_env = {
        **ENV,
        "OLLAMA_HOST": OLLAMA_URL.removeprefix("http://"),
        "OLLAMA_MODELS": str(Path.home() / ".ollama/models"),
    }
    if not port_open(port):
        process = spawn("ollama", ["ollama", "serve"], model_env)
        REPORT["ollama_pid"] = process.pid
        wait_port(port)
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with opener.open(OLLAMA_URL + "/api/tags", timeout=10) as response:
        names = [m["name"] for m in json.load(response)["models"]]
    if MODEL not in names:
        run(
            "download_qwen",
            [PYTHON, "-u", ROOT / "scripts/local/download_qwen.py"],
            timeout=MODEL_DOWNLOAD_TIMEOUT,
        )
    run(
        "ollama_context",
        ["ollama", "create", MODEL, "-f", ROOT / "scripts/models/qwen3.5-9b.Modelfile"],
        env=model_env,
    )
    if not importlib.util.find_spec("faster_whisper"):
        run("speech_dependencies", [PYTHON, "-m", "pip", "install", "faster-whisper==1.2.1"])
    from huggingface_hub import snapshot_download

    for name in [EMBEDDING, RERANKER, ASR]:
        try:
            path = snapshot_download(name, local_files_only=True)
            if not any(Path(path).rglob("*.safetensors")) and not (Path(path) / "model.bin").exists():
                raise FileNotFoundError(name)
        except (OSError, ValueError):
            path = snapshot_download(
                name, allow_patterns=["*.json", "*.txt", "*.model", "*.bin", "*.safetensors"]
            )
        REPORT.setdefault("models", {})[name] = str(path)
    ENV["HF_HUB_OFFLINE"] = "1"
    save()


def configure():
    target = ROOT / "config.local.json"
    values = json.loads(target.read_text()) if target.exists() else {}
    values.update(
        active_model_profile=PROFILE,
        embedding_model=EMBEDDING,
        reranker_model=RERANKER,
        embedding_local_only=True,
        reranker_enabled=True,
    )
    values.setdefault("model_profiles", {})[PROFILE] = {
        "model_provider": "ollama",
        "model_name": MODEL,
        "model_base_url": OLLAMA_URL,
        "model_api_key": "",
        "model_enabled": True,
        "model_timeout": 180,
        "model_context_tokens": 8192,
        "model_output_tokens": 4096,
        "vision_enabled": True,
        "voice_enabled": True,
        "vision_api_key": "",
        "voice_api_key": "",
        "vision_model": MODEL,
        "asr_model": ASR,
        "tts_model": TTS_VOICE,
        "model_slots": {
            "vision": {
                "provider": "ollama",
                "model": MODEL,
                "base_url": OLLAMA_URL,
                "enabled": True,
                "timeout": 180,
            },
            "asr": {"provider": "local_speech", "model": ASR, "enabled": True, "timeout": 120},
            "tts": {"provider": "local_speech", "model": TTS_VOICE, "enabled": True, "timeout": 60},
        },
    }
    serialized = json.dumps(values, ensure_ascii=False, indent=2)
    if target.exists() and target.read_text() == serialized:
        return
    if target.exists():
        folder = ROOT / "data/private-backups/local-setup"
        folder.mkdir(parents=True, exist_ok=True)
        backup = folder / (datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%f") + ".json")
        shutil.copy2(target, backup)
        backup.chmod(0o600)
    temp = target.with_suffix(".tmp")
    temp.write_text(serialized)
    temp.chmod(0o600)
    temp.replace(target)


def databases():
    for _ in range(60):
        probe = subprocess.run(
            [
                "docker",
                "compose",
                "exec",
                "-T",
                "mysql",
                "mysqladmin",
                "ping",
                "-h",
                "127.0.0.1",
                "-uroot",
                "-ptravel_root_local_only",
            ],
            cwd=ROOT,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        if probe.returncode == 0:
            break
        time.sleep(2)
    else:
        raise RuntimeError("MySQL did not become ready")
    sql = " ".join(
        f"CREATE DATABASE IF NOT EXISTS {name} CHARACTER SET utf8mb4; "
        f"GRANT ALL PRIVILEGES ON {name}.* TO 'travel'@'%';"
        for name in ["travel_agent_test", "travel_agent_eval"]
    )
    run(
        "test_databases",
        [
            "docker",
            "compose",
            "exec",
            "-T",
            "mysql",
            "mysql",
            "-uroot",
            "-ptravel_root_local_only",
            "-e",
            sql,
        ],
    )
    run("migrations", [PYTHON, "-m", "alembic", "upgrade", "head"])


def browser_tests():
    env = {
        **ENV,
        "TRAVEL_DATABASE_URL": "mysql+pymysql://travel:travel_local_only@127.0.0.1:13316/travel_agent_test?charset=utf8mb4",
        "TRAVEL_CHECKPOINT_URL": "mysql://travel:travel_local_only@127.0.0.1:13316/travel_agent_test",
        "TRAVEL_REDIS_URL": "redis://127.0.0.1:16389/10",
        "TRAVEL_BROKER_URL": "redis://127.0.0.1:16389/11",
        "TRAVEL_ELASTIC_INDEX": "travel-agent-test-chunks",
        "TRAVEL_SEMANTIC_CACHE_INDEX": "travel-agent-test-research-cache",
        "TRAVEL_DATA_DIR": "/tmp/travel-agent-test-uploads",
        "TRIPAL_E2E_BASE_URL": "http://127.0.0.1:8818",
    }
    if port_open(8818):
        raise RuntimeError("Isolated browser test port 8818 is occupied")
    api = spawn("browser_api", [PYTHON, "-m", "uvicorn", "travel_agent.api:app", "--port", "8818"], env)
    worker = spawn(
        "browser_worker",
        [
            PYTHON,
            "-m",
            "celery",
            "-A",
            "travel_agent.worker:celery",
            "worker",
            "--pool=solo",
            "--concurrency=1",
            "--loglevel=WARNING",
        ],
        env,
    )
    try:
        wait_port(8818)
        run("browser", ["npm", "run", "test:e2e", "--prefix", "frontend"], env=env)
    finally:
        for process in [worker, api]:
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()


def main():
    global PREVIOUS
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    existing = REPORT_DIR / "status.json"
    if existing.exists():
        PREVIOUS = json.loads(existing.read_text()).get("stages", {})
    save()
    try:
        run("containers", ["docker", "compose", "up", "-d"])
        for port in [13316, 16389, 19220]:
            wait_port(port)
        prepare_models()
        configure()
        databases()
        run("model_readiness", [PYTHON, "scripts/local/check_model.py"])
        run("local_channels", [PYTHON, "scripts/validation/local_channels.py"])
        if RUN_NOTE_IMPORT_CHECK:
            run("note_imports", [PYTHON, "scripts/validation/notes.py"])
        if RUN_BACKEND_TESTS:
            run(
                "backend",
                [PYTHON, "-m", "pytest", "-q", "--tb=short"],
                env={**ENV, "TRAVEL_ACTIVE_MODEL_PROFILE": ""},
            )
        run("regression", [PYTHON, "scripts/validation/evaluate.py", "--mode", "regression"])
        run("local_planning", [PYTHON, "scripts/validation/evaluate.py", "--mode", "local-model-smoke"])
        run("streaming", [PYTHON, "scripts/validation/stream.py"])
        if RUN_REAL_PLANNING:
            run("live_planning", [PYTHON, "scripts/validation/plan.py"])
        if RUN_REAL_PLANNING and RUN_MULTI_CITY_AND_EDIT:
            run(
                "live_scenarios",
                [PYTHON, "scripts/validation/scenarios.py"],
                env={**ENV, "TRIPAL_MODEL_REPETITIONS": str(MODEL_SCENARIO_REPETITIONS)},
            )
        run("frontend_build", ["npm", "run", "build", "--prefix", "frontend"])
        if RUN_BROWSER_TESTS:
            browser_tests()
        if not port_open(8808):
            app_env = {k: v for k, v in ENV.items() if k != "TRAVEL_ACTIVE_MODEL_PROFILE"}
            launcher = spawn("application", [PYTHON, "run_project.py"], app_env)
            REPORT["application_launcher_pid"] = launcher.pid
            wait_port(8808)
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with opener.open("http://127.0.0.1:8808/api/v1/models", timeout=10) as response:
            view = json.load(response)
        for name, slot in view["slots"].items():
            if slot.get("status") != "ready":
                raise RuntimeError(f"Model slot {name} is not ready")
            if slot.get("protocol") != "local" and urlparse(slot.get("base_url", "")).hostname not in {
                "127.0.0.1",
                "localhost",
                "::1",
            }:
                raise RuntimeError(f"Model slot {name} unexpectedly targets a remote endpoint")
        REPORT.update(model_slots=view["slots"], current_stage="complete", passed=True)
    except Exception as exc:
        REPORT.update(passed=False, error=str(exc))
        raise
    finally:
        REPORT["finished_utc"] = datetime.now(timezone.utc).isoformat()
        save()
    print("Complete:", REPORT_DIR / "status.json", flush=True)


if __name__ == "__main__":
    main()
