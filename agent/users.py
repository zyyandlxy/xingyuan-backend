"""
用户系统 — 注册、登录、JWT 认证、登录记录
"""

from __future__ import annotations

import hashlib
import time
import uuid
from datetime import datetime, timezone

import bcrypt
import jwt

from agent.store import _execute, _fetchone, _fetchall

# ═══════════════════════════════════════════
# JWT 配置
# ═══════════════════════════════════════════

JWT_SECRET = "xingyuan-jwt-secret-v1"  # 生产环境从环境变量读取
JWT_EXPIRE_SECONDS = 7 * 24 * 3600  # Token 7 天过期


def create_token(user_id: str, username: str) -> str:
    """生成 JWT Token"""
    payload = {
        "sub": user_id,
        "usr": username,
        "iat": int(time.time()),
        "exp": int(time.time()) + JWT_EXPIRE_SECONDS,
    }
    return jwt.encode(payload, JWT_SECRET, algorithm="HS256")


def verify_token(token: str) -> dict | None:
    """验证 JWT Token，返回 payload 或 None"""
    try:
        return jwt.decode(token, JWT_SECRET, algorithms=["HS256"])
    except jwt.PyJWTError:
        return None


# ═══════════════════════════════════════════
# 用户表初始化
# ═══════════════════════════════════════════

USER_TABLES_SQL = """
CREATE TABLE IF NOT EXISTS users (
    id          TEXT PRIMARY KEY,
    username    TEXT NOT NULL UNIQUE,
    password    TEXT NOT NULL,
    nickname    TEXT DEFAULT '',
    avatar      TEXT DEFAULT '✨',
    created_at  TEXT NOT NULL,
    last_login  TEXT
);

CREATE TABLE IF NOT EXISTS login_history (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id     TEXT NOT NULL,
    ip          TEXT DEFAULT '',
    device      TEXT DEFAULT '',
    login_at    TEXT NOT NULL,
    FOREIGN KEY (user_id) REFERENCES users(id)
);

CREATE INDEX IF NOT EXISTS idx_login_user ON login_history(user_id, login_at DESC);
"""


# ═══════════════════════════════════════════
# 用户操作
# ═══════════════════════════════════════════

async def init_user_tables():
    """初始化用户相关表"""
    from agent.store import get_store
    store = await get_store()
    db = await store._get_conn()
    await db.executescript(USER_TABLES_SQL)
    await db.commit()


async def register_user(username: str, password: str, nickname: str = "") -> dict:
    """
    注册新用户
    返回: {id, username, nickname, token}
    """
    from agent.store import get_store
    store = await get_store()
    db = await store._get_conn()

    # 检查用户名是否已存在
    row = await _fetchone(db, "SELECT id FROM users WHERE username = ?", (username,))
    if row:
        raise ValueError("用户名已被注册")

    # 密码哈希
    pwd_hash = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()

    user_id = f"u_{uuid.uuid4().hex[:16]}"
    now = datetime.now(timezone.utc).isoformat()

    await db.execute(
        "INSERT INTO users (id, username, password, nickname, created_at, last_login) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (user_id, username, pwd_hash, nickname or username, now, now),
    )
    await db.commit()

    token = create_token(user_id, username)
    return {
        "id": user_id,
        "username": username,
        "nickname": nickname or username,
        "token": token,
    }


async def login_user(username: str, password: str, ip: str = "", device: str = "") -> dict:
    """
    用户登录
    返回: {id, username, nickname, token, login_count}
    """
    from agent.store import get_store
    store = await get_store()
    db = await store._get_conn()

    row = await _fetchone(
        db, "SELECT * FROM users WHERE username = ?", (username,)
    )
    if not row:
        raise ValueError("用户名或密码错误")

    pwd_hash = row["password"]
    if not bcrypt.checkpw(password.encode(), pwd_hash.encode()):
        raise ValueError("用户名或密码错误")

    user_id = row["id"]
    now = datetime.now(timezone.utc).isoformat()

    # 更新最后登录时间
    await db.execute("UPDATE users SET last_login = ? WHERE id = ?", (now, user_id))

    # 记录登录历史
    await db.execute(
        "INSERT INTO login_history (user_id, ip, device, login_at) VALUES (?, ?, ?, ?)",
        (user_id, ip, device, now),
    )

    # 查询登录次数
    count_row = await _fetchone(
        db, "SELECT COUNT(*) as cnt FROM login_history WHERE user_id = ?",
        (user_id,),
    )
    login_count = count_row["cnt"] if count_row else 0

    await db.commit()

    token = create_token(user_id, row["username"])
    return {
        "id": user_id,
        "username": row["username"],
        "nickname": row["nickname"] or row["username"],
        "token": token,
        "login_count": login_count,
        "last_login": row["last_login"],
    }


async def get_user_by_id(user_id: str) -> dict | None:
    """根据 ID 获取用户信息"""
    from agent.store import get_store
    store = await get_store()
    db = await store._get_conn()

    row = await _fetchone(db, "SELECT * FROM users WHERE id = ?", (user_id,))
    if not row:
        return None
    return {
        "id": row["id"],
        "username": row["username"],
        "nickname": row["nickname"],
        "avatar": row["avatar"],
        "created_at": row["created_at"],
        "last_login": row["last_login"],
    }


async def get_login_history(user_id: str, limit: int = 20) -> list[dict]:
    """获取用户登录历史"""
    from agent.store import get_store
    store = await get_store()
    db = await store._get_conn()

    rows = await _fetchall(
        db,
        "SELECT * FROM login_history WHERE user_id = ? ORDER BY login_at DESC LIMIT ?",
        (user_id, limit),
    )
    return [
        {"ip": r["ip"], "device": r["device"], "login_at": r["login_at"]}
        for r in rows
    ]


async def get_total_users() -> int:
    """获取总注册用户数"""
    from agent.store import get_store
    store = await get_store()
    db = await store._get_conn()

    row = await _fetchone(db, "SELECT COUNT(*) as cnt FROM users")
    return row["cnt"] if row else 0
