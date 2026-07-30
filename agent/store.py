"""
对话持久化存储
基于 aiosqlite 的异步 SQLite 操作层
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path

import aiosqlite

from agent.models import ConversationDetail, ConversationMeta, Message


class ConversationStore:
    """对话存储管理器"""

    def __init__(self, db_path: str = "data/conversations.db"):
        self.db_path = Path(db_path)
        self._conn: aiosqlite.Connection | None = None

    # ── 生命周期 ──────────────────────────────────

    async def _get_conn(self) -> aiosqlite.Connection:
        """获取数据库连接（懒初始化）"""
        if self._conn is None:
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
            self._conn = await aiosqlite.connect(str(self.db_path))
            self._conn.row_factory = aiosqlite.Row
            await self._conn.execute("PRAGMA journal_mode=WAL")
            await self._conn.execute("PRAGMA foreign_keys=ON")
        return self._conn

    async def init(self) -> None:
        """初始化表结构"""
        db = await self._get_conn()
        await db.executescript("""
            CREATE TABLE IF NOT EXISTS conversations (
                id          TEXT PRIMARY KEY,
                user_id     TEXT DEFAULT '',
                title       TEXT NOT NULL DEFAULT '新对话',
                model       TEXT NOT NULL DEFAULT 'glm-4-flash',
                created_at  TEXT NOT NULL,
                updated_at  TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS messages (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
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
        # 兼容旧表：添加 user_id 列（如果不存在）
        try:
            await db.execute("ALTER TABLE conversations ADD COLUMN user_id TEXT DEFAULT ''")
        except Exception:
            pass
        await db.commit()

    async def close(self) -> None:
        """关闭数据库连接"""
        if self._conn:
            await self._conn.close()
            self._conn = None

    # ── 对话 CRUD ──────────────────────────────────

    async def create_conversation(
        self,
        title: str | None = None,
        model: str = "glm-4-flash",
        system_prompt: str | None = None,
        user_id: str = "",
    ) -> str:
        """创建新对话，返回对话 ID"""
        db = await self._get_conn()
        conv_id = f"conv_{uuid.uuid4().hex[:16]}"
        now = datetime.now(timezone.utc).isoformat()
        title = title or "新对话"

        await db.execute(
            "INSERT INTO conversations (id, user_id, title, model, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (conv_id, user_id, title, model, now, now),
        )

        if system_prompt:
            await db.execute(
                "INSERT INTO messages (conversation_id, role, content, created_at) "
                "VALUES (?, 'system', ?, ?)",
                (conv_id, system_prompt, now),
            )

        await db.commit()
        return conv_id

    async def get_conversation(self, conv_id: str) -> ConversationDetail | None:
        """获取对话详情（含所有消息）"""
        db = await self._get_conn()

        conv = await db.execute(
            "SELECT * FROM conversations WHERE id = ?", (conv_id,)
        )
        row = await conv.fetchone()
        if not row:
            return None

        msgs = await db.execute(
            "SELECT role, content, name, tool_call_id "
            "FROM messages WHERE conversation_id = ? ORDER BY id",
            (conv_id,),
        )
        messages = [
            Message(
                role=m["role"],
                content=m["content"],
                name=m["name"],
                tool_call_id=m["tool_call_id"],
            )
            for m in await msgs.fetchall()
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
        db = await self._get_conn()

        if user_id:
            total_row = await db.execute(
                "SELECT COUNT(*) FROM conversations WHERE user_id = ?", (user_id,)
            )
        else:
            total_row = await db.execute("SELECT COUNT(*) FROM conversations")
        total = (await total_row.fetchone())[0]

        offset = (page - 1) * page_size
        if user_id:
            rows = await db.execute(
                """
                SELECT c.*, COUNT(m.id) as msg_count
                FROM conversations c
                LEFT JOIN messages m ON m.conversation_id = c.id AND m.role != 'system'
                WHERE c.user_id = ?
                GROUP BY c.id
                ORDER BY c.updated_at DESC
                LIMIT ? OFFSET ?
                """,
                (user_id, page_size, offset),
            )
        else:
            rows = await db.execute(
                """
                SELECT c.*, COUNT(m.id) as msg_count
                FROM conversations c
                LEFT JOIN messages m ON m.conversation_id = c.id AND m.role != 'system'
                GROUP BY c.id
                ORDER BY c.updated_at DESC
                LIMIT ? OFFSET ?
                """,
                (page_size, offset),
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
            for r in await rows.fetchall()
        ]

        return items, total

    async def delete_conversation(self, conv_id: str) -> bool:
        """删除对话，返回是否成功"""
        db = await self._get_conn()
        cursor = await db.execute(
            "DELETE FROM conversations WHERE id = ?", (conv_id,)
        )
        await db.commit()
        return cursor.rowcount > 0

    async def update_title(self, conv_id: str, title: str) -> bool:
        """更新对话标题"""
        db = await self._get_conn()
        now = datetime.now(timezone.utc).isoformat()
        cursor = await db.execute(
            "UPDATE conversations SET title = ?, updated_at = ? WHERE id = ?",
            (title, now, conv_id),
        )
        await db.commit()
        return cursor.rowcount > 0

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
        db = await self._get_conn()
        now = datetime.now(timezone.utc).isoformat()

        await db.execute(
            "INSERT INTO messages (conversation_id, role, content, name, "
            "tool_call_id, meta, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                conv_id,
                role,
                content,
                name,
                tool_call_id,
                json.dumps(meta or {}, ensure_ascii=False),
                now,
            ),
        )

        await db.execute(
            "UPDATE conversations SET updated_at = ? WHERE id = ?",
            (now, conv_id),
        )

        await db.commit()

    async def add_messages_batch(
        self,
        conv_id: str,
        messages: list[Message],
    ) -> None:
        """批量添加消息"""
        db = await self._get_conn()
        now = datetime.now(timezone.utc).isoformat()

        for msg in messages:
            await db.execute(
                "INSERT INTO messages (conversation_id, role, content, name, "
                "tool_call_id, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                (
                    conv_id,
                    msg.role,
                    msg.content,
                    msg.name,
                    msg.tool_call_id,
                    now,
                ),
            )

        await db.execute(
            "UPDATE conversations SET updated_at = ? WHERE id = ?",
            (now, conv_id),
        )

        await db.commit()


# ═══════════════════════════════════════════
# 通用 SQL 辅助函数（给 users.py 等模块用）
# ═══════════════════════════════════════════

async def _fetchone(db: aiosqlite.Connection, sql: str, params=()):
    """执行查询并返回一行"""
    cursor = await db.execute(sql, params)
    return await cursor.fetchone()


async def _fetchall(db: aiosqlite.Connection, sql: str, params=()):
    """执行查询并返回所有行"""
    cursor = await db.execute(sql, params)
    return await cursor.fetchall()


async def _execute(db: aiosqlite.Connection, sql: str, params=()):
    """执行 SQL 语句"""
    return await db.execute(sql, params)


# ═══════════════════════════════════════════
# 全局存储实例
# ═══════════════════════════════════════════

_store: ConversationStore | None = None


async def get_store(db_path: str | None = None) -> ConversationStore:
    """获取全局存储实例"""
    global _store
    if _store is None:
        from agent.config import get_settings

        path = db_path or get_settings().database_path
        _store = ConversationStore(path)
        await _store.init()
    return _store


async def close_store() -> None:
    """关闭全局存储"""
    global _store
    if _store:
        await _store.close()
        _store = None
