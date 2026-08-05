"""
对话管理路由测试
覆盖: 创建/列表/详情/删除 CRUD、游客 ID 隔离、软删除、权限校验
"""

from __future__ import annotations

import pytest


@pytest.fixture
def guest_headers():
    return {"X-Guest-ID": "guest-crud-001"}


def test_create_conversation(client, guest_headers):
    """游客创建对话 → 返回元信息"""
    r = client.post("/conversations", json={"title": "我的新对话"}, headers=guest_headers)
    assert r.status_code == 201
    data = r.json()
    assert data["id"].startswith("conv_")
    assert data["title"] == "我的新对话"
    assert data["message_count"] == 0


def test_list_conversations_empty(client, guest_headers):
    """新游客对话列表为空"""
    r = client.get("/conversations", headers=guest_headers)
    assert r.status_code == 200
    data = r.json()
    assert data["items"] == []
    assert data["total"] == 0


def test_conversation_isolation_between_guests(client):
    """不同游客 ID 之间数据隔离（互不可见）"""
    a = {"X-Guest-ID": "guest-iso-a"}
    b = {"X-Guest-ID": "guest-iso-b"}

    ca = client.post("/conversations", json={"title": "A 的对话"}, headers=a).json()
    cb = client.post("/conversations", json={"title": "B 的对话"}, headers=b).json()

    list_a = client.get("/conversations", headers=a).json()
    list_b = client.get("/conversations", headers=b).json()

    assert len(list_a["items"]) == 1
    assert len(list_b["items"]) == 1
    assert list_a["items"][0]["id"] == ca["id"]
    assert list_b["items"][0]["id"] == cb["id"]

    # A 不能读 B 的对话
    r = client.get(f"/conversations/{cb['id']}", headers=a)
    assert r.status_code == 404


def test_delete_conversation(client, guest_headers):
    """删除对话 → 列表为空 + 详情 404"""
    conv = client.post("/conversations", json={"title": "待删除"}, headers=guest_headers).json()

    r = client.delete(f"/conversations/{conv['id']}", headers=guest_headers)
    assert r.status_code == 204

    detail = client.get(f"/conversations/{conv['id']}", headers=guest_headers)
    assert detail.status_code == 404

    listing = client.get("/conversations", headers=guest_headers).json()
    assert listing["total"] == 0


def test_delete_nonexistent_returns_404(client, guest_headers):
    """删除不存在的对话 → 404"""
    r = client.delete("/conversations/conv_doesnotexist", headers=guest_headers)
    assert r.status_code == 404


def test_guest_creates_own_conversation_each_time(client):
    """无 X-Guest-ID 时生成临时游客（每次不同），对话不混用"""
    r1 = client.post("/conversations", json={"title": "临时 1"})
    r2 = client.post("/conversations", json={"title": "临时 2"})
    assert r1.status_code == 201
    assert r2.status_code == 201
    assert r1.json()["id"] != r2.json()["id"]


def test_user_scoped_conversations(client, auth_headers):
    """登录用户：对话按用户隔离，JWT 用户与游客不相见"""
    # 游客建一个
    client.post("/conversations", json={"title": "游客的"}, headers={"X-Guest-ID": "guest-user-1"})

    # 登录用户建一个
    r = client.post("/conversations", json={"title": "用户的"}, headers=auth_headers)
    assert r.status_code == 201
    user_conv = r.json()

    listing = client.get("/conversations", headers=auth_headers).json()
    assert listing["total"] == 1
    assert listing["items"][0]["id"] == user_conv["id"]
    assert listing["items"][0]["title"] == "用户的"
