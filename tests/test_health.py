"""健康检查端点测试"""


def test_health(client):
    """测试基础健康检查"""
    resp = client.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert "version" in data
    assert "version_notes" in data  # 后端数据驱动：版本亮点文案随 /health 下发
    assert "auth_enabled" in data


def test_health_version_notes_match_version(client):
    """版本号与亮点文案必须成对存在（agent/version.py 唯一来源）"""
    from agent.version import APP_VERSION, VERSION_NOTES
    resp = client.get("/health")
    data = resp.json()
    assert data["version"] == APP_VERSION
    # 当前版本应有亮点文案（发布时补一条），供前端轮询展示
    assert data["version_notes"] == VERSION_NOTES.get(APP_VERSION, "")


def test_ready(client):
    """测试就绪检查"""
    resp = client.get("/health/ready")
    assert resp.status_code in (200, 503)
    data = resp.json()
    assert "checks" in data
