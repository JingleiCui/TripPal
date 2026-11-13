"""Actionable provider failures without returning URLs, keys or raw exceptions."""

from .providers.base import ProviderError


def classify(exc):
    text = str(exc).lower()
    status = getattr(exc, "status_code", getattr(exc, "code", None))
    if "user location is not supported" in text:
        return ProviderError(
            "model_region",
            "Gemini 拒绝当前地区的 API 请求；密钥已读取，请核对 Google 支持地区或选择可用的模型服务",
        )
    if status in (401, 403) or "api_key_invalid" in text or "api key not valid" in text:
        return ProviderError("credentials", "模型鉴权失败，请检查密钥来源、有效期和模型访问权限")
    if status == 429 or "resource_exhausted" in text:
        return ProviderError("quota", "模型额度或调用频率受限，请检查平台配额后重试")
    if "not_found" in text or status == 404:
        return ProviderError("model_not_found", "平台没有找到该模型，请按账号可用模型列表核对 model_name")
    return None
