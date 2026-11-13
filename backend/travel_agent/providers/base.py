"""Provider gateway: only read-only operations are retried and cached."""

import hashlib
import json
import random
import time
from datetime import datetime, timezone
from urllib.parse import urlparse
import httpx
import redis
from ..config import settings


class ProviderError(RuntimeError):
    def __init__(self, code, message, retryable=False):
        super().__init__(message)
        self.code, self.retryable = code, retryable


def timestamp():
    return datetime.now(timezone.utc).isoformat()


def safe_url(value):
    if not isinstance(value, str):
        return None
    parsed = urlparse(value)
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
        return None
    return value


def read_json(url, params, ttl=900):
    # URLs are constant provider endpoints, never arbitrary URLs supplied by a model.
    cache = redis.Redis.from_url(settings.redis_url, socket_timeout=2)
    key = "provider:v1:" + hashlib.sha256(json.dumps([url, params], sort_keys=True).encode()).hexdigest()
    try:
        old = cache.get(key)
        if old:
            return json.loads(old)
        minute = int(time.time() // 60)
        bucket = f"quota:{urlparse(url).hostname}:{minute}"
        count = cache.incr(bucket)
        cache.expire(bucket, 65)
        if count > 60:
            raise ProviderError("local_rate_limit", "本机调用频率已达上限，请稍后重试")
    except redis.RedisError:
        pass
    for attempt in range(3):
        try:
            with httpx.Client(timeout=httpx.Timeout(30, connect=5), follow_redirects=False) as client:
                response = client.get(url, params=params)
            if response.status_code == 429 or response.status_code >= 500:
                raise ProviderError("upstream_unavailable", "平台暂时不可用或已限流", True)
            if response.status_code != 200:
                raise ProviderError("upstream_rejected", f"平台拒绝查询（HTTP {response.status_code}）")
            result = response.json()
            if not isinstance(result, dict):
                raise ProviderError("schema", "平台返回了不符合约定的结构")
            # Never cache provider application errors (HTTP 200 can still be an error).
            if result.get("status") == "0" or result.get("errcode", 0) not in (0, "0"):
                raise ProviderError(
                    "provider_error", f"平台查询失败：{result.get('info', result.get('errmsg', '未知错误'))}"
                )
            envelope = {"data": result, "retrieved_at": timestamp()}
            try:
                cache.setex(key, ttl, json.dumps(envelope))
            except redis.RedisError:
                pass
            return envelope
        except (httpx.TimeoutException, httpx.NetworkError) as exc:
            error = ProviderError("network", "平台连接超时或网络不可用", True)
            error.__cause__ = exc
        except (ValueError, TypeError) as exc:
            raise ProviderError("schema", "平台返回内容无法解析") from exc
        except ProviderError as exc:
            error = exc
        if not error.retryable or attempt == 2:
            raise error
        time.sleep(0.4 * 2**attempt + random.random() * 0.2)


def source(provider, url, retrieved_at, **extra):
    return {"provider": provider, "url": url, "retrieved_at": retrieved_at, **extra}
