"""
认证路由 — 注册、登录、用户信息
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Header, Request
from pydantic import BaseModel, Field

from agent.users import (
    get_login_history,
    get_user_by_id,
    init_user_tables,
    login_user,
    register_user,
    verify_token,
)

router = APIRouter()


# ═══════════════════════════════════════════
# 请求模型
# ═══════════════════════════════════════════

class RegisterRequest(BaseModel):
    username: str = Field(..., min_length=2, max_length=30, description="用户名")
    password: str = Field(..., min_length=6, max_length=100, description="密码")
    nickname: str = Field(default="", max_length=30, description="昵称")


class LoginRequest(BaseModel):
    username: str = Field(..., description="用户名")
    password: str = Field(..., description="密码")


# ═══════════════════════════════════════════
# 路由
# ═══════════════════════════════════════════

@router.post("/register", summary="用户注册")
async def register(body: RegisterRequest, request: Request):
    """注册新用户，返回 Token"""
    await init_user_tables()
    try:
        result = await register_user(
            username=body.username.strip(),
            password=body.password,
            nickname=body.nickname.strip() or body.username.strip(),
        )
        return {
            "success": True,
            "message": "注册成功",
            "data": result,
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/login", summary="用户登录")
async def login(body: LoginRequest, request: Request):
    """用户登录，返回 Token 和用户信息"""
    await init_user_tables()
    # 获取客户端信息
    ip = request.headers.get("X-Forwarded-For", request.client.host if request.client else "unknown")
    device = request.headers.get("User-Agent", "unknown")

    try:
        result = await login_user(
            username=body.username.strip(),
            password=body.password,
            ip=ip,
            device=device[:200],
        )
        return {
            "success": True,
            "message": "登录成功",
            "data": result,
        }
    except ValueError as e:
        raise HTTPException(status_code=401, detail=str(e))


@router.get("/me", summary="当前用户信息")
async def current_user(authorization: str = Header(default="")):
    """获取当前登录用户信息"""
    token = authorization.removeprefix("Bearer ").strip()
    if not token:
        raise HTTPException(status_code=401, detail="未登录")

    payload = verify_token(token)
    if not payload:
        raise HTTPException(status_code=401, detail="Token 无效或已过期")

    user = await get_user_by_id(payload["sub"])
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")

    return {"success": True, "data": user}


@router.get("/login-history", summary="登录历史")
async def login_history(authorization: str = Header(default="")):
    """获取当前用户的登录历史"""
    token = authorization.removeprefix("Bearer ").strip()
    if not token:
        raise HTTPException(status_code=401, detail="未登录")

    payload = verify_token(token)
    if not payload:
        raise HTTPException(status_code=401, detail="Token 无效或已过期")

    history = await get_login_history(payload["sub"])
    return {"success": True, "data": history}
