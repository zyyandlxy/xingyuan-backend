"""
核心聊天引擎
封装智谱 AI GLM 调用：非流式、流式、工具调用循环
"""

from __future__ import annotations

import json
import re
import uuid
from collections.abc import AsyncGenerator
from typing import Any

from loguru import logger
from zhipuai import ZhipuAI

from agent.config import get_settings
from agent.models import (
    ChatRequest,
    ChatResponse,
    Message,
    StreamChunk,
    TokenUsage,
    Tool,
)
from agent.vision import strip_image_markers


# ═══════════════════════════════════════════
# 无符号输出（用户需求：回复不带任何符号，只保留标点）
# 双保险：① system 提示词约束（OUTPUT_RULE）② 后端 sanitize_reply 兜底
# ═══════════════════════════════════════════

OUTPUT_RULE = (
    "回复规则：请不要使用任何 emoji 表情、Markdown 标记（如 # * - > _ 等）、"
    "以及任何特殊装饰符号或图形字符。回复内容只使用文字、数字与标点符号，保持简洁自然。"
)

# 保留：汉字、CJK 标点、全角标点、破折号/省略号/弯引号、英文字母数字、英文标点、空白
# 其余一律删除（emoji、Markdown 标记、装饰字符、数学符号、箭头等）
_NO_SYMBOL_RE = re.compile(
    r"[^一-鿿"          # CJK 统一汉字
    r"　-〿"           # CJK 标点
    r"＀-￯"           # 全角标点
    r"–—‘’“”…"  # – — ‘ ’ “ ” …
    r"A-Za-z0-9"
    r"\s"
    r".,!?;:'\"()"
    r"]"
)


def sanitize_reply(text: str) -> str:
    """去掉回复中除标点外的所有符号（emoji / Markdown 标记 / 装饰字符），保留文字、数字、标点与空白。"""
    if not text:
        return text
    return _NO_SYMBOL_RE.sub("", text)


# ═══════════════════════════════════════════
# 工具调用循环
# ═══════════════════════════════════════════

async def _execute_tool_loop(
    client: ZhipuAI,
    model: str,
    messages: list[dict[str, Any]],
    tools: list[dict[str, Any]],
    max_rounds: int,
) -> tuple[str, TokenUsage, list[dict[str, Any]]]:
    """
    执行工具调用循环：发送消息 → 模型请求工具 → 返回工具结果 → 重复
    直到模型不再请求工具或达到最大轮次
    """
    total_usage = TokenUsage()
    all_tool_calls: list[dict[str, Any]] = []
    final_content = ""

    for _round in range(max_rounds):
        response = client.chat.completions.create(
            model=model,
            messages=messages,
            tools=tools,
            temperature=get_settings().zhipuai_temperature,
            max_tokens=get_settings().zhipuai_max_tokens,
        )

        choice = response.choices[0]
        finish_reason = choice.finish_reason

        # 累积 token 用量
        if response.usage:
            total_usage.prompt_tokens += response.usage.prompt_tokens
            total_usage.completion_tokens += response.usage.completion_tokens
            total_usage.total_tokens += response.usage.total_tokens

        msg = choice.message

        # 模型返回了工具调用请求
        if msg.tool_calls and finish_reason == "tool_calls":
            tool_calls_data = [
                {
                    "id": tc.id,
                    "type": tc.type,
                    "function": {
                        "name": tc.function.name,
                        "arguments": tc.function.arguments,
                    },
                }
                for tc in msg.tool_calls
            ]
            all_tool_calls.extend(tool_calls_data)

            # 把助手消息加入历史
            messages.append({
                "role": "assistant",
                "content": msg.content or "",
                "tool_calls": [
                    {
                        "id": tc.id,
                        "type": tc.type,
                        "function": {
                            "name": tc.function.name,
                            "arguments": tc.function.arguments,
                        },
                    }
                    for tc in msg.tool_calls
                ],
            })

            # 为每个工具调用返回占位结果（后续可由用户实现真正的工具执行器）
            for tc in msg.tool_calls:
                tool_result = json.dumps(
                    {
                        "tool": tc.function.name,
                        "arguments": tc.function.arguments,
                        "result": f"[工具 {tc.function.name} 执行结果占位]",
                    },
                    ensure_ascii=False,
                )
                messages.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": tool_result,
                })

            continue  # 继续循环，让模型处理工具结果

        # 正常文本回复
        final_content = msg.content or ""
        break

    else:
        # 达到最大轮次仍未结束
        logger.warning(f"工具调用达到最大轮次 {max_rounds}，强制终止")
        final_content = (
            final_content or "已达到工具调用最大轮次，请简化请求后重试。"
        )

    return final_content, total_usage, all_tool_calls


# ═══════════════════════════════════════════
# 非流式聊天
# ═══════════════════════════════════════════

