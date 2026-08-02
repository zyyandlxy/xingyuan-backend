"""
星媛 Agent — 生产级 AI 微服务入口
FastAPI + 智谱 AI GLM + SSE 流式 + 工具调用 + PWA
"""

from __future__ import annotations

import os
import sys
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from loguru import logger

from agent.config import get_settings
from agent.exceptions import AppException
from agent.middleware import (
    AuthMiddleware,
    LoggingMiddleware,
    RateLimitMiddleware,
    RequestIDMiddleware,
    SecurityHeadersMiddleware,
    TimingMiddleware,
    request_id_var,
)
from agent.models import ErrorResponse
from agent.store import close_store, get_store
from routers import auth, chat, conversations, health, iteration


# ═══════════════════════════════════════════
# 日志配置
# ═══════════════════════════════════════════

def setup_logging():
    """配置 loguru 结构化日志"""
    logger.remove()
    settings = get_settings()

    # 控制台输出（彩色）
    logger.add(
        sys.stderr,
        format=(
            "<green>{time:HH:mm:ss}</green> | "
            "<level>{level: <8}</level> | "
            "<cyan>{extra[request_id]: <14}</cyan> | "
            "<level>{message}</level>"
        ),
        level=settings.log_level,
        colorize=True,
    )

    # 文件输出
    log_path = Path(settings.log_file)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    logger.add(
        str(log_path),
        format="{time:YYYY-MM-DD HH:mm:ss.SSS} | {level: <8} | "
               "{extra[request_id]: <14} | {message}",
        rotation="00:00",
        retention="30 days",
        level="INFO",
        encoding="utf-8",
    )

    # 为所有日志绑定默认 request_id
    logger.configure(extra={"request_id": ""})


# ═══════════════════════════════════════════
# 应用生命周期
# ═══════════════════════════════════════════

@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用启动/关闭时的资源管理"""
    settings = get_settings()
    setup_logging()

    logger.bind(request_id="startup").info(
        f"星媛 Agent 启动中... model={settings.zhipuai_model}"
    )

    # 初始化数据库
    await get_store()
    from agent.users import init_user_tables
    from agent.iteration import init_iteration_tables
    await init_user_tables()
    await init_iteration_tables()

    # WAL checkpoint — 每次启动合并 WAL 防止膨胀
    import aiosqlite
    async with aiosqlite.connect(settings.database_path) as wal_db:
        await wal_db.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    logger.bind(request_id="startup").info("数据库初始化完成 (WAL checkpoint 已执行)")

    yield

    # 清理资源
    await close_store()
    logger.bind(request_id="shutdown").info("星媛 Agent 已关闭")


# ═══════════════════════════════════════════
# 应用工厂
# ═══════════════════════════════════════════

def create_app() -> FastAPI:
    settings = get_settings()

    app = FastAPI(
        title="星媛 Agent API",
        version="2.5.0",
        description="星媛 AI Agent — 智谱 GLM、流式 SSE、工具调用、自我迭代、PWA",
        lifespan=lifespan,
        docs_url="/docs",
        redoc_url="/redoc",
    )

    # ── 安全中间件（最外层） ─────────────────
    app.add_middleware(SecurityHeadersMiddleware)

    # ── 业务中间件（由外到内） ───────────────
    app.add_middleware(RequestIDMiddleware)
    app.add_middleware(TimingMiddleware)
    app.add_middleware(LoggingMiddleware)
    app.add_middleware(AuthMiddleware)
    app.add_middleware(RateLimitMiddleware)

    # CORS：生产环境应限制具体域名
    cors_origins = settings.cors_origin_list
    if "*" in cors_origins:
        # 开发模式：允许所有来源，但禁用 credentials（符合 CORS 规范）
        cors_origins = ["*"]
        allow_creds = False
    else:
        allow_creds = True

    app.add_middleware(
        CORSMiddleware,
        allow_origins=cors_origins,
        allow_credentials=allow_creds,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["X-Request-ID", "X-Process-Time", "X-RateLimit-Remaining"],
    )

    # ── 路由注册 ────────────────────────────
    app.include_router(health.router, tags=["Health"])
    app.include_router(auth.router, prefix="/auth", tags=["Auth"])
    app.include_router(chat.router, prefix="/chat", tags=["Chat"])
    app.include_router(
        conversations.router, prefix="/conversations", tags=["Conversations"]
    )
    app.include_router(
        iteration.router, prefix="/iteration", tags=["Self-Iteration"]
    )

    # ── 静态文件 (Web UI + PWA) ────────────
    static_dir = Path(__file__).parent / "static"
    if static_dir.exists():
        app.mount("/", StaticFiles(directory=str(static_dir), html=True), name="static")

    # ── 全局异常处理 ────────────────────────
    @app.exception_handler(AppException)
    async def handle_app_exception(request: Request, exc: AppException):
        return JSONResponse(
            status_code=exc.status_code,
            content=ErrorResponse(
                error=str(exc),
                detail=exc.detail,
                code=exc.error_code,
                request_id=request_id_var.get(),
            ).model_dump(),
        )

    @app.exception_handler(Exception)
    async def handle_general_exception(request: Request, exc: Exception):
        is_debug = settings.debug or os.getenv("ENV", "") == "development"
        logger.error(f"未处理异常: {exc}", request_id=request_id_var.get())
        return JSONResponse(
            status_code=500,
            content=ErrorResponse(
                error="服务内部错误",
                detail=str(exc) if is_debug else "请稍后重试或联系管理员",
                code="INTERNAL_ERROR",
                request_id=request_id_var.get(),
            ).model_dump(),
        )

    return app


# ═══════════════════════════════════════════
# 应用实例
# ═══════════════════════════════════════════

app = create_app()

# 直接运行
if __name__ == "__main__":
    import uvicorn

    settings = get_settings()
    uvicorn.run(
        "main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.debug,
        log_level=settings.log_level.lower(),
    )
