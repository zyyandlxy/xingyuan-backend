"""
健康检查路由
"""

from __future__ import annotations

from fastapi import APIRouter

from agent.config import get_settings
from agent.store import get_store

router = APIRouter()


@router.get("/health", summary="健康检查")
async def health():
    """基础健康检查"""
    settings = get_settings()
    return {
        "status": "ok",
        "version": "2.7.0",
        "auth_enabled": settings.is_auth_enabled,
    }


@router.get("/health/ready", summary="就绪探测")
async def ready():
    """深度就绪检查（含数据库连通性）"""
    settings = get_settings()

    checks = {
        "api_key_configured": bool(settings.zhipuai_api_key),
        "database": "ok",
    }

    # 检查数据库
    try:
        store = await get_store()
        await store.list_conversations(page=1, page_size=1)
    except Exception:
        checks["database"] = "error"

    all_ok = all(v == "ok" or v is True for v in checks.values())
    status_code = 200 if all_ok else 503

    return {
        "status": "ready" if all_ok else "not_ready",
        "checks": checks,
    }
