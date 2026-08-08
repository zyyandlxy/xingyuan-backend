"""个人资料 agent_avatar（智能体头像）集成测试

需要 DATABASE_URL 指向独立的测试库（如 xingyuan_test），切勿指向生产 neondb。
同时覆盖 init_user_tables 的 ALTER TABLE ADD COLUMN IF NOT EXISTS 兼容逻辑：
测试库 users 表已存在且无 agent_avatar 列，注册/登录能正常触发建列并返回字段。
"""

from __future__ import annotations

import pytest


def test_register_returns_agent_avatar(client):
    """注册用户默认 agent_avatar 为空字符串"""
    r = client.post(
        "/auth/register",
        json={"username": "aa_user1", "password": "TestPass123"},
    )
    assert r.status_code == 200
    assert r.json()["data"]["agent_avatar"] == ""


def test_update_profile_agent_avatar(client, auth_headers):
    """PUT /auth/me 单独更新 agent_avatar 生效，且昵称同时更新"""
    data_uri = "data:image/jpeg;base64,/9j/4AAQSkZJRg=="
    r = client.put(
        "/auth/me",
        headers=auth_headers,
        json={"nickname": "小明", "agent_avatar": data_uri},
    )
    assert r.status_code == 200
    d = r.json()["data"]
    assert d["agent_avatar"] == data_uri
    assert d["nickname"] == "小明"


def test_get_me_returns_agent_avatar(client, auth_headers):
    """设置后 GET /auth/me 返回 agent_avatar"""
    data_uri = "data:image/png;base64,iVBORw0KGgo="
    client.put("/auth/me", headers=auth_headers, json={"agent_avatar": data_uri})
    r = client.get("/auth/me", headers=auth_headers)
    assert r.status_code == 200
    assert r.json()["data"]["agent_avatar"] == data_uri


def test_login_returns_agent_avatar(client):
    """登录返回 agent_avatar 字段（前端据此恢复智能体头像）"""
    reg = client.post(
        "/auth/register",
        json={"username": "aa_login", "password": "TestPass123"},
    )
    token = reg.json()["data"]["token"]
    data_uri = "data:image/png;base64,iVBORw0KGgo="
    client.put(
        "/auth/me",
        headers={"Authorization": f"Bearer {token}"},
        json={"agent_avatar": data_uri},
    )
    login = client.post(
        "/auth/login", json={"username": "aa_login", "password": "TestPass123"}
    )
    assert login.status_code == 200
    assert login.json()["data"]["agent_avatar"] == data_uri
