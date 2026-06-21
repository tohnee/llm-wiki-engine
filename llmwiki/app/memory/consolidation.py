"""记忆巩固分层(借自 llm-wiki v2 的 Consolidation tiers)。

working(原始观察)→ episodic(会话摘要)→ semantic(跨会话事实)→ procedural(工作流模式)。
每升一层:更压缩、更高置信、更长寿。证据累积驱动晋升。

本模块实现 working→episodic(会话结束压缩)与 episodic→semantic(跨会话归并)两步,
procedural 留扩展位(从重复 semantic 中抽工作流)。
"""
from __future__ import annotations

import time
import uuid

from app.core.config import get_settings
from app.db.store import Store
from app.llm.gateway import get_gateway, Priority

_S = get_settings()

_EPISODIC_SYS = "把以下对话压缩成 2-3 条要点观察(每条一句),只输出要点,每行一条,不编号。"
_SEMANTIC_SYS = "以下是多条情景观察。归并出跨会话稳定的结论(去重、合并同类),每行一条,不编号。"


async def _store_obs(store: Store, tenant_id: str, user_id: str, session_id: str,
                     tier: str, content: str, confidence: float) -> str:
    obs_id = f"ob_{uuid.uuid4().hex[:16]}"
    now = time.time()
    async with store.pool.acquire() as con:
        await con.execute(
            """INSERT INTO observations
               (obs_id,tenant_id,user_id,session_id,tier,content,confidence,created_at,last_access)
               VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$8)""",
            obs_id, tenant_id, user_id, session_id, tier, content, confidence, now)
    return obs_id


async def consolidate_session(store: Store, tenant_id: str, user_id: str,
                              session_id: str, turns: list[dict]) -> int:
    """working→episodic:会话结束时把对话压成情景观察。返回写入条数。"""
    if not turns:
        return 0
    convo = "\n".join(f"{t['role']}: {t['content']}" for t in turns[-20:])
    gw = get_gateway()
    resp = await gw.complete(
        tenant_id=tenant_id, model=_S.model_haiku, system=_EPISODIC_SYS,
        user_content=convo, priority=Priority.COMPILE_BATCH, max_tokens=512)
    text = "".join(b.text for b in resp.content if b.type == "text")
    points = [p.strip("-• ").strip() for p in text.splitlines() if p.strip()]
    for p in points:
        await _store_obs(store, tenant_id, user_id, session_id, "episodic", p, 0.6)
    return len(points)


async def promote_to_semantic(store: Store, tenant_id: str, min_episodic: int = 5) -> int:
    """episodic→semantic:跨会话归并稳定结论。返回写入条数。"""
    async with store.pool.acquire() as con:
        rows = await con.fetch(
            "SELECT obs_id,content FROM observations "
            "WHERE tenant_id=$1 AND tier='episodic' AND promoted_to IS NULL LIMIT 100",
            tenant_id)
    if len(rows) < min_episodic:
        return 0
    joined = "\n".join(r["content"] for r in rows)
    gw = get_gateway()
    resp = await gw.complete(
        tenant_id=tenant_id, model=_S.model_sonnet, system=_SEMANTIC_SYS,
        user_content=joined, priority=Priority.COMPILE_BATCH, max_tokens=768)
    text = "".join(b.text for b in resp.content if b.type == "text")
    sem = [p.strip("-• ").strip() for p in text.splitlines() if p.strip()]
    sem_ids = []
    for s in sem:
        sem_ids.append(await _store_obs(store, tenant_id, "system", "", "semantic", s, 0.8))
    # 标记 episodic 已晋升
    if sem_ids:
        async with store.pool.acquire() as con:
            await con.executemany(
                "UPDATE observations SET promoted_to=$2 WHERE tenant_id=$1 AND obs_id=$3",
                [(tenant_id, sem_ids[0], r["obs_id"]) for r in rows])
    return len(sem)
