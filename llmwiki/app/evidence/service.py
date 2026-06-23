"""Evidence Service:6 个只读工具,同时服务 Fast QA 与 Agentic QA。

安全核心:tenant_id 从内部签名 header 解出并强制注入,忽略 body 中任何 tenant 字段。
工具面只读、无副作用 → 问答 agent 无需 sandbox,逻辑隔离 + 服务端 ACL 即足够。

工具:
  POST /navigate      KG 入口:意图→定位 entity/section→给出候选 scope(document_ids)
  POST /search        scope 内 span 级混合检索
  POST /read_span     取原文 span(citation 落点)
  POST /expand        span→parent chunk 上下文
  POST /lookup_entity 实体卡 + 跨文档 mention
  POST /get_toc       文档结构
"""
from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from app.core.tenant import verify_internal_header, TenantContext
from app.db.store import Store
from app.evidence.retrieval import Retriever

_store: Store | None = None
_retriever: Retriever | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _store, _retriever
    from app.core.security_guard import enforce_production_secrets
    enforce_production_secrets(required_keys=("INTERNAL_HMAC_SECRET",))
    _store = await Store.connect()
    _retriever = Retriever(_store)
    yield


app = FastAPI(title="LLM-Wiki Evidence Service", lifespan=lifespan)

from app.core.observability import setup_logging, install_metrics_route  # noqa: E402
setup_logging("evidence")
install_metrics_route(app)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


async def _ctx(x_internal_auth: str = Header(...)) -> TenantContext:
    try:
        return verify_internal_header(x_internal_auth)
    except PermissionError as e:
        raise HTTPException(status_code=401, detail=str(e))


# ---------------- 请求体(注意:不含 tenant_id;服务端注入) ----------------
class NavigateReq(BaseModel):
    query: str
    hops: int = 1                    # KG 邻域扩展跳数(多跳问答调大)

class NeighborsReq(BaseModel):
    entity_ids: list[str]
    hops: int = 1

class SearchReq(BaseModel):
    query: str
    document_ids: list[str] | None = None
    span_types: list[str] | None = None
    k: int | None = None
    index_only: bool = False        # 强制只走 tier-0 摘要扫描("quick answer")

class ReadSpanReq(BaseModel):
    doc_id: str
    span_id: str

class ExpandReq(BaseModel):
    span_id: str

class LookupEntityReq(BaseModel):
    name: str | None = None
    entity_id: str | None = None

class TocReq(BaseModel):
    doc_id: str


@app.post("/navigate")
async def navigate(req: NavigateReq, x_internal_auth: str = Header(...)):
    ctx = await _ctx(x_internal_auth)
    # 1) 实体链接:用 query 向量在 entities 上检索(优于字符串 ILIKE),叠加名字模糊召回
    from app.llm.embed import embed
    qvec = embed([req.query])[0]
    cands = await _store.link_entities(ctx.tenant_id, qvec, top_k=5, name_hint=req.query)
    if not cands:
        return {"scope_document_ids": [], "entities": [], "edges": [], "wiki_hints": []}

    seed_ids = [c["entity_id"] for c in cands]
    # 2) KG 邻域扩展:沿 relations BFS 1~2 跳,把相关实体与文档全部拉进 scope(多跳骨架)
    subgraph = await _store.neighbors(ctx.tenant_id, seed_ids, hops=req.hops)

    docs: set[str] = set()
    for c in cands:
        docs.update(c.get("document_ids") or [])
    for n in subgraph["nodes"]:
        docs.update(n.get("document_ids") or [])

    # 3) wiki 提示(让 L4 wiki 产物被消费)
    node_ids = [n["entity_id"] for n in subgraph["nodes"]] or seed_ids
    async with _store.pool.acquire() as con:
        wrows = await con.fetch(
            "SELECT title,tier,provenance_mix FROM wiki_nodes "
            "WHERE tenant_id=$1 AND entity_id=ANY($2) LIMIT 10",
            ctx.tenant_id, node_ids)
    wiki = [{"title": w["title"], "tier": w["tier"], "provenance_mix": w["provenance_mix"]}
            for w in wrows]

    return {
        "scope_document_ids": sorted(docs),
        "entities": [{"entity_id": c["entity_id"], "name": c["name"],
                      "type": c["type"], "sim": round(float(c.get("sim", 0)), 3)} for c in cands],
        "edges": subgraph["edges"],          # ★ 关系边现在返回了(第3题:关系展示)
        "wiki_hints": wiki,
    }


