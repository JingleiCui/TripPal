"""Actual local-model note import acceptance. Separate evaluation DB; synthetic inputs labelled."""

from pathlib import Path
import io
import json
import os
import sys
import subprocess
import time
import uuid
from unittest.mock import patch

# User-editable configuration; no cloud inference is allowed by this check.
ROOT = Path(__file__).resolve().parents[2]
REPORT = ROOT / "reports/note-import-real-local.json"
FONT = "/System/Library/Fonts/STHeiti Medium.ttc"
VERIFY_QUEUE = True  # One additional text-only import verifies the real isolated background worker.
os.environ["TRAVEL_DATABASE_URL"] = (
    "mysql+pymysql://travel:travel_local_only@127.0.0.1:13316/travel_agent_eval?charset=utf8mb4"
)
os.environ["TRAVEL_CHECKPOINT_URL"] = "mysql://travel:travel_local_only@127.0.0.1:13316/travel_agent_eval"
os.environ["TRAVEL_REDIS_URL"] = "redis://127.0.0.1:16389/12"
os.environ["TRAVEL_BROKER_URL"] = "redis://127.0.0.1:16389/13"
os.environ["TRAVEL_DATA_DIR"] = "/tmp/tripal-note-real-qa"
sys.path.insert(0, str(ROOT / "backend"))


def verify_queue(client):
    log = REPORT.with_suffix(".worker.log").open("w")
    env = {**os.environ, "PYTHONPATH": str(ROOT / "backend")}
    worker = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "celery",
            "-A",
            "travel_agent.notes.worker:celery",
            "worker",
            "-Q",
            "note_imports",
            "--pool=solo",
            "--concurrency=1",
            "--loglevel=WARNING",
            "--hostname=note-qa@%h",
            "--without-gossip",
            "--without-mingle",
        ],
        cwd=ROOT,
        env=env,
        stdout=log,
        stderr=subprocess.STDOUT,
    )
    try:
        response = client.post("/api/v1/note-imports", data={"body_text": "北京颐和园一日游，仅作规划参考。"})
        response.raise_for_status()
        ident = response.json()["id"]
        assert response.json()["parsed"]["status"] == "queued"
        deadline = time.monotonic() + 120
        while time.monotonic() < deadline:
            if worker.poll() is not None:
                raise RuntimeError("Background worker exited; see the worker log")
            result = client.get("/api/v1/note-imports/" + ident).json()["parsed"]
            if result["status"] not in {"queued", "running"}:
                assert result["status"] == "ready" and result["facts"], result
                return True
            time.sleep(2)
        raise RuntimeError("Background import timed out")
    finally:
        worker.terminate()
        try:
            worker.wait(timeout=10)
        except subprocess.TimeoutExpired:
            worker.kill()
            worker.wait()
        log.close()


def main():
    from PIL import Image, ImageDraw, ImageFont
    from fastapi.testclient import TestClient
    from travel_agent.api import app
    from travel_agent.db import Base, engine
    from travel_agent.models.registry import resolve
    from travel_agent.notes import jobs

    for slot in ["chat", "structured", "vision"]:
        spec = resolve(slot)
        assert spec.provider == "ollama", "Refusing cloud-model probes"
    Base.metadata.create_all(engine)
    picture = Image.new("RGB", (900, 520), "white")
    draw = ImageDraw.Draw(picture)
    draw.multiline_text(
        (35, 30),
        "北京一日游攻略\n第一站：颐和园\n第二站：圆明园\n预算：200元，仅供参考",
        font=ImageFont.truetype(FONT, 42),
        fill="black",
        spacing=20,
    )
    graphic = io.BytesIO()
    picture.save(graphic, "PNG")
    # Synthetic non-text image + camera-style footer: verify exclusion, not photographic accuracy.
    empty = Image.new("RGB", (900, 520))
    pixels = empty.load()
    for y in range(520):
        for x in range(900):
            pixels[x, y] = (int(30 + y * 0.2), int(100 + x * 0.08), 180)
    camera = empty.copy()
    d = ImageDraw.Draw(camera)
    d.rectangle((0, 440, 900, 520), fill="white")
    d.text(
        (30, 455),
        "SONY A7 IV  |  35mm  f/2.8  1/250s  ISO100",
        font=ImageFont.truetype(FONT, 25),
        fill="black",
    )
    photo = io.BytesIO()
    empty.save(photo, "PNG")
    watermark = io.BytesIO()
    camera.save(watermark, "PNG")
    client = TestClient(app)
    name = "note-real-" + uuid.uuid4().hex[:10]
    result = client.post(
        "/api/v1/auth/register", json={"name": name, "password": "Local-note-acceptance-123"}
    )
    result.raise_for_status()
    client.headers["X-CSRF-Token"] = result.json()["csrf"]
    with patch.object(jobs, "dispatch"):
        response = client.post(
            "/api/v1/note-imports",
            data={
                "body_text": "北京旅行参考攻略。颐和园和圆明园适合按区域安排，作者预算200元不代表实时价格。"
            },
            files=[
                ("files", ("guide.png", graphic.getvalue(), "image/png")),
                ("files", ("plain.png", photo.getvalue(), "image/png")),
                ("files", ("camera.png", watermark.getvalue(), "image/png")),
            ],
        )
    response.raise_for_status()
    ident = response.json()["id"]
    start = time.monotonic()
    jobs.process(ident)
    note = client.get("/api/v1/note-imports/" + ident).json()
    data = note["parsed"]
    assert data["status"] in {"ready", "partial"}, data
    assert data["images"][0]["status"] == "ok", data["images"][0]
    assert "颐和园" in data["images"][0]["text"]
    assert all(i["status"] == "skipped" for i in data["images"][1:]), data["images"]
    facts = data["facts"]
    assert any(f["kind"] == "place" and "颐和园" in f["text"] for f in facts)
    assert all(f["sources"] for f in facts)
    confirmed = client.post(
        f"/api/v1/note-imports/{ident}/confirm", json={"selected_fact_ids": [f["id"] for f in facts]}
    )
    confirmed.raise_for_status()
    output = {
        "passed": True,
        "synthetic_inputs": True,
        "actual_local_inference": True,
        "seconds": round(time.monotonic() - start, 2),
        "import_id": ident,
        "images": data["images"],
        "facts": facts,
        "status": data["status"],
        "map_matches": sum(bool(f.get("place")) for f in facts),
    }
    output["async_queue_verified"] = verify_queue(client) if VERIFY_QUEUE else False
    REPORT.write_text(json.dumps(output, ensure_ascii=False, indent=2))
    print(json.dumps({k: v for k, v in output.items() if k not in {"images", "facts"}}, ensure_ascii=False))


if __name__ == "__main__":
    main()
