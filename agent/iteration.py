"""
自我迭代引擎 — 用户记忆、偏好学习、对话进化
星媛会根据与用户的互动不断优化自己的表现
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone

import aiosqlite

from agent.store import _fetchall, _fetchone, get_store


# ═══════════════════════════════════════════
# 记忆表初始化
# ═══════════════════════════════════════════

MEMORY_TABLES_SQL = """
CREATE TABLE IF NOT EXISTS agent_memory (
    id          TEXT PRIMARY KEY,
    user_id     TEXT NOT NULL,
    category    TEXT NOT NULL DEFAULT 'general',
    key         TEXT NOT NULL,
    value       TEXT NOT NULL,
    confidence  REAL DEFAULT 0.5,
    source      TEXT DEFAULT 'conversation',
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS agent_feedback (
    id          TEXT PRIMARY KEY,
    user_id     TEXT NOT NULL,
    conv_id     TEXT,
    msg_id      TEXT,
    rating      INTEGER NOT NULL CHECK(rating BETWEEN 0 AND 5),
    comment     TEXT DEFAULT '',
    created_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS agent_evolution (
    id          TEXT PRIMARY KEY,
    user_id     TEXT NOT NULL,
    version     INTEGER NOT NULL DEFAULT 1,
    change_log  TEXT NOT NULL,
    applied_at  TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_memory_user ON agent_memory(user_id, category);
CREATE INDEX IF NOT EXISTS idx_feedback_user ON agent_feedback(user_id, created_at DESC);
"""


async def init_iteration_tables():
    """初始化自我迭代表"""
    store = await get_store()
    db = await store._get_conn()
    await db.executescript(MEMORY_TABLES_SQL)
    await db.commit()


# ═══════════════════════════════════════════
# 用户记忆管理
# ═══════════════════════════════════════════

async def remember(user_id: str, key: str, value: str, category: str = "general", confidence: float = 0.5):
    """记住关于用户的一件事"""
    store = await get_store()
    db = await store._get_conn()
    now = datetime.now(timezone.utc).isoformat()

    # 检查是否已存在
    existing = await _fetchone(
        db, "SELECT id FROM agent_memory WHERE user_id = ? AND key = ?",
        (user_id, key),
    )
    if existing:
        await db.execute(
            "UPDATE agent_memory SET value=?, confidence=?, updated_at=? WHERE id=?",
            (value, confidence, now, existing["id"]),
        )
    else:
        await db.execute(
            "INSERT INTO agent_memory (id, user_id, category, key, value, confidence, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (f"mem_{uuid.uuid4().hex[:12]}", user_id, category, key, value, confidence, now, now),
        )
    await db.commit()


async def recall(user_id: str, category: str | None = None) -> list[dict]:
    """获取关于用户的记忆"""
    store = await get_store()
    db = await store._get_conn()

    if category:
        rows = await _fetchall(
            db,
            "SELECT * FROM agent_memory WHERE user_id=? AND category=? ORDER BY updated_at DESC",
            (user_id, category),
        )
    else:
        rows = await _fetchall(
            db,
            "SELECT * FROM agent_memory WHERE user_id=? ORDER BY updated_at DESC LIMIT 50",
            (user_id,),
        )
    return [{"key": r["key"], "value": r["value"], "category": r["category"],
             "confidence": r["confidence"]} for r in rows]


async def forget(user_id: str, key: str):
    """删除一条记忆"""
    store = await get_store()
    db = await store._get_conn()
    await db.execute(
        "DELETE FROM agent_memory WHERE user_id=? AND key=?", (user_id, key)
    )
    await db.commit()


# ═══════════════════════════════════════════
# 反馈收集
# ═══════════════════════════════════════════

async def save_feedback(user_id: str, rating: int, conv_id: str = "", comment: str = ""):
    """保存用户反馈（0-5星）"""
    store = await get_store()
    db = await store._get_conn()
    now = datetime.now(timezone.utc).isoformat()

    await db.execute(
        "INSERT INTO agent_feedback (id, user_id, conv_id, rating, comment, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (f"fb_{uuid.uuid4().hex[:12]}", user_id, conv_id, rating, comment, now),
    )
    await db.commit()


async def get_feedback_stats(user_id: str) -> dict:
    """获取反馈统计"""
    store = await get_store()
    db = await store._get_conn()

    row = await _fetchone(
        db,
        "SELECT AVG(rating) as avg_rating, COUNT(*) as total FROM agent_feedback WHERE user_id=?",
        (user_id,),
    )
    if row and row["total"]:
        return {"avg_rating": round(row["avg_rating"], 1), "total_feedback": row["total"]}
    return {"avg_rating": 0, "total_feedback": 0}


# ═══════════════════════════════════════════
# 自我进化 — 个性系统提示词生成
# ═══════════════════════════════════════════

async def generate_persona_prompt(user_id: str) -> str:
    """
    根据用户记忆和交互历史，生成个性化的系统提示词
    这是星媛自我迭代的核心
    """
    memories = await recall(user_id)
    feedback = await get_feedback_stats(user_id)

    # 基础提示词
    base = (
        "你是星媛，用户的专属 AI 智能助手。你温柔、专业、可靠、善解人意。"
        "请用中文回答，保持回复简洁且有帮助。"
    )

    # 根据记忆添加个性适配
    parts = [base]

    # 用户偏好（清理注入风险）
    prefs = [m for m in memories if m["category"] == "preference" and m["confidence"] > 0.3]
    if prefs:
        safe = []
        for p in prefs[:10]:
            val = str(p["value"])[:200].replace("\n", " ").replace("\r", "")
            key = str(p["key"])[:50].replace("\n", " ").replace("\r", "")
            safe.append(f"{key}={val}")
        parts.append(f"用户偏好: {'；'.join(safe)}。请据此调整回复风格和内容。")

    # 用户信息
    info = [m for m in memories if m["category"] == "user_info" and m["confidence"] > 0.5]
    if info:
        safe = []
        for i in info[:10]:
            val = str(i["value"])[:200].replace("\n", " ").replace("\r", "")
            key = str(i["key"])[:50].replace("\n", " ").replace("\r", "")
            safe.append(f"{key}: {val}")
        parts.append(f"关于用户的信息: {'；'.join(safe)}。在恰当的时候自然地引用这些信息。")

    # 交互模式
    patterns = [m for m in memories if m["category"] == "pattern"]
    if patterns:
        pattern_str = "；".join(f"{p['key']}: {p['value']}" for p in patterns[:5])
        parts.append(f"用户交互模式: {pattern_str}。据此优化交互方式。")

    # 反馈驱动的改进
    if feedback["total_feedback"] > 0:
        if feedback["avg_rating"] >= 4.0:
            parts.append("用户对你的表现很满意。保持当前风格。")
        elif feedback["avg_rating"] < 3.0:
            parts.append("用户满意度有待提升。请更加细心、更有深度地回复。")

    parts.append("你具备自我迭代能力，会根据与用户的互动不断优化自己。每次对话都是一次学习机会。")

    return "\n".join(parts)


# ═══════════════════════════════════════════
# 自动学习 — 从对话中提取信息
# ═══════════════════════════════════════════

LEARNING_TRIGGERS = [
    # (关键词模式, 记忆类别, 提取模板)
    ("我叫*", "user_info", "name"),
    ("我是*", "user_info", "occupation"),
    ("我喜欢*", "preference", "like"),
    ("我讨厌*", "preference", "dislike"),
    ("我从事*", "user_info", "job"),
    ("我的工作是*", "user_info", "job"),
    ("我在*学习", "user_info", "school"),
    ("我的爱好是*", "preference", "hobby"),
    ("我不喜欢*", "preference", "dislike"),
    ("我在*工作", "user_info", "workplace"),
]


async def learn_from_message(user_id: str, content: str):
    """从用户消息中自动学习信息"""
    for pattern, category, key in LEARNING_TRIGGERS:
        prefix = pattern.replace("*", "")
        if prefix in content:
            # 简单提取：取关键词后面的内容（一段话）
            idx = content.find(prefix)
            if idx >= 0:
                extracted = content[idx + len(prefix):].split("。")[0].split("，")[0].strip()[:100]
                if extracted and len(extracted) > 1:
                    await remember(user_id, key, extracted, category, confidence=0.6)
                    break  # 每条消息只触发一个学习模式


# ═══════════════════════════════════════════
# 进化记录
# ═══════════════════════════════════════════

async def record_evolution(user_id: str, change_log: str):
    """记录一次自我进化"""
    store = await get_store()
    db = await store._get_conn()

    # 获取当前版本号
    row = await _fetchone(
        db,
        "SELECT MAX(version) as max_v FROM agent_evolution WHERE user_id=?",
        (user_id,),
    )
    version = (row["max_v"] or 0) + 1 if row else 1

    now = datetime.now(timezone.utc).isoformat()
    await db.execute(
        "INSERT INTO agent_evolution (id, user_id, version, change_log, applied_at) "
        "VALUES (?, ?, ?, ?, ?)",
        (f"evo_{uuid.uuid4().hex[:12]}", user_id, version, change_log, now),
    )
    await db.commit()
    return version
