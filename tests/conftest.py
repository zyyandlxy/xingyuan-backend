"""测试配置和共享 Fixture"""

from __future__ import annotations

import os
import uuid
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


def _test_database_url() -> str:
    """返回 Neon 测试库连接串；未设置 DATABASE_URL 则跳过数据库相关测试。

    注意：请务必指向独立的 Neon 测试库（如 xingyuan_test），不要用生产库！
    """
    url = os.environ.get("DATABASE_URL", "").strip()
    if not url:
        pytest.skip(
            "DATABASE_URL 未设置：请用独立的 Neon 测试库连接串设置环境变量后重跑"
        )
    return url


@pytest.fixture(autouse=True)
def clean_env():
    """每个测试前清理环境变量"""
    old = os.environ.copy()
    os.environ["ZHIPUAI_API_KEY"] = "test-api-key"
    os.environ["SERVICE_API_KEY"] = ""  # 测试时不启用认证
    os.environ["RATE_LIMIT_PER_MINUTE"] = "0"  # 不限流
    os.environ["AUTH_RATE_LIMIT"] = "0"  # 测试不限认证限流
    yield
    os.environ.clear()
    os.environ.update(old)


@pytest.fixture
def settings():
    """获取测试配置"""
    from agent.config import Settings
    return Settings(
        zhipuai_api_key="test-api-key",
        service_api_key="",
        rate_limit_per_minute=0,
    )


@pytest.fixture(autouse=True)
def _reset_test_db():
    """跑测试前清空测试库中的业务表，避免用例间互相污染。

    仅在设置了 DATABASE_URL 时生效（未设置则数据库相关用例被 _test_database_url 跳过）。
    全新库尚未建表时忽略 UndefinedTableError——表会由首个 TestClient 的 lifespan 创建。
    """
    url = os.environ.get("DATABASE_URL", "").strip()
    if not url:
        return
    import asyncio
    import asyncpg
    from asyncpg.exceptions import UndefinedTableError

    async def _reset():
        conn = await asyncpg.connect(url)
        try:
            try:
                await conn.execute(
                    "TRUNCATE TABLE conversations, messages, users, login_history, "
                    "agent_memory, agent_feedback, agent_evolution RESTART IDENTITY CASCADE"
                )
            except UndefinedTableError:
                pass  # 全新库还没建表，交给 TestClient lifespan 创建
        finally:
            await conn.close()

    asyncio.run(_reset())


@pytest.fixture
def client(monkeypatch):
    """FastAPI 测试客户端，使用 Neon 测试数据库"""
    db_url = _test_database_url()

    monkeypatch.setenv("ZHIPUAI_API_KEY", "test-api-key")
    monkeypatch.setenv("DATABASE_URL", db_url)
    monkeypatch.setenv("RATE_LIMIT_PER_MINUTE", "0")
    monkeypatch.setenv("SERVICE_API_KEY", "")

    from agent.config import reload_settings
    reload_settings()

    from main import app
    with TestClient(app) as c:
        yield c


@pytest.fixture
def auth_headers(client):
    """注册测试用户并返回带 JWT 的 Authorization header"""
    name = f"t{uuid.uuid4().hex[:10]}"
    reg = client.post(
        "/auth/register",
        json={"username": name, "password": "TestPass123"},
    )
    token = reg.json()["data"]["token"]
    return {"Authorization": f"Bearer {token}"}
