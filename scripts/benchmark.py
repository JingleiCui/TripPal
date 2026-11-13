"""Small local API baseline; does not call travel providers or models."""

from pathlib import Path
import json
import math
import subprocess
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
import httpx

BASE_URL = "http://127.0.0.1:8808"
REQUESTS = 30
CONCURRENCY = 4
ROOT = Path(__file__).resolve().parents[1]


def main():
    with httpx.Client(base_url=BASE_URL, timeout=15, trust_env=False) as client:
        r = client.post(
            "/api/v1/auth/register",
            json={"name": "benchmark-" + uuid.uuid4().hex[:12], "password": "local-benchmark-only-123"},
        )
        r.raise_for_status()

        def sample(_):
            start = time.perf_counter()
            r = client.get("/api/v1/trips")
            r.raise_for_status()
            return (time.perf_counter() - start) * 1000

        sample(0)
        with ThreadPoolExecutor(max_workers=CONCURRENCY) as pool:
            values = list(pool.map(sample, range(REQUESTS)))
    ordered = sorted(values)
    containers = subprocess.run(
        [
            "docker",
            "stats",
            "--no-stream",
            "--format",
            "{{json .}}",
            "travel-agent-mysql-1",
            "travel-agent-redis-1",
            "travel-agent-elasticsearch-1",
        ],
        capture_output=True,
        text=True,
    ).stdout
    memory = subprocess.run(["memory_pressure", "-Q"], capture_output=True, text=True).stdout
    report = {
        "endpoint": "GET /api/v1/trips",
        "requests": REQUESTS,
        "concurrency": CONCURRENCY,
        "warmed": True,
        "p50_ms": round(ordered[math.ceil(len(ordered) * 0.5) - 1], 2),
        "p95_ms": round(ordered[math.ceil(len(ordered) * 0.95) - 1], 2),
        "samples_ms": values,
        "container_stats": [json.loads(line) for line in containers.splitlines() if line],
        "host_memory_pressure": memory,
        "limitations": "空行程账号、少量本机请求；不是 Agent 性能或容量承诺",
    }
    folder = ROOT / "reports"
    folder.mkdir(exist_ok=True)
    (folder / "performance.json").write_text(json.dumps(report, ensure_ascii=False, indent=2))
    print("p50_ms", report["p50_ms"], "p95_ms", report["p95_ms"])


if __name__ == "__main__":
    main()