@app.post("/neighbors")
async def neighbors(req: NeighborsReq, x_internal_auth: str = Header(...)):
    """关系子图接口:给定实体,返回 hops 跳邻域 {nodes, edges}。
    同时服务多跳取证与前端图可视化。"""
    ctx = await _ctx(x_internal_auth)
    return await _store.neighbors(ctx.tenant_id, req.entity_ids, hops=req.hops)


@app.get("/graph/export")
async def graph_export(fmt: str = "json", x_internal_auth: str = Header(...)):
    """导出全租户 KG:fmt = json | graphml | cypher | html。"""
    ctx = await _ctx(x_internal_auth)
    from app.evidence.graph_export import export
    graph = await _store.export_graph(ctx.tenant_id)
    if fmt not in ("json", "graphml", "cypher", "html"):
        raise HTTPException(400, "fmt must be json|graphml|cypher|html")
    return {"format": fmt, "node_count": len(graph["nodes"]),
            "edge_count": len(graph["edges"]), "data": export(graph, fmt)}


@app.get("/status")
async def status(x_internal_auth: str = Header(...)):
    """知识库健康洞察(规模/hubs/orphans/ambiguous 比例)。供前端面板。"""
    ctx = await _ctx(x_internal_auth)
    from app.maintain.lint import wiki_status
    return await wiki_status(_store, ctx.tenant_id)


@app.post("/search")
async def search(req: SearchReq, x_internal_auth: str = Header(...)):
    ctx = await _ctx(x_internal_auth)
    from app.evidence.tiered import tiered_search
    result = await tiered_search(
        _store, ctx.tenant_id, req.query,
        document_ids=req.document_ids, index_only=req.index_only, final_k=req.k)
    # tier-0 命中:直接给索引级回答(标注未读正文);否则给 span 候选
    if result["tier"] == 0:
        return {"tier": 0, "answer": result["answer"], "note": result["note"], "results": []}
    return {"tier": 1, "results": result["spans"]}


@app.post("/read_span")
async def read_span(req: ReadSpanReq, x_internal_auth: str = Header(...)):
    ctx = await _ctx(x_internal_auth)
    span = await _store.get_span(ctx.tenant_id, req.span_id)
    if not span or span["document_id"] != req.doc_id:
        raise HTTPException(404, "span not found in tenant scope")
    return span


@app.post("/expand")
async def expand(req: ExpandReq, x_internal_auth: str = Header(...)):
    ctx = await _ctx(x_internal_auth)
    chunk = await _store.get_chunk_for_span(ctx.tenant_id, req.span_id)
    if not chunk:
        raise HTTPException(404, "span not found")
    return chunk


@app.post("/lookup_entity")
async def lookup_entity(req: LookupEntityReq, x_internal_auth: str = Header(...)):
    ctx = await _ctx(x_internal_auth)
    async with _store.pool.acquire() as con:
        if req.entity_id:
            row = await con.fetchrow(
                "SELECT * FROM entities WHERE tenant_id=$1 AND entity_id=$2",
                ctx.tenant_id, req.entity_id)
        else:
            row = await con.fetchrow(
                "SELECT * FROM entities WHERE tenant_id=$1 AND name ILIKE $2 LIMIT 1",
                ctx.tenant_id, req.name)
    if not row:
        raise HTTPException(404, "entity not found")
    return {
        "entity_id": row["entity_id"], "name": row["name"], "type": row["type"],
        "aliases": row["aliases"], "description": row["description"],
        "mention_span_ids": row["mention_span_ids"], "document_ids": row["document_ids"],
    }


@app.post("/get_toc")
async def get_toc(req: TocReq, x_internal_auth: str = Header(...)):
    ctx = await _ctx(x_internal_auth)
    async with _store.pool.acquire() as con:
        rows = await con.fetch(
            "SELECT DISTINCT section_path FROM chunks "
            "WHERE tenant_id=$1 AND document_id=$2 ORDER BY section_path",
            ctx.tenant_id, req.doc_id)
    return {"toc": [r["section_path"] for r in rows]}
