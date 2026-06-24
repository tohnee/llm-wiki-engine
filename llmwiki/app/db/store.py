"""存储访问层(asyncpg)。

安全要点:所有读写方法的第一个参数都是 tenant_id,且 WHERE 子句强制带 tenant_id。
调用方不允许构造不带 tenant_id 的查询。新租户首次写入时自动建立 LIST 分区(物理隔离)。
"""
from __future__ import annotations

import json
from typing import Any, Optional

import asyncpg

from app.core.config import get_settings
from app.models.schema import Chunk, Span, Fact, Entity, Relation, Document, WikiNode
from app.evidence.typed_graph import normalize_relation_type

_S = get_settings()

# 每个新租户分区上需要建立的索引(分区表的索引须建在分区上)
# pgvector hnsw 索引上限 2000 维,本工程 embed_dim=1536(doubao-embedding-vision 2048 维客户端截断)。
_PARTITION_INDEXES = """
CREATE INDEX IF NOT EXISTS {p}_spans_emb ON {p}_spans
    USING hnsw (embedding vector_cosine_ops);
CREATE INDEX IF NOT EXISTS {p}_spans_tsv ON {p}_spans USING gin (tsv);
CREATE INDEX IF NOT EXISTS {p}_spans_doc ON {p}_spans (document_id);
CREATE INDEX IF NOT EXISTS {p}_spans_content_trgm ON {p}_spans USING gin (content gin_trgm_ops);
CREATE INDEX IF NOT EXISTS {p}_chunks_doc ON {p}_chunks (document_id);
CREATE INDEX IF NOT EXISTS {p}_entities_block ON {p}_entities (name_block);
CREATE INDEX IF NOT EXISTS {p}_entities_emb ON {p}_entities
    USING hnsw (embedding vector_cosine_ops);
CREATE INDEX IF NOT EXISTS {p}_facts_subj ON {p}_facts (subject_entity);
CREATE INDEX IF NOT EXISTS {p}_relations_src ON {p}_relations (source_entity);
"""

_PARTITIONED_TABLES = [
    "documents", "chunks", "spans", "facts", "entities", "relations", "wiki_nodes"
]


def _safe_part(tenant_id: str) -> str:
    """分区后缀:仅允许字母数字下划线,防注入。"""
    s = "".join(c if c.isalnum() else "_" for c in tenant_id)
    return f"t_{s}"


