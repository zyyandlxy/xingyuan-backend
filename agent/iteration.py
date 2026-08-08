"""
自我迭代引擎 — 用户记忆、偏好学习、对话进化
星媛会根据与用户的互动不断优化自己的表现
"""

from __future__ import annotations

import json
import re
import time
import uuid
from datetime import datetime, timezone

from agent.store import _acquire, _execute, _fetchall, _fetchone, _tx, get_store


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

CREATE TABLE IF NOT EXISTS question_stats (
    id          TEXT PRIMARY KEY,
    user_id     TEXT NOT NULL,
    qkey        TEXT NOT NULL,
    qtext       TEXT NOT NULL,
    count       INTEGER NOT NULL DEFAULT 1,
    first_at    TEXT NOT NULL,
    last_at     TEXT NOT NULL,
    updated_at  TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_memory_user ON agent_memory(user_id, category);
CREATE INDEX IF NOT EXISTS idx_feedback_user ON agent_feedback(user_id, created_at DESC);
CREATE UNIQUE INDEX IF NOT EXISTS idx_qstats_user_key ON question_stats(user_id, qkey);
CREATE INDEX IF NOT EXISTS idx_qstats_user ON question_stats(user_id);
"""


_iteration_tables_ready = False


async def init_iteration_tables():
    """初始化自我迭代表（DDL 只执行一次，后续调用直接跳过）"""
    global _iteration_tables_ready
    if _iteration_tables_ready:
        return
    store = await get_store()
    async with _tx(store) as db:
        await db.execute(MEMORY_TABLES_SQL)
    _iteration_tables_ready = True


# persona 提示词缓存：{user_id: (prompt, 生成时间戳)}，写记忆时主动失效
_persona_cache: dict[str, tuple[str, float]] = {}
_PERSONA_TTL = 300  # 5 分钟


# ═══════════════════════════════════════════
# 用户记忆管理
# ═══════════════════════════════════════════

async def remember(user_id: str, key: str, value: str, category: str = "general", confidence: float = 0.5):
    """记住关于用户的一件事"""
    store = await get_store()
    now = datetime.now(timezone.utc).isoformat()
    _persona_cache.pop(user_id, None)  # 记忆变化 → 下次重新生成 persona

    async with _tx(store) as db:
        # 检查是否已存在
        existing = await _fetchone(
            db, "SELECT id FROM agent_memory WHERE user_id = $1 AND key = $2",
            (user_id, key),
        )
        if existing:
            await _execute(
                db,
                "UPDATE agent_memory SET value=$1, confidence=$2, updated_at=$3 WHERE id=$4",
                (value, confidence, now, existing["id"]),
            )
        else:
            await _execute(
                db,
                "INSERT INTO agent_memory (id, user_id, category, key, value, confidence, created_at, updated_at) "
                "VALUES ($1, $2, $3, $4, $5, $6, $7, $8)",
                (f"mem_{uuid.uuid4().hex[:12]}", user_id, category, key, value, confidence, now, now),
            )


async def recall(user_id: str, category: str | None = None) -> list[dict]:
    """获取关于用户的记忆"""
    store = await get_store()

    async with _acquire(store) as db:
        if category:
            rows = await _fetchall(
                db,
                "SELECT * FROM agent_memory WHERE user_id=$1 AND category=$2 ORDER BY updated_at DESC",
                (user_id, category),
            )
        else:
            rows = await _fetchall(
                db,
                "SELECT * FROM agent_memory WHERE user_id=$1 ORDER BY updated_at DESC LIMIT 50",
                (user_id,),
            )
    return [{"key": r["key"], "value": r["value"], "category": r["category"],
             "confidence": r["confidence"]} for r in rows]


async def forget(user_id: str, key: str):
    """删除一条记忆"""
    store = await get_store()
    _persona_cache.pop(user_id, None)  # 记忆变化 → 下次重新生成 persona
    async with _tx(store) as db:
        await _execute(db, "DELETE FROM agent_memory WHERE user_id=$1 AND key=$2", (user_id, key))


# ═══════════════════════════════════════════
# 反馈收集
# ═══════════════════════════════════════════

async def save_feedback(user_id: str, rating: int, conv_id: str = "", comment: str = ""):
    """保存用户反馈（0-5星）"""
    store = await get_store()
    now = datetime.now(timezone.utc).isoformat()

    async with _tx(store) as db:
        await _execute(
            db,
            "INSERT INTO agent_feedback (id, user_id, conv_id, rating, comment, created_at) "
            "VALUES ($1, $2, $3, $4, $5, $6)",
            (f"fb_{uuid.uuid4().hex[:12]}", user_id, conv_id, rating, comment, now),
        )


async def get_feedback_stats(user_id: str) -> dict:
    """获取反馈统计"""
    store = await get_store()

    async with _acquire(store) as db:
        row = await _fetchone(
            db,
            "SELECT AVG(rating) as avg_rating, COUNT(*) as total FROM agent_feedback WHERE user_id=$1",
            (user_id,),
        )
    if row and row["total"]:
        # asyncpg 把 AVG(integer) 解为 Decimal，转 float 再取整
        return {"avg_rating": round(float(row["avg_rating"]), 1), "total_feedback": row["total"]}
    return {"avg_rating": 0, "total_feedback": 0}


# ═══════════════════════════════════════════
# 自我进化 — 个性系统提示词生成
# ═══════════════════════════════════════════

async def generate_persona_prompt(user_id: str) -> str:
    """
    根据用户记忆和交互历史，生成个性化的系统提示词
    这是星媛自我迭代的核心
    """
    # 缓存命中（5 分钟内）：跳过 2 次 DB 查询，缩短发消息到首字的等待
    now = time.time()
    cached = _persona_cache.get(user_id)
    if cached and now - cached[1] < _PERSONA_TTL:
        return cached[0]

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

    prompt = "\n".join(parts)
    _persona_cache[user_id] = (prompt, now)
    return prompt


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
# 高频提问统计 — 用户常问的问题（>= 阈值自动记入记忆，供用户查看）
# ═══════════════════════════════════════════

_QUESTION_THRESHOLD = 3  # 同一问题提问达到该次数，写入 agent_memory


def _normalize_question(text: str) -> str:
    """归一化文本用于去重统计：去空白/常见标点/转小写（保留中文）"""
    return re.sub(r"[\s\.\,\。\，\！\!\？\?\、\；\;\：\:\-\_\'\"“”‘’\(\)\[\]【】]+", "", text).lower()


async def record_question(user_id: str, content: str):
    """统计用户问题频率；同一问题计数 >= _QUESTION_THRESHOLD 时记入记忆"""
    if not content:
        return
    text = content.strip()
    qkey = _normalize_question(text)
    if not qkey or len(qkey) < 2:
        return

    store = await get_store()
    now = datetime.now(timezone.utc).isoformat()
    async with _tx(store) as db:
        row = await _fetchone(
            db,
            "SELECT id, count FROM question_stats WHERE user_id=$1 AND qkey=$2",
            (user_id, qkey),
        )
        if row:
            new_count = row["count"] + 1
            await _execute(
                db,
                "UPDATE question_stats SET count=$1, qtext=$2, last_at=$3, updated_at=$4 WHERE id=$5",
                (new_count, text[:120], now, now, row["id"]),
            )
        else:
            new_count = 1
            await _execute(
                db,
                "INSERT INTO question_stats (id, user_id, qkey, qtext, count, first_at, last_at, updated_at) "
                "VALUES ($1,$2,$3,$4,$5,$6,$7,$8)",
                (f"qs_{uuid.uuid4().hex[:12]}", user_id, qkey, text[:120], new_count, now, now, now),
            )

    if new_count >= _QUESTION_THRESHOLD:
        # 写入记忆：key 归一化（内部），value 面向用户展示（前端按类别展示 value）
        await remember(
            user_id,
            f"q_{qkey}",
            f"你常问：「{text[:40]}」（已提问 {new_count} 次）",
            category="frequent_question",
            confidence=0.8,
        )


# ═══════════════════════════════════════════
# 进化记录
# ═══════════════════════════════════════════

async def record_evolution(user_id: str, change_log: str):
    """记录一次自我进化"""
    store = await get_store()

    async with _tx(store) as db:
        # 获取当前版本号
        row = await _fetchone(
            db,
            "SELECT MAX(version) as max_v FROM agent_evolution WHERE user_id=$1",
            (user_id,),
        )
        version = (row["max_v"] or 0) + 1 if row else 1

        now = datetime.now(timezone.utc).isoformat()
        await _execute(
            db,
            "INSERT INTO agent_evolution (id, user_id, version, change_log, applied_at) "
            "VALUES ($1, $2, $3, $4, $5)",
            (f"evo_{uuid.uuid4().hex[:12]}", user_id, version, change_log, now),
        )
    return version
