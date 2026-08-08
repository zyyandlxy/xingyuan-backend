"""agent/vision 单元测试 — 智谱 GLM-4V 视觉适配器 + 内容视图纯函数

describe_images 的所有网络调用均用 fake httpx.AsyncClient 拦截，不发真实请求。
@no_db: 纯单元测试，不连数据库，跳过 _reset_test_db 的 TRUNCATE。
"""
from __future__ import annotations

import asyncio
import json

import pytest

pytestmark = pytest.mark.no_db

from agent.vision import (
    _is_valid_uri,
    compose_stored_content,
    describe_images,
    inject_vision_content,
    strip_image_markers,
)


# ═══════════════════════════════════════════
# 内容视图纯函数
# ═══════════════════════════════════════════

def test_compose_stored_content():
    """B 视图：text + 每张图一个 [图片]...[/图片] 标记"""
    assert compose_stored_content("hi", ["a", "b"]) == "hi[图片]a[/图片][图片]b[/图片]"
    assert compose_stored_content("", []) == ""
    assert compose_stored_content("看这个", ["data:image/jpeg;base64,AAA"]) == \
        "看这个[图片]data:image/jpeg;base64,AAA[/图片]"


def test_strip_image_markers():
    """防御剥离：任意文本中的 [图片]...[/图片] 全去掉"""
    assert strip_image_markers("hi[图片]data:image/jpeg;base64,AAA[/图片]xx") == "hixx"
    assert strip_image_markers("no markers") == "no markers"
    assert strip_image_markers("a[图片]b[/图片]c[图片]d[/图片]e") == "ace"


def test_inject_vision_content():
    """C 视图：text + 视觉描述（纯文本，无标记）"""
    assert inject_vision_content("hi", "一只猫") == "hi\n\n[图片内容] 一只猫"
    assert inject_vision_content("hi", "   ") == "hi"
    assert inject_vision_content("", "猫") == "\n\n[图片内容] 猫"


def test_is_valid_uri():
    """MIME 白名单 + base64 长度上限"""
    assert _is_valid_uri("data:image/jpeg;base64,/9j/4AAQ==")
    assert _is_valid_uri("data:image/png;base64,AAAA")
    assert _is_valid_uri("data:image/webp;base64,BBBB")
    assert _is_valid_uri("data:image/gif;base64,CCCC")
    assert not _is_valid_uri("data:text/plain;base64,xxx")
    assert not _is_valid_uri("http://evil/x.png")
    assert not _is_valid_uri("data:image/jpeg;base64," + "A" * (6 * 1024 * 1024 + 1))


# ═══════════════════════════════════════════
# describe_images — 多图一次调用 + 失败降级
# ═══════════════════════════════════════════

class _Settings:
    zhipuai_api_key = "zhipu-test-key"
    zhipu_vision_model = "glm-4v-flash"
    zhipu_vision_base_url = "https://open.bigmodel.cn/api/paas/v4"


class _FakeResp:
    status_code = 200
    text = '{"choices":[{"message":{"content":"图片里有只猫"}}]}'

    def json(self):
        return json.loads(self.text)


class _FakeClient:
    def __init__(self, *a, **k):
        self.resp = _FakeResp()
        self.exc = None
        self.kw = None

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def post(self, *a, **k):
        self.kw = k
        if self.exc:
            raise self.exc
        return self.resp


def _patch_http(monkeypatch, exc=None, status=None):
    fake = _FakeClient()
    fake.exc = exc
    if status is not None:
        fake.resp.status_code = status
    monkeypatch.setattr("agent.vision.httpx.AsyncClient", lambda *a, **k: fake)
    return fake


def _patch_settings(monkeypatch, key="zhipu-test-key"):
    s = _Settings()
    s.zhipuai_api_key = key
    monkeypatch.setattr("agent.vision.get_settings", lambda: s)


def test_describe_images_success(monkeypatch):
    """正常 200：返回视觉文字描述"""
    _patch_settings(monkeypatch)
    _patch_http(monkeypatch)
    out = asyncio.run(describe_images(["data:image/jpeg;base64,AAA"]))
    assert out == "图片里有只猫"


def test_describe_images_no_key(monkeypatch):
    """无 key：返回占位，不抛异常、不发请求"""
    _patch_settings(monkeypatch, key="")
    fake = _patch_http(monkeypatch)
    out = asyncio.run(describe_images(["data:image/jpeg;base64,AAA"]))
    assert "暂时无法解析" in out
    assert fake.kw is None  # 未发起请求


def test_describe_images_timeout(monkeypatch):
    """超时：返回占位，不中断聊天"""
    _patch_settings(monkeypatch)
    _patch_http(monkeypatch, exc=TimeoutError("boom"))
    out = asyncio.run(describe_images(["data:image/jpeg;base64,AAA"]))
    assert "暂时无法解析" in out


def test_describe_images_non_200(monkeypatch):
    """非 2xx：返回占位"""
    _patch_settings(monkeypatch)
    _patch_http(monkeypatch, status=500)
    out = asyncio.run(describe_images(["data:image/jpeg;base64,AAA"]))
    assert "暂时无法解析" in out


def test_describe_images_all_invalid(monkeypatch):
    """全部非法 URI：返回占位（不发请求）"""
    _patch_settings(monkeypatch)
    fake = _patch_http(monkeypatch)
    out = asyncio.run(describe_images(["data:text/plain;base64,xxx"]))
    assert "暂时无法解析" in out
    assert fake.kw is None


def test_describe_images_multi_images_one_call(monkeypatch):
    """多图一次调用：content 数组含多个 image_url part，且带用户文本上下文"""
    _patch_settings(monkeypatch)
    fake = _patch_http(monkeypatch)
    asyncio.run(describe_images(
        ["data:image/jpeg;base64,AAA", "data:image/png;base64,BBB"], "看猫"))
    payload = fake.kw["json"]
    parts = payload["messages"][0]["content"]
    urls = [p["image_url"]["url"] for p in parts if p["type"] == "image_url"]
    assert urls == ["data:image/jpeg;base64,AAA", "data:image/png;base64,BBB"]
    assert "看猫" in parts[0]["text"]
    assert payload["model"] == "glm-4v-flash"
