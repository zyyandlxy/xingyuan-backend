"""
Pydantic 数据模型
定义所有 API 请求/响应、内部数据结构
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator


# ═══════════════════════════════════════════
# 消息模型
# ═══════════════════════════════════════════

class Message(BaseModel):
    """单条对话消息"""
    role: Literal["system", "user", "assistant", "tool"] = "user"
    content: str = Field(..., min_length=1, description="消息内容")
    name: str | None = Field(default=None, description="工具名称（tool 角色时使用）")
    tool_call_id: str | None = Field(default=None, description="工具调用 ID")

    model_config = {"extra": "allow"}


# ═══════════════════════════════════════════
# 工具定义模型
# ═══════════════════════════════════════════

class FunctionParameter(BaseModel):
    """函数参数定义"""
    type: str = "object"
    properties: dict[str, Any] = Field(default_factory=dict)
    required: list[str] = Field(default_factory=list)


class FunctionDef(BaseModel):
    """函数定义"""
    name: str = Field(..., description="函数名")
    description: str = Field(default="", description="函数描述")
    parameters: FunctionParameter = Field(default_factory=FunctionParameter)


class Tool(BaseModel):
    """工具定义"""
    type: Literal["function"] = "function"
    function: FunctionDef


# ═══════════════════════════════════════════
# 请求模型
# ═══════════════════════════════════════════

class ChatRequest(BaseModel):
    """聊天请求"""
    messages: list[Message] = Field(..., min_length=1, description="消息列表")
    model: str | None = Field(default=None, description="模型名，不填用默认")
    temperature: float | None = Field(
        default=None, ge=0.0, le=1.0, description="采样温度"
    )
    max_tokens: int | None = Field(
        default=None, ge=1, le=128000, description="最大输出 token"
    )
    tools: list[Tool] | None = Field(default=None, description="可用工具列表")
    stream: bool = Field(default=False, description="是否流式输出")
    conversation_id: str | None = Field(
        default=None, description="关联对话 ID，不填则创建新对话"
    )
    system_prompt: str | None = Field(
        default=None, description="系统提示词，会插入到消息列表最前"
    )
    images: list[str] | None = Field(
        default=None,
        description="用户消息附带的图片（base64 data URI 列表），仅用于持久化与视觉识别，不进入 LLM content",
    )

    @field_validator("images")
    @classmethod
    def check_images(cls, v: list[str] | None) -> list[str] | None:
        """校验图片数量上限"""
        if v and len(v) > 9:
            raise ValueError("最多同时发送 9 张图片")
        return v

    @field_validator("messages")
    @classmethod
    def check_roles(cls, v: list[Message]) -> list[Message]:
        """校验消息角色合法性"""
        for msg in v:
            if msg.role == "tool" and not msg.tool_call_id:
                raise ValueError("tool 消息必须提供 tool_call_id")
        return v


class CreateConversationRequest(BaseModel):
    """创建对话请求"""
    title: str | None = Field(default=None, description="对话标题")
    system_prompt: str | None = Field(default=None, description="系统提示词")


# ═══════════════════════════════════════════
# 响应模型
# ═══════════════════════════════════════════

class TokenUsage(BaseModel):
    """Token 用量"""
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0


class ChatResponse(BaseModel):
    """非流式聊天响应"""
    id: str = Field(default_factory=lambda: f"msg_{uuid.uuid4().hex[:12]}")
    conversation_id: str
    content: str
    model: str
    usage: TokenUsage = Field(default_factory=TokenUsage)
    tool_calls: list[dict[str, Any]] = Field(default_factory=list)
    created_at: str = Field(
        default_factory=lambda: datetime.now().isoformat()
    )


class StreamChunk(BaseModel):
    """流式输出的单个数据块（SSE 格式）"""
    id: str
    conversation_id: str
    delta: str = ""
    finish_reason: str | None = None
    usage: TokenUsage | None = None


class ConversationMeta(BaseModel):
    """对话元信息"""
    id: str
    title: str
    model: str
    message_count: int = 0
    created_at: str
    updated_at: str


class ConversationDetail(BaseModel):
    """对话详情（含消息列表）"""
    id: str
    title: str
    model: str
    messages: list[Message]
    created_at: str
    updated_at: str


class ConversationList(BaseModel):
    """对话列表（分页）"""
    items: list[ConversationMeta]
    total: int
    page: int
    page_size: int


# ═══════════════════════════════════════════
# 通用响应
# ═══════════════════════════════════════════

class ErrorResponse(BaseModel):
    """错误响应"""
    error: str
    detail: str | None = None
    code: str = "internal_error"
    request_id: str | None = None


class HealthResponse(BaseModel):
    """健康检查响应"""
    status: str = "ok"
    version: str = "1.0.0"
    model: str
    auth_enabled: bool
