"""测试配置和共享 Fixture"""

from __future__ import annotations

import os
import uuid
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


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
        database_path=":memory:",
    )


@pytest.fixture
def client(tmp_path, monkeypatch):
    """FastAPI 测试客户端，使用临时目录"""
    db_path = tmp_path / "test.db"

    monkeypatch.setenv("ZHIPUAI_API_KEY", "test-api-key")
    monkeypatch.setenv("DATABASE_PATH", str(db_path))
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
