"""本地编译 demo:把一个 md 文件编译进知识库(inline,渐进 D0→D1)。

用法: python -m scripts.ingest_demo --tenant t1 --doc doc1 --md ./sample.md --depth D1
"""
import argparse
import asyncio

from app.core.tenant import TenantContext
from app.db.store import Store
from app.compile.dag import CompileBus
from app.compile.orchestrator import compile_document_inline
from app.models.schema import CompileDepth


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tenant", required=True)
    ap.add_argument("--doc", required=True)
    ap.add_argument("--md", required=True)
    ap.add_argument("--depth", default="D1", choices=["D0", "D1", "D2"])
    args = ap.parse_args()

    md = open(args.md, encoding="utf-8").read()
    store = await Store.connect()
    bus = await CompileBus.connect()
    ctx = TenantContext(tenant_id=args.tenant, user_id="ingest", session_id="ingest")

    # 先建文档行(简化:直接 upsert documents 略;生产在 ingest 入口做)
    await store.ensure_tenant_partition(args.tenant)
    async with store.pool.acquire() as con:
        await con.execute(
            "INSERT INTO documents (document_id,tenant_id,title,source_uri,depth) "
            "VALUES ($1,$2,$3,$4,$5) ON CONFLICT DO NOTHING",
            args.doc, args.tenant, args.doc, f"local://{args.md}", args.depth)

    await compile_document_inline(store, bus, ctx, args.doc, md, CompileDepth(args.depth))
    print(f"compiled {args.doc} at depth {args.depth}")


if __name__ == "__main__":
    asyncio.run(main())
