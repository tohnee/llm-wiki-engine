"""编译编排器:L0–L4 完整串联,所有产物落库。

inline 版(单进程,渐进编译/小文档/本地开发)。生产用 run_worker.py 消费 Redis Streams。
"""
from __future__ import annotations

import asyncio

from app.core.config import get_settings
from app.core.tenant import TenantContext
from app.core.schema_layer import SchemaStore, TenantSchema
from app.db.store import Store
from app.models.schema import DocStatus, CompileDepth, Fact, Entity
from app.compile.dag import CompileBus
from app.compile.manifest import Manifest, ChunkArtifacts
from app.compile.workers.l1_chunk_span import build_chunks_and_spans
from app.compile.workers.l2_extract import extract_chunk, block_key
from app.compile.workers.l3_resolve_relation import resolve_entity, extract_relations
from app.compile.workers.l4_wiki import render_wiki_node
from app.compile.contradiction import detect_contradictions
from app.llm.embed import embed
from app.llm.gateway import Priority

_S = get_settings()


async def compile_document_inline(
    store: Store, bus: CompileBus, ctx: TenantContext,
    document_id: str, markdown: str, depth: CompileDepth = CompileDepth.D1,
    manifest: Manifest | None = None, schema: TenantSchema | None = None,
) -> dict:
    """编译入口。
    schema: 可选;不传则按 tenant_id 自动从 SchemaStore 加载(失败回退默认)。
    """
    tenant_id = ctx.tenant_id
    # ---- 加载 schema(BUG-1 修复):D2 路径与 L2/L3 都需要,顶部一次取定 ----
    if schema is None:
        try:
            schema_store = await SchemaStore.connect()
            schema = await schema_store.get(tenant_id)
        except Exception as e:
            print(f"[compile] load schema failed (fallback to default): {e}", flush=True)
            schema = TenantSchema(tenant_id=tenant_id)
    await store.ensure_tenant_partition(tenant_id)
    await store.set_doc_status(tenant_id, document_id, DocStatus.PARSING.value)

    # ---- L1: chunk/span + embedding ----
    chunks, spans = build_chunks_and_spans(tenant_id, document_id, markdown)
    span_by_chunk = {c.chunk_id: [s for s in spans if s.chunk_id == c.chunk_id] for c in chunks}

    # 增量:跳过 hash 未变化的 chunk(manifest 提供精确失效)
    # BUG FIX: 此前用 stale_artifacts() 返回 None 判断"未变化",但该方法对"新 chunk"
    #   (无 manifest 记录)也返回 None,导致新文档全部 chunk 被跳过,L2 抽取不执行。
    #   修正:直接用 manifest.get() 区分"新 chunk"(prev is None → 需编译)与
    #   "未变化"(prev 存在且 hash 一致 → 跳过)。
    if manifest:
        changed = []
        for c in chunks:
            prev = await manifest.get(tenant_id, c.chunk_id)
            if prev and prev.content_hash == c.content_hash:
                continue  # hash 一致,真正未变化,跳过
            changed.append(c)  # 新 chunk(prev=None)或 hash 变化,需编译
    else:
        existing = await store.existing_chunk_hashes(tenant_id, document_id)
        changed = [c for c in chunks if existing.get(c.chunk_id) != c.content_hash]

    await store.upsert_chunks(tenant_id, chunks)
    await store.upsert_spans(tenant_id, spans)
    await store.set_doc_status(tenant_id, document_id, DocStatus.QUERYABLE_COARSE.value)
    # tier-0 摘要质量:对变化 chunk 生成语义摘要(覆盖启发式),并回写
    if changed:
        from app.compile.workers.summarize import generate_summaries
        await generate_summaries(tenant_id, changed, max_chars=schema.summary_max_chars)
        await store.upsert_chunks(tenant_id, changed)
    if depth == CompileDepth.D0:
        return {"chunks": len(chunks), "spans": len(spans), "depth": "D0"}

    # ---- L2: 仅对变化 chunk 抽 fact/entity ----
    # 大文档(变化 chunk 多)走 Batch API:成本减半、不占交互配额;小文档保持实时低延迟。
    # OpenAI 兼容模式不支持 batch,强制走实时路径。
    BATCH_THRESHOLD = 30
    _use_batch = len(changed) >= BATCH_THRESHOLD and _S.llm_provider.lower() != "openai"
    all_facts: list[Fact] = []
    all_entities: list[Entity] = []
    chunk_facts: dict[str, list[str]] = {}
    chunk_entities: dict[str, list[str]] = {}
    persist_entities: list[Entity] = []  # 在 try 外定义,确保 return 时可访问

    # 用 try/except 包裹 L2-L4,任何失败不影响 L1 产物的可查询性
    try:
        if _use_batch:
            from app.compile.workers.l2_extract import batch_extract_document
            chunks_spans = [(c.chunk_id, c.content, span_by_chunk[c.chunk_id]) for c in changed]
            batch_out = await batch_extract_document(tenant_id, document_id, chunks_spans, schema=schema)
            for c in changed:
                facts, ents = batch_out.get(c.chunk_id, ([], []))
                all_facts.extend(facts); all_entities.extend(ents)
                chunk_facts[c.chunk_id] = [f.fact_id for f in facts]
                chunk_entities[c.chunk_id] = [e.entity_id for e in ents]
        else:
            sem = asyncio.Semaphore(4)  # 并发=4,避免 API 限流(429)

            async def _one(chunk):
                async with sem:
                    try:
                        return await asyncio.wait_for(
                            extract_chunk(
                                tenant_id, document_id, chunk.content, span_by_chunk[chunk.chunk_id],
                                priority=Priority.COMPILE_REALTIME, schema=schema),
                            timeout=120.0,  # 单 chunk 超时 120s
                        )
                    except asyncio.TimeoutError:
                        print(f"[compile] chunk {chunk.chunk_id} extract timed out, skipping", flush=True)
                        return [], []
                    except Exception as e:
                        print(f"[compile] chunk {chunk.chunk_id} extract failed: {e}, skipping", flush=True)
                        return [], []

            results = await asyncio.gather(*[_one(c) for c in changed]) if changed else []
            for chunk, (facts, ents) in zip(changed, results):
                all_facts.extend(facts); all_entities.extend(ents)
                chunk_facts[chunk.chunk_id] = [f.fact_id for f in facts]
                chunk_entities[chunk.chunk_id] = [e.entity_id for e in ents]

        # ---- L3: entity resolution(blocking)→ canonical 映射 ----
        if all_entities:
            try:
                ent_vecs = await embed([e.name + " " + e.type for e in all_entities])
                for e, v in zip(all_entities, ent_vecs):
                    e.embedding = v
            except Exception as embed_err:
                print(f"[compile] entity embedding failed (non-fatal): {embed_err}", flush=True)
        name_to_canonical: dict[str, str] = {}
        block_keys: dict[str, str] = {}
        for e in all_entities:
            bk = block_key(e.name, e.type)
            cands = await store.entity_candidates_in_block(tenant_id, bk)
            cid, is_new = await resolve_entity(tenant_id, e, cands)
            name_to_canonical[e.name.lower()] = cid
            if is_new:
                e.entity_id = cid
                block_keys[cid] = bk
                persist_entities.append(e)

        # fact 的 subject/object 重指向 canonical(按名匹配)
        for f in all_facts:
            f.subject_entity = name_to_canonical.get(f.subject_entity.lower(), f.subject_entity)
            f.object_value = name_to_canonical.get(f.object_value.lower(), f.object_value)

        # ---- 矛盾检测 + 溯源三态 ----
        all_facts = await detect_contradictions(tenant_id, all_facts)
        from collections import defaultdict
        from app.memory.quality import resolve_contradiction
        import time as _t
        _now = _t.time()
        groups = defaultdict(list)
        for f in all_facts:
            if f.provenance and f.provenance.value == "ambiguous":
                groups[(f.subject_entity.lower(), f.predicate.lower())].append({
                    "fact_id": f.fact_id, "source_count": f.source_count,
                    "last_confirmed": f.last_confirmed or _now, "predicate": f.predicate,
                    "contradicts": f.contradicts, "stale": f.stale})
        supersede_patches = []
        for grp in groups.values():
            if len(grp) >= 2:
                supersede_patches += resolve_contradiction(grp)["supersede"]
        stale_ids = {p["fact_id"] for p in supersede_patches}
        for f in all_facts:
            if f.fact_id in stale_ids:
                f.stale = True
                f.superseded_by = next(p["superseded_by"] for p in supersede_patches if p["fact_id"] == f.fact_id)

        # ---- 落库 ----
        if persist_entities:
            await store.upsert_entities(tenant_id, persist_entities, block_keys)
        await store.upsert_facts(tenant_id, all_facts)

        # ---- manifest 记录(精确增量) ----
        if manifest:
            for c in changed:
                await manifest.record(tenant_id, ChunkArtifacts(
                    chunk_id=c.chunk_id, content_hash=c.content_hash,
                    fact_ids=chunk_facts.get(c.chunk_id, []),
                    entity_ids=chunk_entities.get(c.chunk_id, [])))

        # ---- L4: relation + wiki render(仅 D2) ----
        if depth == CompileDepth.D2 and persist_entities:
            facts_summary = "\n".join(
                f"{f.subject_entity} {f.predicate} {f.object_value}" for f in all_facts[:200])
            rels = await extract_relations(tenant_id, persist_entities, facts_summary, schema=schema)
            if rels:
                await store.upsert_relations(tenant_id, rels)
            nodes = []
            for e in persist_entities[:50]:
                ef = [f for f in all_facts if f.subject_entity == e.entity_id]
                er = [r for r in rels if e.entity_id in (r.source_entity, r.target_entity)]
                nodes.append(await render_wiki_node(tenant_id, e, ef, er))
            if nodes:
                await store.upsert_wiki_nodes(tenant_id, nodes)

        await store.set_doc_status(tenant_id, document_id, DocStatus.QUERYABLE_FULL.value)
    except Exception as e:
        print(f"[compile] L2-L4 pipeline failed for doc {document_id}, keeping queryable_coarse: {e}", flush=True)
        import traceback
        traceback.print_exc()

    return {
        "chunks": len(chunks), "spans": len(spans),
        "facts": len(all_facts), "entities": len(persist_entities),
        "ambiguous": sum(1 for f in all_facts if f.provenance and f.provenance.value == "ambiguous"),
        "depth": depth.value,
    }
