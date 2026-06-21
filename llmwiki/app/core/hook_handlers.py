"""注册 v2 事件钩子的具体 handler。在服务启动时 import 本模块即完成注册。

on_query          → crystallize 回填(质量门控)
on_session_start  → 加载近期 episodic 观察注入会话上下文
on_session_end    → consolidate_session(working→episodic)
on_memory_write   → 矛盾检查 + supersession(覆盖 crystallize 回填路径)
"""
from __future__ import annotations

from app.core import hooks
from app.db.store import Store
from app.core.governance import AuditLog

_store: Store | None = None


async def _get_store() -> Store:
    global _store
    if _store is None:
        _store = await Store.connect()
    return _store


_redis = None


async def _get_redis():
    global _redis
    if _redis is None:
        import redis.asyncio as aioredis
        from app.core.config import get_settings
        _redis = aioredis.from_url(get_settings().redis_url, decode_responses=True)
    return _redis


@hooks.on(hooks.ON_SESSION_START)
async def _load_context_on_session_start(ctx, **_):
    """会话开始:从近期 episodic 观察中加载相关上下文,存入 Redis 供 pipeline 注入。"""
    store = await _get_store()
    async with store.pool.acquire() as con:
        rows = await con.fetch(
            "SELECT content FROM observations "
            "WHERE tenant_id=$1 AND user_id=$2 AND tier='episodic' "
            "ORDER BY created_at DESC LIMIT 5",
            ctx.tenant_id, ctx.user_id)
    if not rows:
        return
    context = "近期会话观察(供参考):\n" + "\n".join(f"- {r['content']}" for r in rows)
    try:
        r = await _get_redis()
        await r.set(f"sess_ctx:{ctx.tenant_id}:{ctx.user_id}:{ctx.session_id}",
                     context, ex=3600)
    except Exception:
        pass  # Redis 不可用不影响主流程


@hooks.on(hooks.ON_QUERY)
async def _crystallize_on_query(ctx, question, answer, verified_ratio, **_):
    from app.memory.crystallize import crystallize
    out = await crystallize(ctx.tenant_id, question, answer, verified_ratio)
    if not out:
        return
    node, facts = out
    store = await _get_store()
    await store.upsert_wiki_nodes(ctx.tenant_id, [node])
    if facts:
        await store.reinforce_or_insert_by_triple(ctx.tenant_id, facts)
        hooks.emit_background(hooks.ON_MEMORY_WRITE, ctx=ctx, facts=facts)
    await AuditLog(store.pool).record(
        ctx.tenant_id, "crystallize", user_id=ctx.user_id, target=node.node_id,
        detail={"facts": len(facts)})


@hooks.on(hooks.ON_SESSION_END)
async def _consolidate_on_session_end(ctx, turns, **_):
    from app.memory.consolidation import consolidate_session
    store = await _get_store()
    await consolidate_session(store, ctx.tenant_id, ctx.user_id, ctx.session_id, turns)


@hooks.on(hooks.ON_MEMORY_WRITE)
async def _check_contradictions_on_write(ctx, facts, **_):
    """写记忆后:检查新 fact 的 (subject, predicate) 是否与已有 fact 矛盾,触发 supersession。
    覆盖 crystallize 回填路径(编译期 contradiction 不覆盖此路径)。"""
    from app.memory.quality import resolve_contradiction

    if not facts:
        return
    store = await _get_store()
    patches = []
    checked: set[tuple[str, str]] = set()
    for f in facts:
        key = (f.subject_entity.lower(), f.predicate.lower())
        if key in checked:
            continue
        checked.add(key)
        async with store.pool.acquire() as con:
            rows = await con.fetch(
                "SELECT fact_id, source_count, last_confirmed, retention, "
                "predicate, contradicts, stale, object_value "
                "FROM facts WHERE tenant_id=$1 "
                "AND lower(subject_entity)=lower($2) "
                "AND lower(predicate)=lower($3) "
                "AND NOT stale LIMIT 20",
                ctx.tenant_id, f.subject_entity, f.predicate)
        if len(rows) < 2:
            continue
        # 只有存在不同 object_value 时才算矛盾
        objects = {r["object_value"].strip().lower() for r in rows}
        if len(objects) < 2:
            continue
        grp = [dict(r) for r in rows]
        result = resolve_contradiction(grp)
        patches.extend(result.get("supersede", []))
    if patches:
        await store.mark_superseded(ctx.tenant_id, patches)
        await AuditLog(store.pool).record(
            ctx.tenant_id, "contradiction_resolve", user_id=ctx.user_id,
            detail={"superseded": len(patches)})
