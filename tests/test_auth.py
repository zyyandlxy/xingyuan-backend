"""
认证与静态资源访问控制测试
覆盖: 服务级 API Key 启用后，静态资源放行、受保护端点拦截、JWT/X-API-Key 通行
"""

from __future__ import annotations

import pytest


@pytest.fixture
def auth_client(tmp_path, monkeypatch):
    """启用服务级 API Key 认证的测试客户端"""
    db_path = tmp_path / "auth_test.db"
    monkeypatch.setenv("ZHIPUAI_API_KEY", "test-api-key")
    monkeypatch.setenv("DATABASE_PATH", str(db_path))
    monkeypatch.setenv("RATE_LIMIT_PER_MINUTE", "0")
    monkeypatch.setenv("SERVICE_API_KEY", "test-service-key-1234567890")

    from agent.config import reload_settings
    reload_settings()

    from main import app
    from fastapi.testclient import TestClient
    with TestClient(app) as c:
        yield c


def test_auth_enabled_flag(auth_client):
    """认证启用后 /health 上报 auth_enabled=true"""
    r = auth_client.get("/health")
    assert r.status_code == 200
    assert r.json()["auth_enabled"] is True


def test_static_assets_public_when_auth_enabled(auth_client):
    """根路径挂载的 PWA 静态资源必须放行（否则前端完全无法加载）"""
    for path in (
        "/css/app.css",
        "/js/app.js",
        "/manifest.json",
        "/icon-192.png",
        "/sw.js",
    ):
        r = auth_client.get(path)
        assert r.status_code == 200, f"{path} 应放行，实际 {r.status_code}"


def test_root_page_public(auth_client):
    """首页 HTML 放行"""
    r = auth_client.get("/")
    assert r.status_code == 200
    assert "星媛" in r.text


def test_conversations_requires_auth(auth_client):
    """游客访问对话列表 → 401"""
    r = auth_client.get("/conversations")
    assert r.status_code == 401


def test_iteration_requires_auth(auth_client):
    """游客访问迭代/记忆端点 → 401"""
    r = auth_client.get("/iteration/memory")
    assert r.status_code == 401


def test_x_api_key_grants_access(auth_client):
    """服务级 X-API-Key 可访问受保护端点"""
    r = auth_client.get(
        "/conversations", headers={"X-API-Key": "test-service-key-1234567890"}
    )
    assert r.status_code == 200


def test_wrong_api_key_rejected(auth_client):
    """错误的 API Key → 401"""
    r = auth_client.get("/conversations", headers={"X-API-Key": "wrong-key"})
    assert r.status_code == 401


def test_register_login_jwt_flow(auth_client):
    """注册 → 登录 → JWT 访问受保护端点"""
    reg = auth_client.post(
        "/auth/register", json={"username": "alice", "password": "Secret123"}
    )
    assert reg.status_code == 200
    token = reg.json()["data"]["token"]
    assert token

    r = auth_client.get(
        "/conversations", headers={"Authorization": f"Bearer {token}"}
    )
    assert r.status_code == 200
    assert r.json()["total"] == 0

    login = auth_client.post(
        "/auth/login", json={"username": "alice", "password": "Secret123"}
    )
    assert login.status_code == 200
    assert login.json()["data"]["token"]


def test_invalid_jwt_rejected(auth_client):
    """伪造 JWT → 401"""
    r = auth_client.get(
        "/conversations", headers={"Authorization": "Bearer not-a-real-token"}
    )
    assert r.status_code == 401
