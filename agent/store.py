"""
对话持久化存储
基于 asyncpg 的异步 PostgreSQL 操作层（Neon 托管）
"""

from __future__ import annotations

import asyncio
import json
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone

import asyncpg

from agent.models import ConversationDetail, ConversationMeta, Message


class ConversationStore:
    """对话存储管理器（asyncpg 连接池）"""

    def __init__(self, db_url: str, *, min_size: int = 1, max_size: int = 5):
        self._dsn = db_url
        self._min_size = min_size
        self._max_size = max_size
        self._pool: asyncpg.Pool | None = None

    @staticmethod
    def _normalize_dsn(dsn: str) -> tuple[str, str | None]:
        """从 DSN 提取并移除 sslmode / channel_binding，返回 (干净 DSN, sslmode 值或 None)。

        asyncpg 用 ssl= 参数控制 TLS，不认 DSN 查询串里的 sslmode；
        channel_binding 是 libpq 专属参数，asyncpg 同样不认。两者若不剥离，
        都会被当作未识别的查询参数传给 PG 当 GUC，
        导致连接报 "unrecognized configuration parameter ..."。
        """
        if "sslmode=" not in dsn and "channel_binding=" not in dsn:
            return dsn, None
        base, _, query = dsn.partition("?")
        rest: list[str] = []
        sslmode: str | None = None
        for part in query.split("&"):
            if part.startswith("sslmode="):
                sslmode = part.split("=", 1)[1]
            elif part.startswith("channel_binding="):
                continue
            elif part:
                rest.append(part)
        clean = base if not rest else f"{base}?{'&'.join(rest)}"
        return clean, sslmode

    # ── 生命周期 ──────────────────────────────────

    async def _get_pool(self) -> asyncpg.Pool:
        """获取连接池（懒初始化）"""
        if self._pool is None:
            clean_dsn, sslmode = self._normalize_dsn(self._dsn)
            kwargs: dict = {
                "min_size": self._min_size,
                "max_size": self._max_size,
                "command_timeout": 30,
            }
            # Neon 强制 SSL：DSN 自带 ?sslmode=require 时剥离后显式传 ssl= 参数。
            # 未指定 sslmode 时留给 asyncpg 默认（prefer，本地无 SSL 的 PG 也可连）。
            if sslmode:
                kwargs["ssl"] = sslmode
            # 池化端点（主机名含 -pooler，走 Neon PgBouncer 事务池化）：事务池化
            # 模式不持久化 prepared statement，禁用 asyncpg 语句缓存以兼容。
            if "-pooler" in clean_dsn:
                kwargs["statement_cache_size"] = 0
            self._pool = await asyncpg.create_pool(clean_dsn, **kwargs)
        return self._pool

    async def init(self) -> None:
        """初始化表结构"""
        async with _tx(self) as db:
            await db.execute("""
                CREATE TABLE IF NOT EXISTS conversations (
                    id          TEXT PRIMARY KEY,
                    user_id     TEXT NOT NULL DEFAULT '',
                    title       TEXT NOT NULL DEFAULT '新对话',
                    model       TEXT NOT NULL DEFAULT 'glm-4-flash',
                    deleted     INTEGER NOT NULL DEFAULT 0,
                    created_at  TEXT NOT NULL,
                    updated_at  TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS messages (
                    id            BIGSERIAL PRIMARY KEY,
                    conversation_id TEXT NOT NULL,
                    role          TEXT NOT NULL CHECK(role IN ('system','user','assistant','tool')),
                    content       TEXT NOT NULL DEFAULT '',
                    name          TEXT,
                    tool_call_id  TEXT,
                    meta          TEXT DEFAULT '{}',
                    created_at    TEXT NOT NULL,
                    FOREIGN KEY (conversation_id)
                        REFERENCES conversations(id)
                        ON DELETE CASCADE
                );

                CREATE INDEX IF NOT EXISTS idx_msg_conv
                    ON messages(conversation_id, id);
                CREATE INDEX IF NOT EXISTS idx_conv_user
                    ON conversations(user_id, updated_at DESC);
            """)
            # 兼容旧表：添加列（如果不存在）。PG 支持 IF NOT EXISTS，不抛异常。
            for col, default in [("user_id", "''"), ("deleted", "0")]:
                await db.execute(
                    f"ALTER TABLE conversations ADD COLUMN IF NOT EXISTS {col} "
                    f"TEXT DEFAULT {default}"
                )

    async def close(self) -> None:
        """关闭数据库连接池"""
        if self._pool:
            await self._pool.close()
            self._pool = None

    # ── 对话 CRUD ──────────────────────────────────

    async def create_conversation(
        self,
        title: str | None = None,
        model: str = "glm-4-flash",
        system_prompt: str | None = None,
        user_id: str = "",
    ) -> str:
        """创建新对话，返回对话 ID"""
        conv_id = f"conv_{uuid.uuid4().hex[:16]}"
        now = datetime.now(timezone.utc).isoformat()
        title = title or "新对话"

        async with _tx(self) as db:
            await db.execute(
                "INSERT INTO conversations (id, user_id, title, model, created_at, updated_at) "
                "VALUES ($1, $2, $3, $4, $5, $6)",
                conv_id, user_id, title, model, now, now,
            )
            if system_prompt:
                await db.execute(
                    "INSERT INTO messages (conversation_id, role, content, created_at) "
                    "VALUES ($1, 'system', $2, $3)",
                    conv_id, system_prompt, now,
                )
        return conv_id

    async def get_conversation(
        self, conv_id: str, user_id: str = ""
    ) -> ConversationDetail | None:
        """获取对话详情（含所有消息），可选的用户隔离"""
        async with _acquire(self) as db:
            if user_id:
                row = await db.fetchrow(
                    "SELECT * FROM conversations WHERE id = $1 AND user_id = $2 AND deleted = 0",
                    conv_id, user_id,
                )
            else:
                row = await db.fetchrow(
                    "SELECT * FROM conversations WHERE id = $1 AND deleted = 0",
                    conv_id,
                )
            if not row:
                return None

            msgs = await db.fetch(
                "SELECT role, content, name, tool_call_id "
                "FROM messages WHERE conversation_id = $1 ORDER BY id",
                conv_id,
            )
            messages = [
                Message(
                    role=m["role"],
                    content=m["content"],
                    name=m["name"],
                    tool_call_id=m["tool_call_id"],
                )
                for m in msgs
            ]

            return ConversationDetail(
                id=row["id"],
                title=row["title"],
                model=row["model"],
                messages=messages,
                created_at=row["created_at"],
                updated_at=row["updated_at"],
            )

    async def list_conversations(
        self, user_id: str = "", page: int = 1, page_size: int = 20
    ) -> tuple[list[ConversationMeta], int]:
        """分页列出对话，支持按用户过滤"""
        async with _acquire(self) as db:
            if user_id:
                total = await db.fetchval(
                    "SELECT COUNT(*) FROM conversations WHERE user_id = $1 AND deleted = 0",
                    user_id,
                )
            else:
                total = await db.fetchval(
                    "SELECT COUNT(*) FROM conversations WHERE deleted = 0"
                )

            offset = (page - 1) * page_size
            if user_id:
                rows = await db.fetch(
                    """
                    SELECT c.*, COUNT(m.id) as msg_count
                    FROM conversations c
                    LEFT JOIN messages m ON m.conversation_id = c.id AND m.role != 'system'
                    WHERE c.user_id = $1 AND c.deleted = 0
                    GROUP BY c.id
                    ORDER BY c.updated_at DESC
                    LIMIT $2 OFFSET $3
                    """,
                    user_id, page_size, offset,
                )
            else:
                rows = await db.fetch(
                    """
                    SELECT c.*, COUNT(m.id) as msg_count
                    FROM conversations c
                    LEFT JOIN messages m ON m.conversation_id = c.id AND m.role != 'system'
                    WHERE c.deleted = 0
                    GROUP BY c.id
                    ORDER BY c.updated_at DESC
                    LIMIT $1 OFFSET $2
                    """,
                    page_size, offset,
                )

            items = [
                ConversationMeta(
                    id=r["id"],
                    title=r["title"],
                    model=r["model"],
                    message_count=r["msg_count"],
                    created_at=r["created_at"],
                    updated_at=r["updated_at"],
                )
                for r in rows
            ]

            return items, total

    async def delete_conversation(
        self, conv_id: str, user_id: str = ""
    ) -> bool:
        """软删除对话（标记 deleted=1），返回是否成功"""
        now = datetime.now(timezone.utc).isoformat()

        async with _tx(self) as db:
            if user_id:
                row = await db.fetchrow(
                    "UPDATE conversations SET deleted = 1, updated_at = $1 "
                    "WHERE id = $2 AND user_id = $3 AND deleted = 0 "
                    "RETURNING id",
                    now, conv_id, user_id,
                )
            else:
                row = await db.fetchrow(
                    "UPDATE conversations SET deleted = 1, updated_at = $1 "
                    "WHERE id = $2 AND deleted = 0 "
                    "RETURNING id",
                    now, conv_id,
                )
            return row is not None

    async def update_title(self, conv_id: str, title: str) -> bool:
        """更新对话标题"""
        now = datetime.now(timezone.utc).isoformat()

        async with _tx(self) as db:
            row = await db.fetchrow(
                "UPDATE conversations SET title = $1, updated_at = $2 "
                "WHERE id = $3 RETURNING id",
                title, now, conv_id,
            )
            return row is not None

    # ── 消息操作 ──────────────────────────────────

    async def add_message(
        self,
        conv_id: str,
        role: str,
        content: str,
        name: str | None = None,
        tool_call_id: str | None = None,
        meta: dict | None = None,
    ) -> None:
        """添加一条消息到对话"""
        now = datetime.now(timezone.utc).isoformat()

        async with _tx(self) as db:
            await db.execute(
                "INSERT INTO messages (conversation_id, role, content, name, "
                "tool_call_id, meta, created_at) VALUES ($1, $2, $3, $4, $5, $6, $7)",
                conv_id, role, content, name, tool_call_id,
                json.dumps(meta or {}, ensure_ascii=False), now,
            )
            await db.execute(
                "UPDATE conversations SET updated_at = $1 WHERE id = $2",
                now, conv_id,
            )

    async def add_messages_batch(
        self,
        conv_id: str,
        messages: list[Message],
    ) -> None:
        """批量添加消息"""
        now = datetime.now(timezone.utc).isoformat()

        async with _tx(self) as db:
            for msg in messages:
                await db.execute(
                    "INSERT INTO messages (conversation_id, role, content, name, "
                    "tool_call_id, created_at) VALUES ($1, $2, $3, $4, $5, $6)",
                    conv_id, msg.role, msg.content, msg.name, msg.tool_call_id, now,
                )
            await db.execute(
                "UPDATE conversations SET updated_at = $1 WHERE id = $2",
                now, conv_id,
            )


