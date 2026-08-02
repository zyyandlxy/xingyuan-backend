"""健康检查端点测试"""


def test_health(client):
    """测试基础健康检查"""
    resp = client.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert "version" in data
    assert "auth_enabled" in data


def test_ready(client):
    """测试就绪检查"""
    resp = client.get("/health/ready")
    assert resp.status_code in (200, 503)
    data = resp.json()
    assert "checks" in data
