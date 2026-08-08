"""
聊天路由 — 需要 JWT 认证
POST /chat         — 非流式聊天
POST /chat/stream  — SSE 流式聊天
"""

from __future__ import annotations

import asyncio
import json
import traceback

from fastapi import APIRouter, Header, HTTPException
from loguru import logger
from sse_starlette.sse import EventSourceResponse

import uuid

from agent.chat import chat, chat_stream
from agent.config import get_settings
from agent.exceptions import AppException, ProviderError, ProviderAuthError, ProviderTimeoutError
from agent.middleware import request_id_var
from agent.models import ChatRequest, ChatResponse, ErrorResponse, Message
from agent.iteration import generate_persona_prompt, init_iteration_tables, learn_from_message, record_question
from agent.store import get_store
from agent.users import verify_token
from agent.vision import compose_stored_content, describe_images, inject_vision_content

router = APIRouter()


def _get_user(authorization: str, x_guest_id: str = "") -> dict:
    """从 Authorization Header 解析用户；无 token 则使用 X-Guest-ID 或生成随机游客 ID"""
    token = authorization.removeprefix("Bearer ").strip()
    if not token:
        guest_id = x_guest_id.strip() or f"guest_{uuid.uuid4().hex[:12]}"
        return {"sub": guest_id, "usr": "guest", "is_guest": True}
    payload = verify_token(token)
    if not payload:
        guest_id = x_guest_id.strip() or f"guest_{uuid.uuid4().hex[:12]}"
        return {"sub": guest_id, "usr": "guest", "is_guest": True}
    payload["is_guest"] = False
    return payload

# ═══════════════════════════════════════════
# ZhipuAI 错误 → 应用异常映射
# ═══════════════════════════════════════════

def _classify_provider_error(e: Exception) -> AppException:
    """将 zhipuai SDK 异常映射为应用层异常"""
    etype = type(e).__name__
    emsg = str(e).lower()

    if "timeout" in etype.lower() or "timeout" in emsg:
        return ProviderTimeoutError("AI 服务响应超时，请稍后重试")
    if "auth" in etype.lower() or "authentication" in etype.lower() or "unauthorized" in emsg:
        return ProviderAuthError("AI 服务认证失败，请联系管理员")
    if "flowexceed" in etype.lower() or "rate" in emsg or "quota" in emsg:
        return ProviderError("AI 服务流量超限，请稍后重试")
    return ProviderError("AI 服务暂时不可用，请稍后重试")


async def _learn_and_personalize(request: ChatRequest, user_id: str, is_guest: bool = False):
    """自动学习 + 注入个性化提示词（游客跳过）"""
    if is_guest:
        return
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


async def _prepare_for_llm(request: ChatRequest) -> ChatRequest:
    """有 images 时：智谱视觉转文字描述 → 深拷贝注入文本；无 images 返回原 request。

    返回的 request 仅供 chat()/chat_stream() 使用（C 视图）；
    持久化、学习、计数仍走原 request 的纯文本（A 视图）与 images 字段（B 视图）。
    """
    if not request.images:
        return request
    last_user = next((m for m in reversed(request.messages) if m.role == "user"), None)
    desc = await describe_images(request.images, last_user.content if last_user else "")
    llm = request.model_copy(deep=True)
    target = next((m for m in reversed(llm.messages) if m.role == "user"), None)
    if target and desc:
        target.content = inject_vision_content(target.content, desc)
    return llm


@router.post("", response_model=ChatResponse, summary="非流式聊天")
async def chat_endpoint(
    request: ChatRequest,
    authorization: str = Header(default=""),
    x_guest_id: str = Header(default="", alias="X-Guest-ID"),
):
    """发送消息，返回完整 AI 回复。需登录。"""
    user = _get_user(authorization, x_guest_id)
    user_id = user["sub"]
    is_guest = user.get("is_guest", False)
    settings = get_settings()
    store = await get_store()

    await _learn_and_personalize(request, user_id, is_guest)

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

    llm_request = await _prepare_for_llm(request)

    # 先持久化用户消息（末条用户消息若有图片，附加 [图片] 标记供历史回放）
    last_user_msg = next((m for m in reversed(request.messages) if m.role == "user"), None)
    for msg in request.messages:
        if msg.role != "system":
            content = (compose_stored_content(msg.content, request.images)
                       if (request.images and msg is last_user_msg) else msg.content)
            await store.add_message(conv_id, msg.role, content,
                                    name=msg.name, tool_call_id=msg.tool_call_id)

    # 高频提问统计：只统计本轮最后一条用户消息（避免重算历史）
    if not is_guest and last_user_msg:
        try:
            await record_question(user_id, last_user_msg.content)
        except Exception:
            pass

    try:
        response = await chat(llm_request, conv_id)

        if response.content:
            await save_msg(conv_id, Message(role="assistant", content=response.content))

        return response

    except ProviderAuthError:
        raise HTTPException(status_code=502, detail="AI 服务认证失败，请联系管理员")
    except ProviderTimeoutError:
        raise HTTPException(status_code=504, detail="AI 服务响应超时，请稍后重试")
    except ProviderError as e:
        raise HTTPException(status_code=502, detail=str(e))
    except AppException as e:
        raise HTTPException(status_code=e.status_code, detail=str(e))
    except Exception as e:
        classified = _classify_provider_error(e)
        raise HTTPException(status_code=classified.status_code, detail=str(classified.detail or str(classified)))


@router.post("/stream", summary="流式聊天（SSE）")
async def chat_stream_endpoint(
    request: ChatRequest,
    authorization: str = Header(default=""),
    x_guest_id: str = Header(default="", alias="X-Guest-ID"),
):
    """流式聊天，需登录。"""
    user = _get_user(authorization, x_guest_id)
    user_id = user["sub"]
    is_guest = user.get("is_guest", False)
    settings = get_settings()
    store = await get_store()

    await _learn_and_personalize(request, user_id, is_guest)

    conv_id = request.conversation_id
    if not conv_id:
        conv_id = await store.create_conversation(
            model=request.model or settings.zhipuai_model,
            system_prompt=request.system_prompt,
            user_id=user_id,
        )

    # 有图片时提前转描述（在 event_generator 之前 await，闭包捕获注入结果）
    llm_request = await _prepare_for_llm(request)

    # 先持久化用户消息（末条用户消息若有图片，附加 [图片] 标记供历史回放）
    last_user_msg = next((m for m in reversed(request.messages) if m.role == "user"), None)
    for msg in request.messages:
        if msg.role != "system":
            content = (compose_stored_content(msg.content, request.images)
                       if (request.images and msg is last_user_msg) else msg.content)
            await store.add_message(conv_id, msg.role, content,
                                    name=msg.name, tool_call_id=msg.tool_call_id)

    # 高频提问统计：只统计本轮最后一条用户消息；流式用后台任务，不拖慢首字
    if not is_guest and last_user_msg:
        try:
            asyncio.create_task(record_question(user_id, last_user_msg.content))
        except Exception:
            pass

    async def event_generator():
        full_content = ""
        try:
            async for chunk in chat_stream(llm_request, conv_id):
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
            classified = _classify_provider_error(e)
            # 连接断开时也保存已收到的部分内容
            if full_content:
                try:
                    await store.add_message(conv_id, "assistant", full_content + " [中断]")
                except Exception:
                    pass
            yield {"event": "error", "data": json.dumps({
                "error": str(classified.detail or str(classified)),
                "code": classified.error_code or "PROVIDER_ERROR",
                "partial_chars": len(full_content),
            })}

    return EventSourceResponse(event_generator())
