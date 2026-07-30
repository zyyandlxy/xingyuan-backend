"""
中间件层
请求ID注入、请求计时、API Key 认证、IP 限流
"""

from __future__ import annotations

import time
import uuid
from collections import defaultdict
from contextvars import ContextVar

from fastapi import Request, Response
from loguru import logger
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

from agent.config import get_settings
from agent.exceptions import AuthenticationError, RateLimitExceeded
from agent.models import ErrorResponse

# 请求级上下文变量
request_id_var: ContextVar[str] = ContextVar("request_id", default="")

# 无需认证的路径
AUTH_WHITELIST = {
    "/health",
    "/health/ready",
    "/docs",
    "/openapi.json",
    "/redoc",
    "/favicon.ico",
    "/",
    "/auth/login",
    "/auth/register",
}


# ═══════════════════════════════════════════
# 请求 ID 中间件
# ═══════════════════════════════════════════

class RequestIDMiddleware(BaseHTTPMiddleware):
    """为每个请求注入唯一 ID，用于日志追踪"""

    async def dispatch(self, request: Request, call_next):
        rid = request.headers.get("X-Request-ID") or f"req_{uuid.uuid4().hex[:12]}"
        request_id_var.set(rid)

        response: Response = await call_next(request)
        response.headers["X-Request-ID"] = rid
        return response


# ═══════════════════════════════════════════
# 请求计时中间件
# ═══════════════════════════════════════════

class TimingMiddleware(BaseHTTPMiddleware):
    """记录每个请求的处理耗时"""

    async def dispatch(self, request: Request, call_next):
        start = time.monotonic()
        response: Response = await call_next(request)
        elapsed_ms = (time.monotonic() - start) * 1000
        response.headers["X-Process-Time"] = f"{elapsed_ms:.1f}ms"
        return response


# ═══════════════════════════════════════════
# API Key 认证中间件
# ═══════════════════════════════════════════

class AuthMiddleware(BaseHTTPMiddleware):
    """X-API-Key 认证中间件"""

    async def dispatch(self, request: Request, call_next):
        settings = get_settings()

        # 认证未启用或路径在白名单中
        if not settings.is_auth_enabled:
            return await call_next(request)

        # 检查路径是否在白名单
        path = request.url.path.rstrip("/") or "/"
        if path in AUTH_WHITELIST or path.startswith("/static") or path.startswith("/auth/"):
            return await call_next(request)

        api_key = request.headers.get("X-API-Key") or request.headers.get("Authorization", "").removeprefix("Bearer ")

        if not api_key or api_key != settings.service_api_key:
            return JSONResponse(
                status_code=401,
                content=ErrorResponse(
                    error="认证失败",
                    detail="Missing or invalid X-API-Key header",
                    code="AUTHENTICATION_FAILED",
                    request_id=request_id_var.get(),
                ).model_dump(),
            )

        return await call_next(request)


# ═══════════════════════════════════════════
# 令牌桶限流中间件
# ═══════════════════════════════════════════

class RateLimitMiddleware(BaseHTTPMiddleware):
    """基于 IP 的令牌桶限流"""

    def __init__(self, app, **kwargs):
        super().__init__(app)
        self._buckets: dict[str, tuple[float, float]] = {}
        self._locks: dict[str, bool] = defaultdict(bool)

    async def dispatch(self, request: Request, call_next):
        settings = get_settings()

        if settings.rate_limit_per_minute <= 0:
            return await call_next(request)

        # 跳过白名单路径
        path = request.url.path.rstrip("/") or "/"
        if path in AUTH_WHITELIST:
            return await call_next(request)

        # 获取客户端 IP
        client_ip = (
            request.headers.get("X-Forwarded-For", "").split(",")[0].strip()
            or request.headers.get("X-Real-IP", "")
            or (request.client.host if request.client else "unknown")
        )

        if not self._consume(client_ip, settings.rate_limit_per_minute):
            return JSONResponse(
                status_code=429,
                content=ErrorResponse(
                    error="请求过于频繁",
                    detail=f"Limit: {settings.rate_limit_per_minute}/min",
                    code="RATE_LIMIT_EXCEEDED",
                    request_id=request_id_var.get(),
                ).model_dump(),
                headers={"Retry-After": "60"},
            )

        return await call_next(request)

    def _consume(self, key: str, rate: int) -> bool:
        """令牌桶消费，返回是否允许"""
        now = time.monotonic()
        refill_rate = rate / 60.0  # tokens per second

        last_ts, tokens = self._buckets.get(key, (now, float(rate)))

        # 补充令牌
        elapsed = now - last_ts
        tokens = min(float(rate), tokens + elapsed * refill_rate)
        tokens -= 1.0

        if tokens < 0:
            # 计算需要等待的时间
            wait_time = abs(tokens) / refill_rate
            self._buckets[key] = (now, 0.0)
            return False

        self._buckets[key] = (now, tokens)

        # 定期清理过期桶
        if len(self._buckets) > 10000:
            threshold = now - 120  # 2分钟未活跃清理
            self._buckets = {
                k: v for k, v in self._buckets.items()
                if v[0] > threshold
            }

        return True


# ═══════════════════════════════════════════
# 日志中间件
# ═══════════════════════════════════════════

class LoggingMiddleware(BaseHTTPMiddleware):
    """结构化请求日志"""

    async def dispatch(self, request: Request, call_next):
        start = time.monotonic()

        response: Response = await call_next(request)

        elapsed = (time.monotonic() - start) * 1000
        logger.info(
            f"{request.method} {request.url.path} "
            f"→ {response.status_code} "
            f"({elapsed:.0f}ms)",
            request_id=request_id_var.get(),
        )

        return response
