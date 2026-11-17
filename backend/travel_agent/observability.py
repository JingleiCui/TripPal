"""统一请求标识、结构化日志与错误响应契约。

前端 `api.ts` 依赖 `detail`（字符串）与 `error.{code,message,request_id}`。
这里保留 `detail` 原样以兼容既有页面、脚本与浏览器测试，同时新增 `error`
对象，让前端可以按错误码分类处理、把 request_id 展示给用户用于排障。
"""

from __future__ import annotations

import logging
import secrets
import time

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

logger = logging.getLogger("travel_agent")
if not logger.handlers:
    _handler = logging.StreamHandler()
    _handler.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s")
    )
    logger.addHandler(_handler)
    logger.setLevel(logging.INFO)
    logger.propagate = False

STATUS_CODES = {
    400: "bad_request",
    401: "unauthorized",
    403: "forbidden",
    404: "not_found",
    405: "method_not_allowed",
    409: "conflict",
    413: "payload_too_large",
    422: "validation_error",
    429: "rate_limited",
    500: "internal_error",
    502: "upstream_error",
    503: "service_unavailable",
    504: "upstream_timeout",
}

FALLBACK_MESSAGES = {
    400: "输入内容不符合要求，请检查日期、天数等字段",
    401: "请先登录",
    403: "当前操作没有权限",
    404: "请求的内容不存在",
    409: "数据已被其他修改更新，请刷新后再试",
    422: "输入内容不符合要求，请检查日期、天数等字段",
    429: "操作过于频繁，请稍后再试",
    500: "服务内部错误，请稍后重试",
    503: "依赖服务暂不可用，请稍后重试",
}


def new_request_id(request: Request) -> str:
    """复用前端或网关传入的 ID，否则生成本次请求的短标识。"""
    supplied = request.headers.get("x-request-id", "")
    if supplied and len(supplied) <= 64 and supplied.isprintable():
        return supplied
    return secrets.token_hex(8)


def message_from_detail(detail: object, status: int) -> str:
    if isinstance(detail, str) and detail.strip():
        return detail
    return FALLBACK_MESSAGES.get(status, f"请求失败（HTTP {status}）")


def error_payload(
    status: int,
    detail: object,
    request_id: str,
    code: str | None = None,
) -> dict:
    return {
        "detail": detail,
        "error": {
            "code": code or STATUS_CODES.get(status, "request_failed"),
            "message": message_from_detail(detail, status),
            "request_id": request_id,
        },
    }


def log_access(request: Request, status: int, started: float) -> None:
    duration_ms = round((time.perf_counter() - started) * 1000, 1)
    logger.info(
        "request method=%s path=%s status=%s duration_ms=%s request_id=%s",
        request.method,
        request.url.path,
        status,
        duration_ms,
        getattr(request.state, "request_id", "-"),
    )


def install(app: FastAPI) -> None:
    """注册 HTTPException / RequestValidationError 的统一响应格式。

    未捕获异常由 api.py 的中间件兜底（那里同时负责访问日志），避免
    Starlette 的 ServerErrorMiddleware 在 TestClient 中二次抛错。
    """

    @app.exception_handler(StarletteHTTPException)
    async def http_exception_handler(request: Request, exc: StarletteHTTPException):
        request_id = getattr(request.state, "request_id", "") or new_request_id(request)
        if exc.status_code >= 500:
            logger.error(
                "http_error status=%s path=%s request_id=%s detail=%s",
                exc.status_code,
                request.url.path,
                request_id,
                exc.detail,
            )
        return JSONResponse(
            status_code=exc.status_code,
            content=error_payload(exc.status_code, exc.detail, request_id),
            headers={"X-Request-Id": request_id},
        )

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(
        request: Request, exc: RequestValidationError
    ):
        request_id = getattr(request.state, "request_id", "") or new_request_id(request)
        errors = jsonable_encoder(exc.errors())
        logger.info(
            "validation_error path=%s request_id=%s fields=%s",
            request.url.path,
            request_id,
            [item.get("loc") for item in errors],
        )
        return JSONResponse(
            status_code=422,
            content=error_payload(
                422, errors, request_id, code="validation_error"
            ),
            headers={"X-Request-Id": request_id},
        )
