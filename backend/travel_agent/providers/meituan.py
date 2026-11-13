"""Invoke the official, locally pinned CLI without shell interpolation.

Token stays in the official CLI's ~/.config/meituan-travel/config.json.
Raw prices and links are preserved; no conversion of masked prices into numbers.
"""

from pathlib import Path
import subprocess
from .base import ProviderError, timestamp
from ..config import settings


def configured():
    return settings.meituan_enabled and Path(settings.meituan_cli).is_file()


def query(city: str, question: str):
    if not configured():
        raise ProviderError("credentials", "美团酒旅尚未启用，请按申请手册配置官方 CLI Token")
    try:
        result = subprocess.run(
            [settings.meituan_cli, city[:40], question[:2000]],
            capture_output=True,
            text=True,
            timeout=settings.meituan_timeout,
            shell=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise ProviderError("timeout", "美团查询超时，已保留其他行程结果；可单独重试") from exc
    if result.returncode:
        # Provider stderr may include secrets. Do not expose it to the browser or model.
        raise ProviderError("upstream_rejected", "美团查询失败，请检查本机 Token、额度及 CLI 配置")
    text = result.stdout.strip()
    if not text:
        raise ProviderError("empty", "美团没有返回查询内容")
    if len(text) > 200000:
        raise ProviderError("schema", "美团返回内容超过本次处理上限")
    from ..market_cards import cards_from_markdown, merchant_facts_from_markdown

    return {
        "items": cards_from_markdown(text),
        "facts": merchant_facts_from_markdown(text),
        "raw_text": text,
        "price_policy": "原文价格，不能推断脱敏数字或视为最终成交价",
        "source": {"provider": "美团酒旅", "url": "https://www.meituan.com/", "retrieved_at": timestamp()},
        "booking_status": "未预订",
    }