async def chat(
    request: ChatRequest,
    conversation_id: str,
    store_messages_cb=None,
) -> ChatResponse:
    """
    执行一次非流式聊天。

    Args:
        request: 聊天请求
        conversation_id: 关联的对话 ID
        store_messages_cb: 可选回调，用于持久化用户消息和 AI 回复
    """
    settings = get_settings()
    client = _get_client()

    model = request.model or settings.zhipuai_model

    # 构建消息列表
    messages = _build_messages(request)

    # 构建工具定义
    tools = None
    if request.tools:
        tools = [
            {
                "type": "function",
                "function": {
                    "name": t.function.name,
                    "description": t.function.description,
                    "parameters": t.function.parameters.model_dump(),
                },
            }
            for t in request.tools
        ]

    # 持久化用户消息
    if store_messages_cb:
        for msg in request.messages:
            if msg.role != "system":
                await store_messages_cb(conversation_id, msg)

    try:
        # 带工具调用
        if tools:
            content, usage, tool_calls = await _execute_tool_loop(
                client, model, messages, tools, settings.max_tool_rounds
            )
        else:
            # 纯文本聊天
            response = client.chat.completions.create(
                model=model,
                messages=messages,
                temperature=request.temperature
                if request.temperature is not None
                else settings.zhipuai_temperature,
                max_tokens=request.max_tokens or settings.zhipuai_max_tokens,
            )

            choice = response.choices[0]
            content = choice.message.content or ""
            usage = TokenUsage(
                prompt_tokens=response.usage.prompt_tokens if response.usage else 0,
                completion_tokens=response.usage.completion_tokens
                if response.usage
                else 0,
                total_tokens=response.usage.total_tokens if response.usage else 0,
            )
            tool_calls = []

        # 无符号输出兜底：去掉 emoji / Markdown 标记 / 装饰字符（仅保留文字数字标点）
        content = sanitize_reply(content)

        # 持久化 AI 回复
        if store_messages_cb and content:
            await store_messages_cb(
                conversation_id,
                Message(role="assistant", content=content),
            )

        return ChatResponse(
            conversation_id=conversation_id,
            content=content,
            model=model,
            usage=usage,
            tool_calls=tool_calls,
        )

    except Exception as e:
        logger.error(f"聊天请求失败: {e}")
        raise


# ═══════════════════════════════════════════
# 流式聊天
# ═══════════════════════════════════════════

async def chat_stream(
    request: ChatRequest,
    conversation_id: str,
) -> AsyncGenerator[StreamChunk, None]:
    """执行流式聊天，逐 token 产出 StreamChunk"""
    settings = get_settings()
    client = _get_client()

    model = request.model or settings.zhipuai_model
    messages = _build_messages(request)

    stream_id = f"stream_{uuid.uuid4().hex[:12]}"

    try:
        response = client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=request.temperature
            if request.temperature is not None
            else settings.zhipuai_temperature,
            max_tokens=request.max_tokens or settings.zhipuai_max_tokens,
            stream=True,
        )

        accumulated = ""
        for chunk in response:
            delta = chunk.choices[0].delta
            # 无符号输出兜底：逐 chunk 清洗，前端实时显示与最终持久化均为干净内容
            content = sanitize_reply(delta.content or "")

            if content:
                accumulated += content

            yield StreamChunk(
                id=stream_id,
                conversation_id=conversation_id,
                delta=content,
                finish_reason=chunk.choices[0].finish_reason,
                usage=TokenUsage(
                    prompt_tokens=chunk.usage.prompt_tokens
                    if chunk.usage
                    else 0,
                    completion_tokens=chunk.usage.completion_tokens
                    if chunk.usage
                    else 0,
                    total_tokens=chunk.usage.total_tokens
                    if chunk.usage
                    else 0,
                ),
            )

        logger.info(
            f"流式完成 conv={conversation_id} "
            f"chars={len(accumulated)}"
        )

    except Exception as e:
        logger.error(f"流式聊天失败: {e}")
        yield StreamChunk(
            id=stream_id,
            conversation_id=conversation_id,
            delta="",
            finish_reason="error",
        )
        raise


# ═══════════════════════════════════════════
# 内部辅助
# ═══════════════════════════════════════════

_client_pool: ZhipuAI | None = None


def _get_client() -> ZhipuAI:
    """获取智谱 AI 客户端（单例）"""
    global _client_pool
    if _client_pool is None:
        settings = get_settings()
        _client_pool = ZhipuAI(api_key=settings.zhipuai_api_key)
    return _client_pool


def _build_messages(request: ChatRequest) -> list[dict[str, Any]]:
    """构建发送给 GLM 的消息列表"""
    messages: list[dict[str, Any]] = []

    # 无符号输出规则始终注入（覆盖 guest / 无 persona 等所有路径），persona 跟在规则之后
    sys_parts = [OUTPUT_RULE]
    if request.system_prompt:
        sys_parts.append(request.system_prompt)
    messages.append({"role": "system", "content": "\n".join(sys_parts)})

    for msg in request.messages:
        # 防御：剥离历史消息里可能残留的 [图片]...[/图片] 标记，杜绝 base64 进 LLM 上下文
        m: dict[str, Any] = {"role": msg.role, "content": strip_image_markers(msg.content)}
        if msg.name:
            m["name"] = msg.name
        if msg.tool_call_id:
            m["tool_call_id"] = msg.tool_call_id
        messages.append(m)

    return messages
