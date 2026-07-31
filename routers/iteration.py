"""
自我迭代路由 — 反馈、记忆管理、进化记录
"""

from __future__ import annotations

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, Field

from agent.iteration import (
    forget,
    generate_persona_prompt,
    get_feedback_stats,
    init_iteration_tables,
    recall,
    record_evolution,
    save_feedback,
)
from agent.users import verify_token

router = APIRouter()


def _get_user(auth: str) -> str:
    token = auth.removeprefix("Bearer ").strip()
    if not token:
        raise HTTPException(status_code=401, detail="请先登录")
    payload = verify_token(token)
    if not payload:
        raise HTTPException(status_code=401, detail="Token 无效")
    return payload["sub"]


class FeedbackBody(BaseModel):
    conv_id: str = ""
    rating: int = Field(..., ge=1, le=5, description="评分 1-5")
    comment: str = ""


class MemoryBody(BaseModel):
    key: str
    value: str
    category: str = "general"


@router.post("/feedback", summary="提交反馈")
async def submit_feedback(
    body: FeedbackBody,
    authorization: str = Header(default=""),
):
    """对 AI 回复评分（1-5），帮助星媛进化"""
    user_id = _get_user(authorization)
    await save_feedback(user_id, body.rating, body.conv_id, body.comment)

    # 如果评分很高或很低，记录进化事件
    if body.rating <= 2:
        await record_evolution(user_id, f"收到低评分 {body.rating}，需要改进")
    elif body.rating == 5:
        await record_evolution(user_id, f"收到满分评价！保持当前风格")

    return {"success": True, "message": "感谢反馈！星媛会继续进步"}


@router.get("/feedback", summary="反馈统计")
async def feedback_stats(authorization: str = Header(default="")):
    """获取当前用户的反馈统计"""
    user_id = _get_user(authorization)
    return await get_feedback_stats(user_id)


@router.get("/memory", summary="获取我的记忆")
async def get_memory(
    category: str = "",
    authorization: str = Header(default=""),
):
    """获取星媛学到的关于你的信息"""
    user_id = _get_user(authorization)
    await init_iteration_tables()
    cat = category if category else None
    memories = await recall(user_id, cat)
    return {"success": True, "data": memories, "total": len(memories)}


@router.post("/memory", summary="主动记忆")
async def add_memory(
    body: MemoryBody,
    authorization: str = Header(default=""),
):
    """主动告诉星媛记住某事"""
    user_id = _get_user(authorization)
    await init_iteration_tables()
    from agent.iteration import remember
    await remember(user_id, body.key, body.value, body.category, 0.9)
    return {"success": True, "message": "已记住！"}


@router.delete("/memory/{key}", summary="删除记忆")
async def delete_memory(
    key: str,
    authorization: str = Header(default=""),
):
    user_id = _get_user(authorization)
    await forget(user_id, key)
    return {"success": True, "message": "已遗忘"}


@router.get("/persona", summary="获取个性化提示词")
async def persona(authorization: str = Header(default="")):
    """获取星媛为你生成的个性化系统提示词"""
    user_id = _get_user(authorization)
    await init_iteration_tables()
    prompt = await generate_persona_prompt(user_id)
    return {"success": True, "data": {"persona": prompt}}
