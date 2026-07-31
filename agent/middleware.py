"""
中间件层
请求ID注入、请求计时、API Key 认证、IP 限流、CSP 安全头
"""

from __future__ import annotations

import time
import uuid
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

# 无需服务级 API Key 认证的路径
API_KEY_WHITELIST = {
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

# 完全跳过限流的路径（健康检查、静态文件、文档）
RATE_LIMIT_WHITELIST = {
    "/health",
    "/health/ready",
    "/docs",
    "/openapi.json",
    "/redoc",
    "/favicon.ico",
    "/",
}

# Auth 端点专用限流：每分钟 5 次（防暴力破解）
AUTH_RATE_LIMIT = 5


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
# Content Security Policy 中间件
# ═══════════════════════════════════════════

class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """添加安全相关的 HTTP 响应头"""

    async def dispatch(self, request: Request, call_next):
        response: Response = await call_next(request)

        # CSP: 允许同源资源 + inline style/script（PWA 需要）
        csp = (
            "default-src 'self'; "
            "script-src 'self' 'unsafe-inline'; "
            "style-src 'self' 'unsafe-inline'; "
            "img-src 'self' data:; "
            "connect-src 'self' https:; "
            "font-src 'self'; "
            "object-src 'none'; "
            "base-uri 'self'; "
            "form-action 'self'"
        )
        response.headers["Content-Security-Policy"] = csp
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"

        return response


# ═══════════════════════════════════════════
# API Key 认证中间件
# ═══════════════════════════════════════════

class AuthMiddleware(BaseHTTPMiddleware):
    """X-API-Key 认证中间件（服务级别，区别于用户 JWT）"""

    async def dispatch(self, request: Request, call_next):
        settings = get_settings()

        # 认证未启用或路径在白名单中
        if not settings.is_auth_enabled:
            return await call_next(request)

        # 检查路径是否在白名单
        path = request.url.path.rstrip("/") or "/"
        if path in API_KEY_WHITELIST or path.startswith("/static") or path.startswith("/auth/"):
            return await call_next(request)

        api_key = request.headers.get("X-API-Key") or request.headers.get(
            "Authorization", ""
        ).removeprefix("Bearer ")

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

class RateLimitMiddleware:
    """基于 IP 的令牌桶限流（纯 ASGI 中间件）。Auth 端点有独立配额"""

    def __init__(self, app):
        self.app = app
        self._buckets: dict[str, tuple[float, float]] = {}

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        path = scope.get("path", "/").rstrip("/") or "/"

        # 白名单路径不限流
        if path in RATE_LIMIT_WHITELIST:
            await self.app(scope, receive, send)
            return

        # Auth 端点始终强制限流，其他端点遵循全局设置
        settings = get_settings()
        is_auth_path = path.startswith("/auth/")
        if not is_auth_path and settings.rate_limit_per_minute <= 0:
            await self.app(scope, receive, send)
            return

        rate = AUTH_RATE_LIMIT if is_auth_path else settings.rate_limit_per_minute

        # 获取客户端 IP
        fwd = next(
            (h[1] for h in scope.get("headers", []) if h[0] == b"x-forwarded-for"),
            b"",
        )
        client_ip = fwd.decode().split(",")[0].strip() if fwd else ""
        if not client_ip:
            real_ip = next(
                (h[1] for h in scope.get("headers", []) if h[0] == b"x-real-ip"),
                b"",
            )
            client_ip = real_ip.decode() if real_ip else ""
        if not client_ip:
            client = scope.get("client")
            client_ip = client[0] if client else "unknown"

        if not self._consume(client_ip, rate):
            rid = request_id_var.get()
            logger.info(
                f"RateLimit BLOCKED path={path} ip={client_ip} rate={rate}",
                request_id=rid,
            )
            response = JSONResponse(
                status_code=429,
                content=ErrorResponse(
                    error="请求过于频繁",
                    detail=f"Limit: {rate}/min",
                    code="RATE_LIMIT_EXCEEDED",
                    request_id=rid,
                ).model_dump(),
                headers={"Retry-After": "60"},
            )
            await response(scope, receive, send)
            return

        await self.app(scope, receive, send)

    def _consume(self, key: str, rate: int) -> bool:
        """令牌桶消费，返回是否允许"""
        now = time.monotonic()
        refill_rate = rate / 60.0

        last_ts, tokens = self._buckets.get(key, (now, float(rate)))

        elapsed = now - last_ts
        new_tokens = min(float(rate), tokens + elapsed * refill_rate)
        if new_tokens < 1.0:
            self._buckets[key] = (now, new_tokens)
            return False

        new_tokens -= 1.0
        self._buckets[key] = (now, new_tokens)

        if len(self._buckets) > 10000:
            threshold = now - 120
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
