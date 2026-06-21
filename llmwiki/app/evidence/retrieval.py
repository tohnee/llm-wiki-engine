"""混合检索:BM25(tsvector)+ 向量(pgvector)→ RRF 融合 → cross-encoder rerank。

所有查询强制带 tenant_id,并可被 scope(document_ids)收窄——这是 navigation-first 的落点:
KG/navigate 先圈定 scope,检索在 scope 内做,而非全库朴素 topK。
"""
from __future__ import annotations

from app.core.config import get_settings
from app.db.store import Store
from app.llm.embed import embed, rerank
from app.models.schema import EvidenceSpan

_S = get_settings()


def _rrf_merge(rank_lists: list[list[str]], k: int) -> dict[str, float]:
    scores: dict[str, float] = {}
    for rl in rank_lists:
        for rank, sid in enumerate(rl):
            scores[sid] = scores.get(sid, 0.0) + 1.0 / (k + rank + 1)
    return scores


class Retriever:
    def __init__(self, store: Store):
        self.store = store

    async def search(
        self, tenant_id: str, query: str,
        document_ids: list[str] | None = None,
        span_types: list[str] | None = None,
        final_k: int | None = None,
    ) -> list[EvidenceSpan]:
        final_k = final_k or _S.retrieve_final_k
        cand_k = _S.retrieve_candidate_k
        qvec = (await embed([query]))[0]

        scope_sql = ""
        params: list = [tenant_id]
        if document_ids:
            params.append(document_ids)
            scope_sql += f" AND document_id = ANY(${len(params)})"
        if span_types:
            params.append(span_types)
            scope_sql += f" AND span_type = ANY(${len(params)})"

        async with self.store.pool.acquire() as con:
            # 向量召回(当 embedding 可用时)
            vec_ids: list[str] = []
            if any(abs(v) > 1e-9 for v in qvec):
                params_v = params + [str(qvec), cand_k]
                vec_rows = await con.fetch(
                    f"""SELECT span_id FROM spans
                        WHERE tenant_id=$1 {scope_sql}
                        ORDER BY embedding <=> ${len(params)+1}
                        LIMIT ${len(params)+2}""",
                    *params_v,
                )
                vec_ids = [r["span_id"] for r in vec_rows]

            # BM25(tsvector)全文检索 — 使用 websearch_to_tsquery 更好支持中文
            params_b = params + [query, cand_k]
            bm_rows = await con.fetch(
                f"""SELECT span_id FROM spans
                    WHERE tenant_id=$1 {scope_sql}
                      AND tsv @@ plainto_tsquery('simple', ${len(params)+1})
                    ORDER BY ts_rank(tsv, plainto_tsquery('simple', ${len(params)+1})) DESC
                    LIMIT ${len(params)+2}""",
                *params_b,
            )
            bm_ids = [r["span_id"] for r in bm_rows]

        # 图遍历流(v2 第三流):query 向量 → link_entities → neighbors → 收集关联 span_ids
        # 捕获 BM25/向量都错过的结构连接(如"升级 Redis 的影响"沿 depends_on 边找到下游服务)
        graph_ids: list[str] = []
        try:
            if any(abs(v) > 1e-9 for v in qvec):
                cands = await self.store.link_entities(tenant_id, qvec, top_k=5, name_hint=query)
                if cands:
                    seed_ids = [c["entity_id"] for c in cands]
                    subgraph = await self.store.neighbors(tenant_id, seed_ids, hops=1)
                    # 从关系边的 source_span_ids 收集候选 span
                    candidate_span_ids: set[str] = set()
                    for edge in subgraph.get("edges", []):
                        candidate_span_ids.update(edge.get("span_ids") or [])
                    if candidate_span_ids:
                        async with self.store.pool.acquire() as con:
                            if document_ids:
                                g_rows = await con.fetch(
                                    "SELECT span_id FROM spans WHERE tenant_id=$1 "
                                    "AND span_id = ANY($2) AND document_id = ANY($3) LIMIT $4",
                                    tenant_id, list(candidate_span_ids)[:200], document_ids, cand_k)
                            else:
                                g_rows = await con.fetch(
                                    "SELECT span_id FROM spans WHERE tenant_id=$1 "
                                    "AND span_id = ANY($2) LIMIT $3",
                                    tenant_id, list(candidate_span_ids)[:200], cand_k)
                            graph_ids = [r["span_id"] for r in g_rows]
        except Exception:
            pass  # 图遍历失败不影响主检索(BM25+向量仍可用)

        # RRF 三流融合:向量 + BM25 + 图遍历
        streams = [s for s in [vec_ids, bm_ids, graph_ids] if s]
        if len(streams) >= 2:
            fused = _rrf_merge(streams, _S.rrf_k)
            top_ids = sorted(fused, key=fused.get, reverse=True)[:cand_k]
        elif streams:
            # 仅一路可用时(如 embedding 不可用)直接取该路结果
            top_ids = streams[0][:cand_k]
        else:
            top_ids = []

        # 取内容 → rerank
        contents: list[tuple[str, str]] = []
        async with self.store.pool.acquire() as con:
            rows = await con.fetch(
                "SELECT span_id,content,document_id,page FROM spans "
                "WHERE tenant_id=$1 AND span_id = ANY($2)",
                tenant_id, top_ids,
            )
        meta = {r["span_id"]: r for r in rows}
        contents = [(sid, meta[sid]["content"]) for sid in top_ids if sid in meta]

        reranked = rerank(query, contents)[:final_k]
        out = []
        for sid, score in reranked:
            r = meta[sid]
            out.append(EvidenceSpan(
                span_id=sid, document_id=r["document_id"], content=r["content"],
                page=r["page"], score=score,
            ))
        return out