class Store:
    def __init__(self, pool: asyncpg.Pool):
        self.pool = pool

    @classmethod
    async def connect(cls) -> "Store":
        pool = await asyncpg.create_pool(_S.pg_dsn, min_size=2, max_size=20)
        return cls(pool)

    async def ensure_tenant_partition(self, tenant_id: str) -> None:
        """幂等地为租户创建所有分区 + 索引。首次写入时调用。"""
        p = _safe_part(tenant_id)
        async with self.pool.acquire() as con:
            async with con.transaction():
                for tbl in _PARTITIONED_TABLES:
                    await con.execute(
                        f"CREATE TABLE IF NOT EXISTS {p}_{tbl} "
                        f"PARTITION OF {tbl} FOR VALUES IN ($tenant$);".replace(
                            "$tenant$", f"'{tenant_id}'"
                        )
                    )
                await con.execute(_PARTITION_INDEXES.format(p=p))

    # ---------------- 写入(批量) ----------------
    async def upsert_document(self, tenant_id: str, document: Document) -> None:
        """幂等创建/更新文档状态行,保证编译状态生命周期可观测。"""
        async with self.pool.acquire() as con:
            await con.execute(
                """INSERT INTO documents
                   (document_id,tenant_id,title,source_uri,status,depth,page_count,compile_error)
                   VALUES ($1,$2,$3,$4,$5,$6,$7,'')
                   ON CONFLICT (tenant_id,document_id) DO UPDATE SET
                     title=EXCLUDED.title, source_uri=EXCLUDED.source_uri,
                     depth=EXCLUDED.depth, page_count=EXCLUDED.page_count,
                     updated_at=now()""",
                document.document_id, tenant_id, document.title, document.source_uri,
                document.status.value if hasattr(document.status, "value") else document.status,
                document.depth.value if hasattr(document.depth, "value") else document.depth,
                document.page_count,
            )

    async def upsert_spans(self, tenant_id: str, spans: list[Span]) -> None:
        rows = [
            (s.span_id, tenant_id, s.chunk_id, s.document_id, s.content, s.page,
             list(s.bbox) if s.bbox else None, s.span_type.value,
             str(s.embedding) if s.embedding else None)
            for s in spans
        ]
        async with self.pool.acquire() as con:
            await con.executemany(
                """INSERT INTO spans
                   (span_id,tenant_id,chunk_id,document_id,content,page,bbox,span_type,embedding)
                   VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9)
                   ON CONFLICT (tenant_id,span_id) DO UPDATE SET
                     content=EXCLUDED.content, embedding=EXCLUDED.embedding""",
                rows,
            )

    async def upsert_chunks(self, tenant_id: str, chunks: list[Chunk]) -> None:
        rows = [
            (c.chunk_id, tenant_id, c.document_id, c.content, c.page_start,
             c.page_end, c.section_path, c.content_hash, c.summary,
             (c.tier.value if c.tier else None))
            for c in chunks
        ]
        async with self.pool.acquire() as con:
            await con.executemany(
                """INSERT INTO chunks
                   (chunk_id,tenant_id,document_id,content,page_start,page_end,
                    section_path,content_hash,summary,tier)
                   VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10)
                   ON CONFLICT (tenant_id,chunk_id) DO UPDATE SET
                     content=EXCLUDED.content, content_hash=EXCLUDED.content_hash,
                     summary=EXCLUDED.summary, tier=EXCLUDED.tier""",
                rows,
            )

    async def upsert_facts(self, tenant_id: str, facts: list[Fact]) -> None:
        import time as _t
        now = _t.time()
        rows = [
            (f.fact_id, tenant_id, f.document_id, f.subject_entity, f.predicate,
             f.object_value, json.dumps(f.qualifiers), f.confidence,
             (f.provenance.value if f.provenance else "extracted"), f.contradicts,
             f.source_count, f.created_at or now, f.last_confirmed or now, f.retention,
             f.superseded_by, f.stale, f.source_span_ids, f.source_hash)
            for f in facts
        ]
        async with self.pool.acquire() as con:
            await con.executemany(
                """INSERT INTO facts
                   (fact_id,tenant_id,document_id,subject_entity,predicate,object_value,
                    qualifiers,confidence,provenance,contradicts,source_count,created_at,
                    last_confirmed,retention,superseded_by,stale,source_span_ids,source_hash)
                   VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16,$17,$18)
                   ON CONFLICT (tenant_id,fact_id) DO UPDATE SET
                     object_value=EXCLUDED.object_value, qualifiers=EXCLUDED.qualifiers,
                     provenance=EXCLUDED.provenance, contradicts=EXCLUDED.contradicts,
                     source_count=facts.source_count+1, last_confirmed=EXCLUDED.last_confirmed,
                     retention=1.0""",
                rows,
            )

    async def reinforce_or_insert_by_triple(self, tenant_id: str, facts: list[Fact]) -> None:
        """按 (subject,predicate,object) 去重:已存在则强化(source_count++/retention 重置),
        否则插入。实现 v2 的"reinforcement"(同一事实多来源 → 置信增强)。"""
        import time as _t
        now = _t.time()
        async with self.pool.acquire() as con:
            for f in facts:
                existing = await con.fetchrow(
                    """SELECT fact_id,source_count FROM facts WHERE tenant_id=$1
                       AND lower(subject_entity)=lower($2) AND lower(predicate)=lower($3)
                       AND lower(object_value)=lower($4) LIMIT 1""",
                    tenant_id, f.subject_entity, f.predicate, f.object_value)
                if existing:
                    await con.execute(
                        """UPDATE facts SET source_count=source_count+1,last_confirmed=$3,
                           retention=1.0 WHERE tenant_id=$1 AND fact_id=$2""",
                        tenant_id, existing["fact_id"], now)
                else:
                    await con.execute(
                        """INSERT INTO facts (fact_id,tenant_id,document_id,subject_entity,
                           predicate,object_value,qualifiers,confidence,provenance,contradicts,
                           source_count,created_at,last_confirmed,retention,stale,source_span_ids,source_hash)
                           VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,1,$11,$11,1.0,false,$12,$13)""",
                        f.fact_id, tenant_id, f.document_id, f.subject_entity, f.predicate,
                        f.object_value, json.dumps(f.qualifiers), f.confidence,
                        (f.provenance.value if f.provenance else "inferred"), f.contradicts,
                        now, f.source_span_ids, f.source_hash)

    async def apply_decay(self, tenant_id: str, batch: int = 1000) -> int:
        """定时衰减:按 Ebbinghaus 重算 retention 与 confidence。返回更新条数。"""
        from app.memory.lifecycle import decayed_confidence
        async with self.pool.acquire() as con:
            rows = await con.fetch(
                "SELECT fact_id,predicate,source_count,last_confirmed,contradicts,stale "
                "FROM facts WHERE tenant_id=$1 AND NOT stale LIMIT $2", tenant_id, batch)
            updates = []
            for r in rows:
                d = dict(r); d["contradicts"] = r["contradicts"]
                ret, conf = decayed_confidence(d)
                updates.append((tenant_id, r["fact_id"], ret, conf))
            if updates:
                await con.executemany(
                    "UPDATE facts SET retention=$3,confidence=$4 WHERE tenant_id=$1 AND fact_id=$2",
                    updates)
            return len(updates)

    async def mark_superseded(self, tenant_id: str, patches: list[dict]) -> None:
        async with self.pool.acquire() as con:
            await con.executemany(
                "UPDATE facts SET superseded_by=$3,stale=true WHERE tenant_id=$1 AND fact_id=$2",
                [(tenant_id, p["fact_id"], p["superseded_by"]) for p in patches])

    async def upsert_entities(self, tenant_id: str, entities: list[Entity], block_keys: dict[str, str]) -> None:
        """block_keys: {entity_id: name_block}。mention/document 用数组并集合并。"""
        rows = [
            (e.entity_id, tenant_id, e.name, e.aliases, e.type, e.description,
             e.mention_span_ids, e.document_ids, block_keys.get(e.entity_id, ""),
             str(e.embedding) if e.embedding else None)
            for e in entities
        ]
        async with self.pool.acquire() as con:
            await con.executemany(
                """INSERT INTO entities
                   (entity_id,tenant_id,name,aliases,type,description,
                    mention_span_ids,document_ids,name_block,embedding)
                   VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10)
                   ON CONFLICT (tenant_id,entity_id) DO UPDATE SET
                     aliases = (SELECT ARRAY(SELECT DISTINCT unnest(entities.aliases || EXCLUDED.aliases))),
                     mention_span_ids = (SELECT ARRAY(SELECT DISTINCT unnest(entities.mention_span_ids || EXCLUDED.mention_span_ids))),
                     document_ids = (SELECT ARRAY(SELECT DISTINCT unnest(entities.document_ids || EXCLUDED.document_ids))),
                     description = COALESCE(NULLIF(EXCLUDED.description,''), entities.description)""",
                rows,
            )

    async def upsert_relations(self, tenant_id: str, relations: list[Relation]) -> None:
        """关系级多源置信(v2):同三元组(source,relation_type,target)只保留一条,
        重复抽到则 source_count++、last_confirmed=now、confidence 按 1-1/(1+n) 重算、
        合并 source_span_ids(去重)。新三元组则正常 INSERT。
        """
        import time as _t
        if not relations:
            return
        now = _t.time()
        async with self.pool.acquire() as con:
            async with con.transaction():
                for r in relations:
                    rel_type = normalize_relation_type(r.relation_type)
                    existing = await con.fetchrow(
                        """SELECT relation_id, source_count, source_span_ids
                           FROM relations
                           WHERE tenant_id=$1 AND source_entity=$2
                             AND relation_type=$3 AND target_entity=$4
                           LIMIT 1""",
                        tenant_id, r.source_entity, rel_type, r.target_entity)
                    if existing:
                        new_n = (existing["source_count"] or 1) + 1
                        merged_spans = list(dict.fromkeys(
                            list(existing["source_span_ids"] or []) + list(r.source_span_ids or [])))
                        new_conf = 1.0 - 1.0 / (1.0 + new_n)  # 与 fact 一致的多源置信公式
                        await con.execute(
                            """UPDATE relations
                               SET source_count=$1, last_confirmed=$2,
                                   source_span_ids=$3, confidence=$4
                               WHERE tenant_id=$5 AND relation_id=$6""",
                            new_n, now, merged_spans, new_conf,
                            tenant_id, existing["relation_id"])
                    else:
                        await con.execute(
                            """INSERT INTO relations
                               (relation_id,tenant_id,source_entity,relation_type,target_entity,
                                source_span_ids,confidence,source_count,last_confirmed)
                               VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9)
                               ON CONFLICT (tenant_id,relation_id) DO NOTHING""",
                            r.relation_id, tenant_id, r.source_entity, rel_type,
                            r.target_entity, r.source_span_ids, r.confidence, 1, now)

    async def upsert_wiki_nodes(self, tenant_id: str, nodes: list) -> None:
        rows = [
            (n.node_id, tenant_id, n.title, n.content, n.entity_id, n.children,
             json.dumps(n.provenance_mix), (n.tier.value if n.tier else None))
            for n in nodes
        ]
        async with self.pool.acquire() as con:
            await con.executemany(
                """INSERT INTO wiki_nodes
                   (node_id,tenant_id,title,content,entity_id,children,provenance_mix,tier)
                   VALUES ($1,$2,$3,$4,$5,$6,$7,$8)
                   ON CONFLICT (tenant_id,node_id) DO UPDATE SET
                     content=EXCLUDED.content, provenance_mix=EXCLUDED.provenance_mix""",
                rows,
            )

    # ---------------- 读取(强制 tenant_id) ----------------
    async def get_span(self, tenant_id: str, span_id: str) -> Optional[dict]:
        async with self.pool.acquire() as con:
            row = await con.fetchrow(
                "SELECT s.span_id, s.document_id, s.content, s.page, s.section_path "
                "FROM spans s LEFT JOIN chunks c USING(tenant_id,chunk_id) "
                "WHERE s.tenant_id=$1 AND s.span_id=$2",
                tenant_id, span_id,
            )
            return dict(row) if row else None

    async def get_chunk_for_span(self, tenant_id: str, span_id: str) -> Optional[dict]:
        async with self.pool.acquire() as con:
            row = await con.fetchrow(
                """SELECT c.chunk_id,c.content,c.section_path,c.document_id
                   FROM spans s JOIN chunks c USING(tenant_id,chunk_id)
                   WHERE s.tenant_id=$1 AND s.span_id=$2""",
                tenant_id, span_id,
            )
            return dict(row) if row else None

    async def existing_chunk_hashes(self, tenant_id: str, document_id: str) -> dict[str, str]:
        """增量编译:返回 {chunk_id: content_hash},用于跳过未变化单元。"""
        async with self.pool.acquire() as con:
            rows = await con.fetch(
                "SELECT chunk_id,content_hash FROM chunks WHERE tenant_id=$1 AND document_id=$2",
                tenant_id, document_id,
            )
            return {r["chunk_id"]: r["content_hash"] for r in rows}

    async def set_doc_status(self, tenant_id: str, document_id: str, status: str, error: str = "") -> None:
        async with self.pool.acquire() as con:
            await con.execute(
                """UPDATE documents SET status=$3, compile_error=$4, updated_at=now()
                   WHERE tenant_id=$1 AND document_id=$2""",
                tenant_id, document_id, status, error[:4000],
            )

    async def entity_candidates_in_block(
        self, tenant_id: str, name_block: str
    ) -> list[dict]:
        """Entity Resolution: 只取同 blocking 桶内的候选,避免 O(n^2)。"""
        async with self.pool.acquire() as con:
            rows = await con.fetch(
                "SELECT entity_id,name,aliases,embedding FROM entities "
                "WHERE tenant_id=$1 AND name_block=$2",
                tenant_id, name_block,
            )
            return [dict(r) for r in rows]

    async def drop_tenant(self, tenant_id: str) -> None:
        """数据生命周期:物理删除该租户所有分区(不可逆)。配合 AuthStore.purge_tenant。"""
        p = _safe_part(tenant_id)
        async with self.pool.acquire() as con:
            async with con.transaction():
                for tbl in _PARTITIONED_TABLES:
                    await con.execute(f"DROP TABLE IF EXISTS {p}_{tbl} CASCADE")

    # ---------------- KG 导航(关系图遍历,强制 tenant_id) ----------------
    async def link_entities(
        self, tenant_id: str, query_vec: list[float], top_k: int = 5,
        name_hint: str | None = None,
    ) -> list[dict]:
        """实体链接:用 query 向量在 entities 上做相似检索(优于字符串匹配),
        可叠加名字模糊命中提升召回。返回候选实体。"""
        async with self.pool.acquire() as con:
            rows = await con.fetch(
                """SELECT entity_id, name, type, document_ids,
                          1 - (embedding <=> $2) AS sim
                   FROM entities
                   WHERE tenant_id=$1 AND embedding IS NOT NULL
                   ORDER BY embedding <=> $2
                   LIMIT $3""",
                tenant_id, str(query_vec), top_k)
            cands = [dict(r) for r in rows]
            if name_hint:
                nrows = await con.fetch(
                    "SELECT entity_id,name,type,document_ids,1.0 AS sim FROM entities "
                    "WHERE tenant_id=$1 AND name ILIKE '%'||$2||'%' LIMIT $3",
                    tenant_id, name_hint, top_k)
                seen = {c["entity_id"] for c in cands}
                for r in nrows:
                    if r["entity_id"] not in seen:
                        cands.append(dict(r))
        return cands

    async def neighbors(
        self, tenant_id: str, entity_ids: list[str], hops: int = 1,
        max_per_hop: int = 50,
    ) -> dict:
        """从给定实体出发,沿 relations 做 BFS 扩展 hops 跳,返回子图 {nodes, edges}。
        多跳问答的骨架:把相关实体及其文档全部拉进 scope。"""
        if not entity_ids:
            return {"nodes": [], "edges": []}
        frontier = set(entity_ids)
        visited: set[str] = set()
        edges: list[dict] = []
        async with self.pool.acquire() as con:
            for _ in range(max(1, hops)):
                if not frontier:
                    break
                rows = await con.fetch(
                    """SELECT source_entity, relation_type, target_entity, source_span_ids
                       FROM relations
                       WHERE tenant_id=$1
                         AND (source_entity = ANY($2) OR target_entity = ANY($2))
                       LIMIT $3""",
                    tenant_id, list(frontier), max_per_hop)
                visited |= frontier
                next_frontier: set[str] = set()
                for r in rows:
                    rel_type = normalize_relation_type(r["relation_type"])
                    edges.append({
                        "source": r["source_entity"], "relation": rel_type,
                        "relation_type": rel_type, "target": r["target_entity"],
                        "span_ids": r["source_span_ids"]})
                    for nid in (r["source_entity"], r["target_entity"]):
                        if nid not in visited:
                            next_frontier.add(nid)
                frontier = next_frontier
            all_ids = list(visited | frontier)
            node_rows = await con.fetch(
                "SELECT entity_id,name,type,document_ids FROM entities "
                "WHERE tenant_id=$1 AND entity_id = ANY($2)",
                tenant_id, all_ids)
        # 去重边
        seen_e = set()
        uniq_edges = []
        for e in edges:
            k = (e["source"], e["relation"], e["target"])
            if k not in seen_e:
                seen_e.add(k); uniq_edges.append(e)
        return {"nodes": [dict(r) for r in node_rows], "edges": uniq_edges}

    async def typed_edges(
        self, tenant_id: str, relation_types: list[str] | None = None,
        entity_ids: list[str] | None = None, limit: int = 200,
    ) -> list[dict]:
        """Return ontology-normalized typed edges for agent traversal and UI filtering."""
        rels = [normalize_relation_type(r) for r in relation_types] if relation_types else None
        async with self.pool.acquire() as con:
            clauses = ["tenant_id=$1"]
            params: list = [tenant_id]
            if rels:
                params.append(rels); clauses.append(f"relation_type = ANY(${len(params)})")
            if entity_ids:
                params.append(entity_ids)
                clauses.append(f"(source_entity = ANY(${len(params)}) OR target_entity = ANY(${len(params)}))")
            params.append(limit)
            rows = await con.fetch(
                f"""SELECT relation_id,source_entity,relation_type,target_entity,source_span_ids,confidence,source_count
                    FROM relations WHERE {' AND '.join(clauses)} LIMIT ${len(params)}""",
                *params)
        return [{
            "relation_id": r["relation_id"], "source": r["source_entity"],
            "relation": normalize_relation_type(r["relation_type"]),
            "relation_type": normalize_relation_type(r["relation_type"]),
            "target": r["target_entity"], "span_ids": r["source_span_ids"],
            "confidence": r["confidence"], "source_count": r["source_count"],
        } for r in rows]

    async def export_graph(self, tenant_id: str) -> dict:
        """导出全租户 typed KG 为 {nodes, edges},供 graph 导出/可视化。"""
        async with self.pool.acquire() as con:
            nodes = await con.fetch(
                "SELECT entity_id,name,type FROM entities WHERE tenant_id=$1", tenant_id)
        edges = await self.typed_edges(tenant_id, limit=10000)
        return {"nodes": [dict(r) for r in nodes], "edges": edges}
