"""端到端编译测试:直接调用 orchestrator 验证 L1-L4 全流程。"""
import asyncio
import sys
import os

# 确保加载环境变量
os.environ.setdefault("EMBED_MOCK", "1")
os.environ.setdefault("LLM_MOCK", "1")
os.environ.setdefault("LLM_PROVIDER", "openai")

from app.core.tenant import TenantContext
from app.db.store import Store
from app.compile.dag import CompileBus
from app.compile.manifest import Manifest
from app.compile.orchestrator import compile_document_inline
from app.models.schema import CompileDepth


async def test():
    store = await Store.connect()
    bus = await CompileBus.connect()
    manifest = await Manifest.connect()
    ctx = TenantContext(tenant_id="t1", user_id="compile", session_id="compile")
    doc_id = "doc_test_e2e_001"
    md = """# 项目报告

## 预算
项目Alpha的总预算为800万元。实际支出900万元,超支100万元。

## 团队
项目Alpha的团队有15名工程师。负责人是李四。

## 供应商
项目Alpha的主要供应商是Gamma公司,提供设备价值400万元。
"""
    print(f"compiling {doc_id}...", flush=True)
    try:
        await compile_document_inline(
            store, bus, ctx, doc_id, md, CompileDepth.D2, manifest=manifest)
        print("compile done", flush=True)
    except Exception as e:
        import traceback
        traceback.print_exc()
        print(f"ERROR: {e}", flush=True)
        return

    # 检查结果
    chunks = await store.list_chunks("t1", doc_id)
    print(f"chunks: {len(chunks)}", flush=True)
    for c in chunks:
        print(f"  chunk {c.chunk_id}: {c.content[:50]}...", flush=True)

    # 检查 entities 和 facts
    ents = await store.list_entities("t1")
    print(f"entities: {len(ents)}", flush=True)
    for e in ents:
        print(f"  {e.entity_id}: {e.name} ({e.type})", flush=True)

    facts = await store.list_facts("t1")
    print(f"facts: {len(facts)}", flush=True)
    for f in facts:
        print(f"  {f.subject_entity} --{f.predicate}--> {f.object_value}", flush=True)


if __name__ == "__main__":
    asyncio.run(test())
