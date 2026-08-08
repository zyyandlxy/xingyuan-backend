"""
用户系统 — 注册、登录、JWT 认证、登录记录
"""

from __future__ import annotations

import os
import time
import uuid
from datetime import datetime, timezone

import bcrypt
import jwt

from agent.store import _acquire, _execute, _fetchall, _fetchone, _tx

# ═══════════════════════════════════════════
# JWT 配置
# ═══════════════════════════════════════════

def _load_or_generate_jwt_secret() -> str:
    """从环境变量或持久化文件加载 JWT 密钥，不存在则随机生成。

    生产环境（Render）必须在环境变量配置固定的 JWT_SECRET，否则每次部署
    会重新生成密钥，导致所有已签发的 token 失效、用户需重新登录。
    """
    secret = os.getenv("JWT_SECRET", "")
    if secret:
        return secret
    secret_file = os.path.join(os.path.dirname(__file__), "..", "data", ".jwt_secret")
    try:
        with open(secret_file) as f:
            return f.read().strip()
    except FileNotFoundError:
        import secrets
        new_secret = secrets.token_hex(32)
        os.makedirs(os.path.dirname(secret_file), exist_ok=True)
        with open(secret_file, "w") as f:
            f.write(new_secret)
        return new_secret


JWT_SECRET = _load_or_generate_jwt_secret()
# 登录有效期 1 年 —— 用户只需登录一次，跨年不再要求重新登录
JWT_EXPIRE_SECONDS = 365 * 24 * 3600


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
    avatar      TEXT DEFAULT '',
    created_at  TEXT NOT NULL,
    last_login  TEXT
);

CREATE TABLE IF NOT EXISTS login_history (
    id          BIGSERIAL PRIMARY KEY,
    user_id     TEXT NOT NULL,
    ip          TEXT DEFAULT '',
    device      TEXT DEFAULT '',
    login_at    TEXT NOT NULL,
    FOREIGN KEY (user_id) REFERENCES users(id)
);

