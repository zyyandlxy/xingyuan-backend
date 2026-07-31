"""
聊天路由 — 需要 JWT 认证
POST /chat         — 非流式聊天
POST /chat/stream  — SSE 流式聊天
"""

from __future__ import annotations

import json
import traceback

from fastapi import APIRouter, Header, HTTPException
from loguru import logger
from sse_starlette.sse import EventSourceResponse

from agent.chat import chat, chat_stream
from agent.config import get_settings
from agent.exceptions import AppException, ProviderError, ProviderAuthError
from agent.middleware import request_id_var
from agent.models import ChatRequest, ChatResponse, ErrorResponse
from agent.iteration import generate_persona_prompt, init_iteration_tables, learn_from_message
from agent.store import get_store
from agent.users import verify_token

router = APIRouter()


def _get_user(authorization: str) -> dict:
    """从 Authorization Header 解析用户"""
    token = authorization.removeprefix("Bearer ").strip()
    if not token:
        raise HTTPException(status_code=401, detail="请先登录")
    payload = verify_token(token)
    if not payload:
        raise HTTPException(status_code=401, detail="Token 无效或已过期")
    return payload


async def _learn_and_personalize(request: ChatRequest, user_id: str):
    """自动学习 + 注入个性化提示词"""
    await init_iteration_tables()
    for msg in request.messages:
        if msg.role == "user" and len(msg.content) > 2:
            try:
                await learn_from_message(user_id, msg.content)
            except Exception as e:
                logger.warning(
                    f"学习失败 user={user_id}: {e}",
                    request_id=request_id_var.get(),
                )

    # 注入个性化提示词
    if not request.system_prompt:
        try:
            persona = await generate_persona_prompt(user_id)
            request.system_prompt = persona
        except Exception as e:
            logger.warning(
                f"生成 persona 失败 user={user_id}: {e}",
                request_id=request_id_var.get(),
            )


@router.post("", response_model=ChatResponse, summary="非流式聊天")
async def chat_endpoint(
    request: ChatRequest,
    authorization: str = Header(default=""),
):
    """发送消息，返回完整 AI 回复。需登录。"""
    user = _get_user(authorization)
    user_id = user["sub"]
    settings = get_settings()
    store = await get_store()

    await _learn_and_personalize(request, user_id)

    conv_id = request.conversation_id
    if not conv_id:
        conv_id = await store.create_conversation(
            model=request.model or settings.zhipuai_model,
            system_prompt=request.system_prompt,
            user_id=user_id,
        )

    async def save_msg(cid: str, msg):
        await store.add_message(cid, msg.role, msg.content,
                                name=msg.name, tool_call_id=msg.tool_call_id)

    try:
        for msg in request.messages:
            if msg.role != "system":
                await save_msg(conv_id, msg)

        response = await chat(request, conv_id)

        if response.content:
            await save_msg(conv_id, type("Msg", (), {
                "role": "assistant", "content": response.content,
                "name": None, "tool_call_id": None,
            })())

        return response

    except ProviderAuthError:
        raise HTTPException(status_code=502, detail="AI 服务认证失败，请联系管理员")
    except ProviderError as e:
        raise HTTPException(status_code=502, detail=str(e))
    except AppException as e:
        raise HTTPException(status_code=e.status_code, detail=str(e))
    except Exception as e:
        logger.error(f"聊天错误: {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail="服务内部错误")


@router.post("/stream", summary="流式聊天（SSE）")
async def chat_stream_endpoint(
    request: ChatRequest,
    authorization: str = Header(default=""),
):
    """流式聊天，需登录。"""
    user = _get_user(authorization)
    user_id = user["sub"]
    settings = get_settings()
    store = await get_store()

    await _learn_and_personalize(request, user_id)

    conv_id = request.conversation_id
    if not conv_id:
        conv_id = await store.create_conversation(
            model=request.model or settings.zhipuai_model,
            system_prompt=request.system_prompt,
            user_id=user_id,
        )

    # 先持久化用户消息
    for msg in request.messages:
        if msg.role != "system":
            await store.add_message(conv_id, msg.role, msg.content)

    async def event_generator():
        full_content = ""
        try:
            async for chunk in chat_stream(request, conv_id):
                full_content += chunk.delta
                yield {"event": "delta", "data": chunk.model_dump_json()}

            # 流正常结束，保存完整回复
            if full_content:
                await store.add_message(conv_id, "assistant", full_content)

            yield {"event": "done", "data": json.dumps({
                "conversation_id": conv_id, "total_chars": len(full_content),
            })}

        except Exception as e:
            logger.error(f"流式错误: {traceback.format_exc()}")
            # 连接断开时也保存已收到的部分内容
            if full_content:
                try:
                    await store.add_message(conv_id, "assistant", full_content + " [中断]")
                except Exception:
                    pass
            yield {"event": "error", "data": json.dumps({
                "error": "流式传输中断",
                "partial_chars": len(full_content),
                "code": "STREAM_ERROR",
            })}

    return EventSourceResponse(event_generator())
