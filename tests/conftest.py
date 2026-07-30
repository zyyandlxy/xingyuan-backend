"""测试配置和共享 Fixture"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient


@pytest.fixture(autouse=True)
def clean_env():
    """每个测试前清理环境变量"""
    old = os.environ.copy()
    # 设置测试环境
    os.environ["ZHIPUAI_API_KEY"] = "test-api-key"
    os.environ["SERVICE_API_KEY"] = ""  # 测试时不启用认证
    os.environ["RATE_LIMIT_PER_MINUTE"] = "0"  # 不限流
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
    # 使用临时目录存放数据库
    db_path = tmp_path / "test.db"

    from agent.config import get_settings

    # 在第一次导入前设置环境
    monkeypatch.setenv("ZHIPUAI_API_KEY", "test-api-key")
    monkeypatch.setenv("DATABASE_PATH", str(db_path))
    monkeypatch.setenv("RATE_LIMIT_PER_MINUTE", "0")
    monkeypatch.setenv("SERVICE_API_KEY", "")

    # 强制重新加载配置
    from agent.config import reload_settings
    reload_settings()

    from main import app
    with TestClient(app) as c:
        yield c
