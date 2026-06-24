"""生产编译 worker:消费 Redis Streams,无状态可水平扩展(K8s + KEDA)。

入口:python -m app.compile.run_worker
消费 compile:L1 流(每条 = 一个文档编译任务),调用 orchestrator 完成 L1–L4。
更细粒度的 per-chunk 并行可把任务拆到各层流;此处以文档级任务为单位,
worker 内部已对 chunk 做并行(orchestrator 的 asyncio.gather),对单机多进程足够。
"""
from __future__ import annotations

import asyncio
import os
import socket

from app.core.tenant import TenantContext
from app.db.store import Store
from app.compile.dag import CompileBus, CompileMsg
from app.compile.manifest import Manifest
from app.compile.orchestrator import compile_document_inline
from app.compile.workers.l0_parse import parse_to_markdown
from app.models.schema import CompileDepth

CONSUMER = f"{socket.gethostname()}-{os.getpid()}"
LEVEL = "L1"   # 文档级任务入口流


async def handle(store: Store, bus: CompileBus, manifest: Manifest, msg: CompileMsg) -> None:
    ctx = TenantContext(tenant_id=msg.tenant_id, user_id="compile", session_id="compile")
    source = msg.payload.get("source_path", "")
    markdown = msg.payload.get("markdown") or await parse_to_markdown(source)
    # 注意: manifest 当前 key = (tenant, chunk_id),未含 document_id。
    # 同一 markdown 多次入库会产生相同 chunk_id → manifest 命中"未变化"→ L2 跳过 →
    # facts/entities/relations 始终为 0。临时禁用 manifest 强制每次全量编译,
    # 待 manifest key 升级为 (tenant, document_id, chunk_id) 后可恢复增量。
    await compile_document_inline(
        store, bus, ctx, msg.document_id, markdown,
        CompileDepth(msg.depth), manifest=None)


async def main() -> None:
    store = await Store.connect()
    bus = await CompileBus.connect()
    manifest = await Manifest.connect()
    print(f"[compile-worker {CONSUMER}] consuming compile:{LEVEL}")
    while True:
        batch = await bus.read(LEVEL, CONSUMER, count=2, block_ms=5000)
        for msg_id, msg in batch:
            try:
                await handle(store, bus, manifest, msg)
                await bus.ack(LEVEL, msg_id)
            except Exception as e:  # noqa: BLE001
                print(f"[compile-worker] job {msg.document_id} failed: {e}")
                await bus.retry_or_dlq(LEVEL, msg_id, msg)


if __name__ == "__main__":
    asyncio.run(main())