CREATE INDEX IF NOT EXISTS idx_login_user ON login_history(user_id, login_at DESC);
"""


# ═══════════════════════════════════════════
# 密码强度校验
# ═══════════════════════════════════════════

def validate_password_strength(password: str, username: str = "") -> str | None:
    """
    校验密码强度，返回 None 表示通过，否则返回错误信息。
    要求: 至少 8 位 + 包含字母和数字
    """
    if len(password) < 8:
        return "密码至少需要 8 位"
    if not any(c.isalpha() for c in password):
        return "密码需要包含至少一个字母"
    if not any(c.isdigit() for c in password):
        return "密码需要包含至少一个数字"
    if username and username.lower() in password.lower():
        return "密码不能包含用户名"
    return None


def validate_username(username: str) -> str | None:
    """校验用户名合法性"""
    if len(username) < 2 or len(username) > 30:
        return "用户名需要 2-30 个字符"
    if not all(c.isalnum() or c in '_-' for c in username):
        return "用户名只能包含字母、数字、下划线和连字符"
    return None


# ═══════════════════════════════════════════
# 用户操作
# ═══════════════════════════════════════════

_user_tables_ready = False


async def init_user_tables():
    """初始化用户相关表（DDL 只执行一次，后续调用直接跳过）"""
    global _user_tables_ready
    if _user_tables_ready:
        return
    from agent.store import get_store
    store = await get_store()
    async with _tx(store) as db:
        await db.execute(USER_TABLES_SQL)
    _user_tables_ready = True


async def register_user(username: str, password: str, nickname: str = "") -> dict:
    """
    注册新用户
    返回: {id, username, nickname, token}
    """
    from agent.store import get_store
    store = await get_store()

    # 用户名校验
    username = username.strip()
    if err := validate_username(username):
        raise ValueError(err)

    # 密码强度校验
    if err := validate_password_strength(password, username):
        raise ValueError(err)

    # 密码哈希
    pwd_hash = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()

    user_id = f"u_{uuid.uuid4().hex[:16]}"
    now = datetime.now(timezone.utc).isoformat()

    async with _tx(store) as db:
        # 检查用户名是否已存在（事务内检查-写入，防并发重复注册）
        row = await _fetchone(db, "SELECT id FROM users WHERE username = $1", (username,))
        if row:
            raise ValueError("用户名已被注册")

        await _execute(
            db,
            "INSERT INTO users (id, username, password, nickname, created_at, last_login) "
            "VALUES ($1, $2, $3, $4, $5, $6)",
            (user_id, username, pwd_hash, nickname or username, now, now),
        )

    token = create_token(user_id, username)
    return {
        "id": user_id,
        "username": username,
        "nickname": nickname or username,
        "avatar": "",
        "token": token,
    }


async def login_user(username: str, password: str, ip: str = "", device: str = "") -> dict:
    """
    用户登录
    返回: {id, username, nickname, token, login_count}
    """
    from agent.store import get_store
    store = await get_store()

    async with _tx(store) as db:
        row = await _fetchone(
            db, "SELECT * FROM users WHERE username = $1", (username,)
        )
        if not row:
            raise ValueError("用户名或密码错误")

        pwd_hash = row["password"]
        if not bcrypt.checkpw(password.encode(), pwd_hash.encode()):
            raise ValueError("用户名或密码错误")

        user_id = row["id"]
        now = datetime.now(timezone.utc).isoformat()

        # 更新最后登录时间
        await _execute(db, "UPDATE users SET last_login = $1 WHERE id = $2", (now, user_id))

        # 记录登录历史
        await _execute(
            db, "INSERT INTO login_history (user_id, ip, device, login_at) VALUES ($1, $2, $3, $4)",
            (user_id, ip, device, now),
        )

        # 查询登录次数
        count_row = await _fetchone(
            db, "SELECT COUNT(*) as cnt FROM login_history WHERE user_id = $1",
            (user_id,),
        )
        login_count = count_row["cnt"] if count_row else 0

    token = create_token(user_id, row["username"])
    return {
        "id": user_id,
        "username": row["username"],
        "nickname": row["nickname"] or row["username"],
        "avatar": row["avatar"],
        "token": token,
        "login_count": login_count,
        "last_login": now,
    }


async def get_user_by_id(user_id: str) -> dict | None:
    """根据 ID 获取用户信息"""
    from agent.store import get_store
    store = await get_store()

    async with _acquire(store) as db:
        row = await _fetchone(db, "SELECT * FROM users WHERE id = $1", (user_id,))
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


async def update_profile(
    user_id: str,
    nickname: str | None = None,
    avatar: str | None = None,
) -> dict | None:
    """更新用户资料（昵称 / 头像），返回更新后的用户信息；用户不存在返回 None"""
    from agent.store import get_store
    store = await get_store()

    if nickname is not None:
        nickname = nickname.strip()[:30]

    async with _tx(store) as db:
        row = await _fetchone(db, "SELECT id FROM users WHERE id = $1", (user_id,))
        if not row:
            return None
        if nickname is not None and avatar is not None:
            await _execute(
                db, "UPDATE users SET nickname=$1, avatar=$2 WHERE id=$3",
                (nickname, avatar, user_id),
            )
        elif nickname is not None:
            await _execute(db, "UPDATE users SET nickname=$1 WHERE id=$2", (nickname, user_id))
        elif avatar is not None:
            await _execute(db, "UPDATE users SET avatar=$1 WHERE id=$2", (avatar, user_id))
    return await get_user_by_id(user_id)


async def change_password(user_id: str, old_password: str, new_password: str) -> None:
    """修改登录密码：校验旧密码 + 新密码强度。校验失败抛 ValueError。"""
    from agent.store import get_store
    store = await get_store()

    async with _tx(store) as db:
        row = await _fetchone(db, "SELECT username, password FROM users WHERE id = $1", (user_id,))
        if not row:
            raise ValueError("用户不存在")
        if not bcrypt.checkpw(old_password.encode(), row["password"].encode()):
            raise ValueError("当前密码错误")
        if err := validate_password_strength(new_password, row["username"]):
            raise ValueError(err)
        pwd_hash = bcrypt.hashpw(new_password.encode(), bcrypt.gensalt()).decode()
        await _execute(db, "UPDATE users SET password=$1 WHERE id=$2", (pwd_hash, user_id))


async def get_login_history(user_id: str, limit: int = 20) -> list[dict]:
    """获取用户登录历史"""
    from agent.store import get_store
    store = await get_store()

    async with _acquire(store) as db:
        rows = await _fetchall(
            db,
            "SELECT * FROM login_history WHERE user_id = $1 ORDER BY login_at DESC LIMIT $2",
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

    async with _acquire(store) as db:
        row = await _fetchone(db, "SELECT COUNT(*) as cnt FROM users")
    return row["cnt"] if row else 0
