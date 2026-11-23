"""Actual offline embedding, reranking, speech and screenshot checks; no cloud models."""
from pathlib import Path
import io
import json
import sys

# Edit here, then Run from the IDE.
ROOT = Path(__file__).resolve().parents[2]
REPORT = ROOT / "reports/local-channels.json"
SPEECH_TEXT = "我想去北京旅游两天。"
FONT_PATH = "/System/Library/Fonts/STHeiti Medium.ttc"
sys.path.insert(0, str(ROOT / "backend"))


def main():
    from PIL import Image, ImageDraw, ImageFont
    from travel_agent.knowledge import embed, rerank
    from travel_agent.voice import synthesize, transcribe
    from travel_agent.vision import read_screenshot
    from travel_agent.models.registry import resolve

    from urllib.parse import urlparse
    for slot in ["chat", "structured", "vision", "asr", "tts"]:
        spec = resolve(slot)
        assert spec.protocol == "local" or urlparse(spec.base_url).hostname in {"127.0.0.1", "localhost", "::1"}, slot
    results = {}
    vectors = embed(["北京旅游", "上海天气"])
    assert len(vectors) == 2 and all(len(v) == 512 for v in vectors)
    results["embedding"] = {"passed": True, "vectors": len(vectors), "dimensions": len(vectors[0])}
    hits = rerank("北京景点", [{"text": "北京颐和园是一处园林景点", "id": "relevant"},
                             {"text": "如何安装电脑操作系统", "id": "unrelated"}])
    assert hits[0]["id"] == "relevant"
    results["rerank"] = {"passed": True, "order": [h["id"] for h in hits]}
    wav = synthesize(SPEECH_TEXT)
    assert wav[:4] == b"RIFF" and len(wav) > 1000
    (REPORT.parent / "local-speech.wav").write_bytes(wav)
    transcript = transcribe(wav)
    assert "北京" in transcript["text"], transcript
    results["speech"] = {"passed": True, "wav_bytes": len(wav), **transcript}
    canvas = Image.new("RGB", (900, 350), "white")
    font = ImageFont.truetype(FONT_PATH, 48)
    ImageDraw.Draw(canvas).multiline_text((40, 40), "北京旅游\n游玩 2 天\n预算 800 元", font=font, fill="black", spacing=20)
    raw = io.BytesIO()
    canvas.save(raw, "PNG")
    (REPORT.parent / "local-vision-input.png").write_bytes(raw.getvalue())
    screenshot = read_screenshot(raw.getvalue(), "image/png")
    assert screenshot["status"] == "ok", screenshot
    assert "北京" in screenshot["fields"]["cities"], screenshot
    results["vision"] = {"passed": True, "synthetic_input": True, "result": screenshot}
    REPORT.write_text(json.dumps({"passed": True, "checks": results}, ensure_ascii=False, indent=2))
    print(json.dumps(results, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
