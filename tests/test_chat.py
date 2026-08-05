"""
聊天路由测试 — 非流式 /chat 与流式 /chat/stream
覆盖: 正常回复、对话持久化、提供方超时/认证失败/未知错误分类、SSE 事件结构
所有 zhipuai 调用均被 mock，不发出真实请求
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import httpx
import pytest
from zhipuai.core._errors import (
    APIAuthenticationError,
    APIServerFlowExceedError,
    APITimeoutError,
)


def _make_plain_response(content: str = "你好，我是星媛"):
    """构造 zhipuai 非流式响应对象"""
    resp = MagicMock()
    resp.choices[0].message.content = content
    resp.choices[0].finish_reason = "stop"
    resp.usage.prompt_tokens = 10
    resp.usage.completion_tokens = 20
    resp.usage.total_tokens = 30
    return resp


def _make_stream_chunk(content: str, finish_reason=None):
    """构造 zhipuai 流式 chunk"""
    chunk = MagicMock()
    chunk.choices[0].delta.content = content
    chunk.choices[0].finish_reason = finish_reason
    chunk.usage = None
    return chunk


class _FakeStream:
    """可迭代 + close() 的 zhipuai 流式响应"""

    def __init__(self, chunks):
        self._it = iter(chunks)

    def __iter__(self):
        return self

    def __next__(self):
        return next(self._it)

    def close(self):
        self._closed = True


# ═══════════════════════════════════════════
# 非流式 /chat
# ═══════════════════════════════════════════

def test_chat_nonstream_success(client):
    """正常回复：返回内容 + 自动创建对话"""
    with patch("agent.chat._get_client") as mock_get:
        mock_get.return_value.chat.completions.create.return_value = (
            _make_plain_response("你好！")
        )
        r = client.post("/chat", json={"messages": [{"role": "user", "content": "在吗"}]})

    assert r.status_code == 200
    data = r.json()
    assert data["content"] == "你好！"
    assert data["conversation_id"].startswith("conv_")
    assert data["model"]
    assert data["usage"]["total_tokens"] == 30


def test_chat_nonstream_persists_messages(client):
    """回复后消息被持久化到对话详情（同一游客 ID 才可读回）"""
    headers = {"X-Guest-ID": "guest-persist-1"}
    with patch("agent.chat._get_client") as mock_get:
        mock_get.return_value.chat.completions.create.return_value = (
            _make_plain_response("好的")
        )
        r = client.post(
            "/chat",
            headers=headers,
            json={"messages": [{"role": "user", "content": "记一下"}]},
        )
    conv_id = r.json()["conversation_id"]

    detail = client.get(f"/conversations/{conv_id}", headers=headers)
    assert detail.status_code == 200
    roles = [m["role"] for m in detail.json()["messages"]]
    contents = [m["content"] for m in detail.json()["messages"]]
    assert "user" in roles and "assistant" in roles
    assert "记一下" in contents and "好的" in contents


def test_chat_nonstream_timeout_maps_504(client):
    """提供方超时 → 504，文案不泄露内部细节"""
    req = httpx.Request("POST", "http://test/chat")
    with patch("agent.chat._get_client") as mock_get:
        mock_get.return_value.chat.completions.create.side_effect = (
            APITimeoutError(request=req)
        )
        r = client.post("/chat", json={"messages": [{"role": "user", "content": "hi"}]})

    assert r.status_code == 504
    body = r.json()
    assert "超时" in body["detail"]
    assert "test-api-key" not in body["detail"]  # 脱敏


def test_chat_nonstream_auth_error_maps_502(client):
    """提供方认证失败 → 502"""
    req = httpx.Request("POST", "http://test/chat")
    resp = httpx.Response(401, request=req)
    with patch("agent.chat._get_client") as mock_get:
        mock_get.return_value.chat.completions.create.side_effect = (
            APIAuthenticationError("bad key", response=resp)
        )
        r = client.post("/chat", json={"messages": [{"role": "user", "content": "hi"}]})

    assert r.status_code == 502
    assert "认证失败" in r.json()["detail"]


def test_chat_nonstream_flow_exceed_maps_502(client):
    """提供方流量超限 → 502，独立文案"""
    req = httpx.Request("POST", "http://test/chat")
    resp = httpx.Response(429, request=req)
    with patch("agent.chat._get_client") as mock_get:
        mock_get.return_value.chat.completions.create.side_effect = (
            APIServerFlowExceedError("flow", response=resp)
        )
        r = client.post("/chat", json={"messages": [{"role": "user", "content": "hi"}]})

    assert r.status_code == 502
    assert "流量" in r.json()["detail"]


# ═══════════════════════════════════════════
# 流式 /chat/stream
# ═══════════════════════════════════════════

def test_chat_stream_success(client):
    """流式：SSE 逐 delta 输出 + done 事件携带 conversation_id"""
    stream = _FakeStream([
        _make_stream_chunk("你好"),
        _make_stream_chunk("，星媛"),
        _make_stream_chunk("！", finish_reason="stop"),
    ])
    with patch("agent.chat._get_client") as mock_get:
        mock_get.return_value.chat.completions.create.return_value = stream
        r = client.post("/chat/stream", json={
            "messages": [{"role": "user", "content": "你好"}],
        })

    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/event-stream")
    text = r.text
    assert "event: delta" in text
    assert '"delta": "你好"' in text or '"delta":"你好"' in text
    assert "event: done" in text
    assert "conversation_id" in text
    assert "event: error" not in text


def test_chat_stream_persists_full_reply(client):
    """流式结束后完整回复入库（不逐 token 入库）"""
    headers = {"X-Guest-ID": "guest-persist-2"}
    stream = _FakeStream([
        _make_stream_chunk("完整"),
        _make_stream_chunk("回复", finish_reason="stop"),
    ])
    with patch("agent.chat._get_client") as mock_get:
        mock_get.return_value.chat.completions.create.return_value = stream
        r = client.post(
            "/chat/stream",
            headers=headers,
            json={"messages": [{"role": "user", "content": "写一段"},
                               {"role": "assistant", "content": "ok"},
                               {"role": "user", "content": "继续"}],
            },
        )

    import re
    m = re.search(r'"conversation_id":\s*"([^"]+)"', r.text)
    assert m, "流式应返回 conversation_id"
    conv_id = m.group(1)

    detail = client.get(f"/conversations/{conv_id}", headers=headers).json()
    contents = [msg["content"] for msg in detail["messages"]]
    assert "完整回复" in contents
    assert not any("完整" in c and "回复" in c and c != "完整回复" for c in contents)


def test_chat_stream_timeout_emits_error_event(client):
    """流式超时 → SSE error 事件，code=PROVIDER_TIMEOUT，无内部细节"""
    req = httpx.Request("POST", "http://test/chat/stream")
    with patch("agent.chat._get_client") as mock_get:
        mock_get.return_value.chat.completions.create.side_effect = (
            APITimeoutError(request=req)
        )
        r = client.post("/chat/stream", json={
            "messages": [{"role": "user", "content": "hi"}],
        })

    assert r.status_code == 200  # SSE 以事件承载错误，而非 HTTP 错误
    text = r.text
    assert "event: error" in text
    assert "PROVIDER_TIMEOUT" in text
    assert "test-api-key" not in text


def test_chat_stream_generic_error_maps_provider_error(client):
    """未知异常 → error 事件 code=PROVIDER_ERROR（不泄露 traceback）"""
    with patch("agent.chat._get_client") as mock_get:
        mock_get.return_value.chat.completions.create.side_effect = (
            RuntimeError("connection pool exhausted")
        )
        r = client.post("/chat/stream", json={
            "messages": [{"role": "user", "content": "hi"}],
        })

    text = r.text
    assert "event: error" in text
    assert "PROVIDER_ERROR" in text
    assert "connection pool exhausted" not in text


def test_chat_stream_guest_id_respected(client):
    """两个不同 X-Guest-ID 的游客对话相互隔离"""
    with patch("agent.chat._get_client") as mock_get:
        mock_get.return_value.chat.completions.create.return_value = (
            _make_plain_response("你好")
        )
        r1 = client.post(
            "/chat",
            headers={"X-Guest-ID": "guest-aaa-111"},
            json={"messages": [{"role": "user", "content": "第一条"}]},
        )
        r2 = client.post(
            "/chat",
            headers={"X-Guest-ID": "guest-bbb-222"},
            json={"messages": [{"role": "user", "content": "第二条"}]},
        )
    c1 = r1.json()["conversation_id"]
    c2 = r2.json()["conversation_id"]
    assert c1 != c2

    # guest-a 只能看到自己的对话
    list_a = client.get("/conversations", headers={"X-Guest-ID": "guest-aaa-111"}).json()
    assert all(c["id"] == c1 for c in list_a["items"])
    assert list_a["total"] == 1
