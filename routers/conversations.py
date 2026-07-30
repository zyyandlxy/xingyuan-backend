"""
对话管理路由 — 需要 JWT 认证，用户隔离
"""

from __future__ import annotations

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel

from agent.config import get_settings
from agent.models import ConversationDetail, ConversationList, ConversationMeta
from agent.store import get_store
from agent.users import verify_token

router = APIRouter()


def _get_user_id(auth: str) -> str:
    token = auth.removeprefix("Bearer ").strip()
    if not token:
        raise HTTPException(status_code=401, detail="请先登录")
    payload = verify_token(token)
    if not payload:
        raise HTTPException(status_code=401, detail="Token 无效")
    return payload["sub"]


class CreateConvBody(BaseModel):
    title: str = "新对话"
    system_prompt: str | None = None


@router.post("", status_code=201, summary="创建对话")
async def create_conversation(
    body: CreateConvBody,
    authorization: str = Header(default=""),
):
    user_id = _get_user_id(authorization)
    store = await get_store()
    settings = get_settings()

    conv_id = await store.create_conversation(
        title=body.title,
        model=settings.zhipuai_model,
        system_prompt=body.system_prompt,
        user_id=user_id,
    )
    detail = await store.get_conversation(conv_id)
    if not detail:
        raise HTTPException(status_code=500, detail="创建失败")

    return ConversationMeta(
        id=detail.id, title=detail.title, model=detail.model,
        message_count=0, created_at=detail.created_at, updated_at=detail.updated_at,
    )


@router.get("", response_model=ConversationList, summary="对话列表")
async def list_conversations(
    page: int = 1, page_size: int = 30,
    authorization: str = Header(default=""),
):
    user_id = _get_user_id(authorization)
    store = await get_store()
    items, total = await store.list_conversations(user_id=user_id, page=page, page_size=page_size)
    return ConversationList(items=items, total=total, page=page, page_size=page_size)


@router.get("/{conv_id}", response_model=ConversationDetail, summary="对话详情")
async def get_conversation(
    conv_id: str,
    authorization: str = Header(default=""),
):
    _get_user_id(authorization)  # 验证登录
    store = await get_store()
    detail = await store.get_conversation(conv_id)
    if not detail:
        raise HTTPException(status_code=404, detail="对话不存在")
    return detail


@router.delete("/{conv_id}", status_code=204, summary="删除对话")
async def delete_conversation(
    conv_id: str,
    authorization: str = Header(default=""),
):
    _get_user_id(authorization)
    store = await get_store()
    deleted = await store.delete_conversation(conv_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="对话不存在")
