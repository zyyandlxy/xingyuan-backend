"""「无符号输出」单元测试 —— 纯逻辑，不连接数据库（@pytest.mark.no_db）"""

from __future__ import annotations

import pytest

from agent.chat import OUTPUT_RULE, sanitize_reply
from agent.models import ChatRequest, Message


@pytest.mark.no_db
def test_sanitize_reply_strips_symbols():
    """去掉 emoji / Markdown 标记 / 装饰字符"""
    assert sanitize_reply("你好！🌟 这是测试 #1 *重点* 🎉") == "你好！ 这是测试 1 重点 "
    assert sanitize_reply("🎉🎊🥳") == ""
    assert sanitize_reply("好的，我这就处理。-- 稍等") == "好的，我这就处理。 稍等"


@pytest.mark.no_db
def test_sanitize_reply_keeps_punctuation_and_text():
    """保留文字、数字、中英文标点"""
    assert sanitize_reply("你，好。！？「」（）——……") == "你，好。！？「」（）——……"
    assert sanitize_reply("第1章 完成任务") == "第1章 完成任务"
    assert sanitize_reply("3:00 见") == "3:00 见"
    assert sanitize_reply("Hello, world! It's fine.") == "Hello, world! It's fine."
    assert sanitize_reply("（重要）【备注】") == "（重要）【备注】"


@pytest.mark.no_db
def test_sanitize_reply_empty():
    assert sanitize_reply("") == ""


@pytest.mark.no_db
def test_build_messages_injects_output_rule():
    """所有路径（含无 persona 的 guest）都注入无符号输出规则"""
    from agent.chat import _build_messages
    req = ChatRequest(messages=[Message(role="user", content="你好")])
    msgs = _build_messages(req)
    assert msgs[0]["role"] == "system"
    assert OUTPUT_RULE in msgs[0]["content"]


@pytest.mark.no_db
def test_build_messages_appends_persona_after_rule():
    """带 persona 时，规则在前、persona 在后"""
    from agent.chat import _build_messages
    req = ChatRequest(
        messages=[Message(role="user", content="你好")],
        system_prompt="你是星媛。",
    )
    msgs = _build_messages(req)
    sys_content = msgs[0]["content"]
    assert OUTPUT_RULE in sys_content
    assert sys_content.endswith("你是星媛。")


# ── chat() / chat_stream() 的 sanitize 集成（mock 智谱客户端，不真实调用）──

from types import SimpleNamespace


def _fake_client(monkeypatch, non_stream_resp=None, stream_chunks=None):
    """构造 mock 客户端：非流式返回 fixed 响应，流式返回 chunks 序列"""
    import agent.chat as chat_mod

    class _FakeResp:
        def __init__(self, content):
            self.choices = [SimpleNamespace(
                message=SimpleNamespace(content=content), finish_reason="stop")]
            self.usage = SimpleNamespace(prompt_tokens=1, completion_tokens=1, total_tokens=2)

    class _FakeChunk:
        def __init__(self, content, finish_reason=None):
            self.choices = [SimpleNamespace(
                delta=SimpleNamespace(content=content), finish_reason=finish_reason)]
            self.usage = SimpleNamespace(prompt_tokens=1, completion_tokens=1, total_tokens=2)

    class _FakeClient:
        def __init__(self):
            self.chat = SimpleNamespace(
                completions=SimpleNamespace(
                    create=lambda **kw: (
                        _FakeResp(non_stream_resp) if not kw.get("stream")
                        else iter([_FakeChunk(c, fr) for c, fr in stream_chunks or []])
                    )
                )
            )

    monkeypatch.setattr(chat_mod, "_get_client", lambda: _FakeClient())
    return chat_mod


@pytest.mark.no_db
def test_chat_non_stream_sanitizes_content(monkeypatch):
    """非流式 chat() 返回的 content 已去掉符号"""
    import asyncio

    chat_mod = _fake_client(monkeypatch, non_stream_resp="好的🌟 马上处理 🎉")
    resp = asyncio.run(chat_mod.chat(
        ChatRequest(messages=[Message(role="user", content="你好")]),
        conversation_id="conv_test",
    ))
    assert resp.content == "好的 马上处理 "
    assert "🌟" not in resp.content and "🎉" not in resp.content


@pytest.mark.no_db
def test_chat_stream_sanitizes_each_chunk(monkeypatch):
    """流式 chat_stream() 每个 delta 都经 sanitize（前端实时显示干净）"""
    chat_mod = _fake_client(
        monkeypatch,
        stream_chunks=[
            ("好的🌟", None),
            ("，马上处理🎉", None),
            ("！", "stop"),
        ],
    )
    import asyncio

    async def collect():
        chunks = []
        async for c in chat_mod.chat_stream(
            ChatRequest(messages=[Message(role="user", content="你好")]),
            conversation_id="conv_test",
        ):
            chunks.append(c.delta)
        return chunks

    deltas = asyncio.run(collect())
    assert deltas == ["好的", "，马上处理", "！"]
    assert "".join(deltas) == "好的，马上处理！"
