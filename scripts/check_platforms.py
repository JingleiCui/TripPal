"""Read-only, small platform probes. Enable model/Meituan checks explicitly here."""

from pathlib import Path
import sys
import json
import time

CHECK_MODEL = False
CHECK_MEITUAN = False
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from travel_agent.config import settings
from travel_agent.providers import amap, meituan
from travel_agent.agent.harness import model


def main():
    report = {}
    checks = {}
    if settings.amap_key:
        checks["amap_places"] = lambda: amap.search_places("北京", "颐和园")
        checks["amap_weather"] = lambda: amap.weather("北京")
    else:
        report["amap"] = {"status": "not_run", "reason": "missing_key"}
    if CHECK_MODEL and settings.model_enabled and settings.model_api_key:
        checks["model"] = lambda: model().invoke("只回复：连接成功").content
    else:
        report["model"] = {"status": "not_run", "reason": "explicit_probe_disabled_or_missing_key"}
    if CHECK_MEITUAN and settings.meituan_enabled:
        checks["meituan"] = lambda: meituan.query("北京", "查询北京一间酒店的参考价格与预订入口，不下单")
    else:
        report["meituan"] = {"status": "not_run", "reason": "explicit_probe_disabled_or_missing_token"}
    for name, fn in checks.items():
        started = time.perf_counter()
        try:
            result = fn()
            report[name] = {
                "status": "passed",
                "elapsed_seconds": round(time.perf_counter() - started, 3),
                "result": result,
            }
        except Exception as exc:
            report[name] = {"status": "failed", "error_type": type(exc).__name__}
    folder = ROOT / "reports"
    folder.mkdir(exist_ok=True)
    (folder / "platform-connectivity.json").write_text(json.dumps(report, ensure_ascii=False, indent=2))
    print(
        json.dumps(
            {k: {a: b for a, b in v.items() if a != "result"} for k, v in report.items()},
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
