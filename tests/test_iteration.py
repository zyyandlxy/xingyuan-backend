"""
自我迭代路由测试 — 反馈、记忆、个性化
覆盖: 游客拒绝（401）、登录用户提交反馈/管理记忆/获取 persona
"""

from __future__ import annotations


def test_guest_rejected_on_feedback(client):
    """游客提交反馈 → 401（迭代端点仅限登录用户）"""
    r = client.post("/iteration/feedback", json={"rating": 5, "comment": "不错"})
    assert r.status_code == 401
    assert "登录" in r.json()["detail"]


def test_guest_rejected_on_memory(client):
    """游客访问记忆 → 401"""
    r = client.get("/iteration/memory")
    assert r.status_code == 401


def test_guest_rejected_on_persona(client):
    """游客获取个性化 → 401"""
    r = client.get("/iteration/persona")
    assert r.status_code == 401


def test_feedback_success(client, auth_headers):
    """登录用户提交反馈 → 成功"""
    r = client.post(
        "/iteration/feedback",
        json={"rating": 5, "comment": "很满意"},
        headers=auth_headers,
    )
    assert r.status_code == 200
    assert r.json()["success"] is True


def test_feedback_rating_validation(client, auth_headers):
    """评分越界 → 422"""
    r = client.post(
        "/iteration/feedback",
        json={"rating": 9, "comment": "超出范围"},
        headers=auth_headers,
    )
    assert r.status_code == 422


def test_memory_crud(client, auth_headers):
    """登录用户：添加记忆 → 查询 → 删除 → 查询为空"""
    # 添加
    r = client.post(
        "/iteration/memory",
        json={"key": "name", "value": "小明", "category": "personal"},
        headers=auth_headers,
    )
    assert r.status_code == 200
    assert r.json()["success"] is True

    # 查询
    r = client.get("/iteration/memory", headers=auth_headers)
    assert r.status_code == 200
    data = r.json()
    assert data["success"] is True
    assert any(m["key"] == "name" for m in data["data"])

    # 按分类过滤
    r = client.get("/iteration/memory?category=personal", headers=auth_headers)
    assert r.status_code == 200
    assert any(m["key"] == "name" for m in r.json()["data"])

    r = client.get("/iteration/memory?category=work", headers=auth_headers)
    assert not any(m["key"] == "name" for m in r.json()["data"])

    # 删除
    r = client.delete("/iteration/memory/name", headers=auth_headers)
    assert r.status_code == 200

    r = client.get("/iteration/memory", headers=auth_headers)
    assert not any(m["key"] == "name" for m in r.json()["data"])


def test_persona_generation(client, auth_headers):
    """登录用户获取个性化提示词"""
    r = client.get("/iteration/persona", headers=auth_headers)
    assert r.status_code == 200
    data = r.json()
    assert data["success"] is True
    assert "persona" in data["data"]
    assert isinstance(data["data"]["persona"], str)
    assert data["data"]["persona"].strip(), "persona 不应为空"


def test_feedback_stats(client, auth_headers):
    """反馈统计：直接返回统计数据，字段完整"""
    r = client.get("/iteration/feedback", headers=auth_headers)
    assert r.status_code == 200
    data = r.json()
    assert "avg_rating" in data
    assert "total_feedback" in data
    assert isinstance(data["total_feedback"], int)