# ═══════════════════════════════════════════
# 通用连接与 SQL 辅助函数（给 users.py 等模块用）
# ═══════════════════════════════════════════

@asynccontextmanager
async def _tx(store: "ConversationStore"):
    """从连接池取一个连接并开启事务；正常结束自动提交，异常自动回滚。"""
    pool = await store._get_pool()
    async with pool.acquire() as conn:
        async with conn.transaction():
            yield conn


@asynccontextmanager
async def _acquire(store: "ConversationStore"):
    """从连接池取一个连接（无显式事务，每条语句自动提交），用于纯读。"""
    pool = await store._get_pool()
    async with pool.acquire() as conn:
        yield conn


async def _fetchone(conn: asyncpg.Connection, sql: str, params=()):
    """执行查询并返回一行"""
    return await conn.fetchrow(sql, *params)


async def _fetchall(conn: asyncpg.Connection, sql: str, params=()):
    """执行查询并返回所有行"""
    return await conn.fetch(sql, *params)


async def _execute(conn: asyncpg.Connection, sql: str, params=()):
    """执行 SQL 语句"""
    return await conn.execute(sql, *params)


# ═══════════════════════════════════════════
# 全局存储实例
# ═══════════════════════════════════════════

_store: ConversationStore | None = None
_store_lock = asyncio.Lock()


async def get_store(db_url: str | None = None) -> ConversationStore:
    """获取全局存储实例（线程安全）"""
    global _store
    if _store is not None:
        return _store
    async with _store_lock:
        if _store is not None:
            return _store
        from agent.config import get_settings

        url = db_url or get_settings().database_url
        if not url:
            raise RuntimeError(
                "DATABASE_URL 未配置：请在 .env 或环境变量中设置 Neon PostgreSQL 连接串"
            )
        _store = ConversationStore(url, min_size=1, max_size=5)
        await _store.init()
        return _store


async def close_store() -> None:
    """关闭全局存储"""
    global _store
    if _store:
        await _store.close()
        _store = None
