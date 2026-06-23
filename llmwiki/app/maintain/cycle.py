"""维护循环(借自 obsidian-wiki 的 archive/rebuild + daily-update),已实现。

Karpathy 洞察:知识管理最贵的是"记账"——人类两周就放弃,AI 不会。做成定时任务。
企业化:obsidian-wiki 默认人确认;此处改为"高风险入人审队列、低风险自动重编"。
"""
from __future__ import annotations

import json
import time

from app.db.store import Store
from app.compile.dag import CompileBus, CompileMsg, unit_hash
from app.maintain.lint import audit_tenant
from app.maintain.crosslink import crosslink_tenant


async def archive_tenant_kg(store: Store, tenant_id: str) -> dict:
    """归档:把导航层导出为 JSON 快照(可上传 S3),用于 rebuild 前留底。"""
    snapshot_id = f"snap_{tenant_id}_{int(time.time())}"
    async with store.pool.acquire() as con:
        facts = await con.fetch("SELECT * FROM facts WHERE tenant_id=$1", tenant_id)
        ents = await con.fetch("SELECT entity_id,name,type,aliases FROM entities WHERE tenant_id=$1", tenant_id)
        rels = await con.fetch("SELECT * FROM relations WHERE tenant_id=$1", tenant_id)
    snapshot = {
        "snapshot_id": snapshot_id, "tenant_id": tenant_id, "ts": int(time.time()),
        "facts": [dict(r) for r in facts],
        "entities": [dict(r) for r in ents],
        "relations": [dict(r) for r in rels],
    }
    # 上传对象存储(S3/MinIO)。此处给落点;生产用 aioboto3 put_object。
    # await s3.put_object(Bucket=..., Key=f"snapshots/{snapshot_id}.json", Body=json.dumps(snapshot))
    return {"snapshot_id": snapshot_id, "facts": len(facts),
            "entities": len(ents), "relations": len(rels),
            "blob_bytes": len(json.dumps(snapshot, default=str))}


async def rebuild_tenant(store: Store, bus: CompileBus, tenant_id: str) -> dict:
    """从 documents 表重投编译任务(选择性重编:bump prompt_version 后用)。"""
    async with store.pool.acquire() as con:
        docs = await con.fetch(
            "SELECT document_id,source_uri,depth FROM documents WHERE tenant_id=$1", tenant_id)
    n = 0
    for d in docs:
        msg = CompileMsg(
            job_id=f"rebuild_{int(time.time())}", tenant_id=tenant_id,
            document_id=d["document_id"], level="L1", unit_id=d["document_id"],
            input_hash=unit_hash(d["source_uri"], "rebuild", "v1"),
            depth=d["depth"], payload={"source_path": d["source_uri"]})
        await bus.submit(msg)
        n += 1
    return {"requeued_documents": n}


async def daily_maintenance(store: Store, tenant_id: str, bus: CompileBus | None = None) -> dict:
    """每日维护(v2 Automation/on_schedule):
    retention decay → lint 体检 → 自愈/人审 → cross-link → episodic→semantic → semantic→procedural 巩固。"""
    from app.memory.consolidation import promote_to_semantic, promote_to_procedural
    from app.memory.quality import self_heal_plan
    from app.core.governance import AuditLog
    from app.core.schema_layer import SchemaStore

    # 加载租户 schema(lint 阈值)
    try:
        _schema_store = await SchemaStore.connect()
        schema = await _schema_store.get(tenant_id)
    except Exception:
        schema = None

    # 1) 记忆衰减(Ebbinghaus 重算 retention/confidence)
    decayed = await store.apply_decay(tenant_id)

    # 2) lint 体检(使用租户 schema 阈值)
    findings = await audit_tenant(store, tenant_id, schema=schema)
    high = [f for f in findings if f.priority >= 1.0]
    low = [f for f in findings if f.priority < 1.0]
    if bus is not None and high:
        for f in high:
            await bus.r.rpush(
                f"review:{tenant_id}",
                json.dumps({"entity": f.entity_name, "rule": f.rule,
                            "detail": f.detail, "priority": round(f.priority, 2)}))

    # 3) cross-link 维护
    cl = await crosslink_tenant(store, tenant_id)

    # 4) episodic→semantic 巩固
    promoted = await promote_to_semantic(store, tenant_id)
    # 4b) semantic→procedural 抽取(可重复工作流识别)
    proc = await promote_to_procedural(store, tenant_id)

    # 5) 审计留痕
    await AuditLog(store.pool).record(
        tenant_id, "daily_maintenance", detail={
            "decayed": decayed, "audited": len(findings),
            "promoted_semantic": promoted, "promoted_procedural": proc,
            "crosslink": cl})

    return {
        "decayed_facts": decayed,
        "audited": len(findings),
        "to_human_review": len(high),
        "auto_fixable": len(low),
        "crosslink": cl,
        "promoted_semantic": promoted,
        "promoted_procedural": proc,
        "top": [(f.entity_name, f.rule, round(f.priority, 2)) for f in findings[:10]],
    }


# ---------------- on_schedule 调度器 ----------------
import asyncio as _asyncio
import os as _os


async def run_scheduler(
    store: Store, bus: CompileBus | None = None,
    interval_sec: int | None = None, tenants: list[str] | None = None,
) -> None:
    """轻量调度循环:每 interval_sec 一次,对每个 tenant emit(ON_SCHEDULE)。

    部署形态:作为独立进程(`python -m app.maintain.scheduler`)或注入到 compile-worker 副驾。
    - interval_sec 默认 86400(每日)。可用环境变量 SCHEDULE_INTERVAL_SEC 覆盖。
    - tenants 不传则取 DB 中所有租户。
    - 失败任何一次循环不会中断 daemon,只 print 错误。
    """
    from app.core import hooks
    from app.core.tenant import TenantContext

    interval = interval_sec or int(_os.getenv("SCHEDULE_INTERVAL_SEC", "86400"))
    print(f"[scheduler] start, interval={interval}s, tenants={tenants or 'auto'}", flush=True)
    while True:
        try:
            if tenants is None:
                async with store.pool.acquire() as con:
                    rows = await con.fetch("SELECT DISTINCT tenant_id FROM documents")
                tenant_list = [r["tenant_id"] for r in rows]
            else:
                tenant_list = list(tenants)
            for t in tenant_list:
                ctx = TenantContext(tenant_id=t, user_id="system", session_id="schedule")
                # 同步触发,handler 内部可 emit_background 异步派发
                await hooks.emit(hooks.ON_SCHEDULE, ctx=ctx, store=store, bus=bus)
        except Exception as e:
            print(f"[scheduler] loop iteration failed: {e}", flush=True)
        await _asyncio.sleep(interval)
