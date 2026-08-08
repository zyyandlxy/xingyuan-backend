"""
智谱 GLM-4V Vision 适配器 — 聊天图片 → 文字描述，供 LLM 使用

只依赖 get_settings() + httpx，不持有 LLM 或 DB 依赖。
任何失败（无 key / 超时 / 非 2xx / 解析错误）→ 返回占位描述，聊天永不中断。
复用 zhipuai_api_key（与主对话同一智谱账号）。

同一用户消息在三个消费者面前呈现三种形态：
  A. 原文      text（前端发来的纯文本）            → learn / record_question / 历史消息
  B. 存储      text + [图片]<dataURL>[/图片]...     → 持久化、历史回放
  C. LLM       text + [图片内容] <智谱视觉描述>     → chat() / chat_stream()
"""

from __future__ import annotations

import re

import httpx
from loguru import logger

from agent.config import get_settings

_IMG_RE = re.compile(r"^data:(image/(?:jpeg|png|webp|gif));base64,[A-Za-z0-9+/=]+$", re.DOTALL)
_ALLOWED_MIME = {"image/jpeg", "image/png", "image/webp", "image/gif"}
_MAX_BASE64_LEN = 6 * 1024 * 1024   # 单张 base64 上限（压缩后通常 ~100-400KB）
_MAX_IMAGES = 9                     # 单条消息最多图片数（与 models.ChatRequest 一致）
_TIMEOUT = 45.0


def _is_valid_uri(uri: str) -> bool:
    """校验图片 data URI：MIME 白名单 + base64 长度上限"""
    return bool(_IMG_RE.match(uri)) and len(uri) <= _MAX_BASE64_LEN


def compose_stored_content(text: str, images: list[str]) -> str:
    """B 视图：text + 每张图一个 [图片]...[/图片] 标记，用于持久化"""
    return text + "".join(f"[图片]{u}[/图片]" for u in images)


def strip_image_markers(content: str) -> str:
    """防御：从任意文本剥离 [图片]...[/图片] 标记"""
    return re.sub(r"\[图片\].*?\[/图片\]", "", content, flags=re.DOTALL)


def inject_vision_content(text: str, description: str) -> str:
    """C 视图：把视觉描述追加到文本后（纯文本，无标记）"""
    desc = (description or "").strip()
    if not desc:
        return text
    return f"{text}\n\n[图片内容] {desc}"


async def describe_images(images: list[str], user_text: str = "") -> str:
    """多图一次调用智谱 GLM-4V 视觉，返回合并后的文字描述。

    任何失败 → 占位描述，不抛异常。复用 zhipuai_api_key。
    """
    valid = [u for u in images if _is_valid_uri(u)]
    placeholder = f"（用户发送了 {len(images)} 张图片，但图片内容暂时无法解析）"
    if not valid:
        return placeholder

    settings = get_settings()
    if not settings.zhipuai_api_key:
        logger.warning("ZHIPUAI_API_KEY 未配置，图片识别降级为占位描述")
        return placeholder

    if user_text and user_text.strip():
        prompt = (
            f"用户消息：{user_text[:500]}\n"
            "请结合上面这条消息，用中文描述下面这些图片的内容，"
            "简洁但具体（主体、场景、关键细节、文字信息）。"
        )
    else:
        prompt = "请用中文描述下面这些图片的内容，简洁但具体（主体、场景、关键细节、文字信息）。"

    payload = {
        "model": settings.zhipu_vision_model,
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    *[
                        {"type": "image_url", "image_url": {"url": u}}
                        for u in valid[:_MAX_IMAGES]
                    ],
                ],
            }
        ],
        "max_tokens": 1024,  # glm-4v-flash 的硬性上限 1024
    }

    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.post(
                f"{settings.zhipu_vision_base_url}/chat/completions",
                headers={
                    "Authorization": f"Bearer {settings.zhipuai_api_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
            )
        if resp.status_code == 200:
            data = resp.json()
            content = data["choices"][0]["message"]["content"]
            if isinstance(content, list):  # 兼容 content 为数组的方言
                content = " ".join(
                    part.get("text", "") for part in content if isinstance(part, dict)
                )
            if content and str(content).strip():
                return str(content).strip()
        logger.warning(f"智谱视觉返回 {resp.status_code}: {resp.text[:200]}")
    except Exception as e:
        logger.warning(f"智谱视觉调用失败: {e}")

    return placeholder
