"""Invoke the official, locally pinned CLI without shell interpolation.

Token stays in the official CLI's ~/.config/meituan-travel/config.json.
Raw prices and links are preserved; no conversion of masked prices into numbers.

除了原有的酒旅查询（query），新增美食推荐（food_recommend）与优惠/团购检索
（deal_search），使美团在「吃住行」中被深度利用，而不仅是住宿商品。
"""

from pathlib import Path
import subprocess
from .base import ProviderError, timestamp
from ..config import settings


def configured():
    return settings.meituan_enabled and Path(settings.meituan_cli).is_file()


def _run_cli(city: str, question: str, timeout=None):
    """统一封装官方 CLI 调用；调用方负责构造 question。"""
    if not configured():
        raise ProviderError("credentials", "美团酒旅尚未启用，请按申请手册配置官方 CLI Token")
    try:
        result = subprocess.run(
            [settings.meituan_cli, city[:40], question[:2000]],
            capture_output=True,
            text=True,
            timeout=timeout or settings.meituan_timeout,
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


def query(city: str, question: str):
    """酒店、门票或交通商品查询（酒旅官方接口）。"""
    return _run_cli(city, question)


def food_recommend(city: str, query: str = "", timeout=None):
    """美食与团购推荐：引导 CLI 返回本地人气餐厅、特色菜与到店/团购信息。

    即便美团不可用也优雅降级，不影响高德 POI 美食检索的兜底。"""
    question = (
        f"推荐{city}本地人气餐厅、特色美食与团购套餐，给出名称、人均、地址和到店/预订方式。"
        f"{query}".strip()
    )
    try:
        result = _run_cli(city, question, timeout=timeout)
        result["source"] = {**result["source"], "provider": "美团美食"}
        return result
    except ProviderError as exc:
        if exc.code in ("empty", "upstream_rejected", "timeout"):
            return {
                "items": [],
                "facts": [],
                "raw_text": "",
                "note": "美团美食暂不可用：" + exc.args[0],
                "source": {"provider": "美团美食", "url": "https://www.meituan.com/", "retrieved_at": timestamp()},
                "booking_status": "未预订",
            }
        raise


def deal_search(city: str, query: str = ""):
    """酒店/门票/交通的优惠活动与团购检索。"""
    question = (
        f"查询{city}的酒店、门票与交通优惠活动及团购，给出名称、价格与有效期。{query}".strip()
    )
    return _run_cli(city, question)
