"""文档入库服务(对外入口)。

POST /ingest  鉴权 → 登记 document 行 → 投递 compile:L1 任务到 Redis Streams。
这是 run_worker 的生产端(此前缺失,导致分布式编译链路只有消费端)。
支持两种输入:已上传到对象存储的源路径(走 MinerU),或直接传 markdown(小文档/测试)。
"""
from __future__ import annotations

import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel

from app.core.auth import auth_context
from app.db.store import Store
from app.db.auth_store import AuthStore
from app.compile.dag import CompileBus, CompileMsg
from app.compile.dag import unit_hash
from app.models.schema import CompileDepth

_store: Store | None = None
_bus: CompileBus | None = None
_auth: AuthStore | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _store, _bus, _auth
    _store = await Store.connect()
    _bus = await CompileBus.connect()
    _auth = AuthStore(_store.pool)
    yield


app = FastAPI(title="LLM-Wiki Ingest", lifespan=lifespan)


def build_ingest_msg(
    *, tenant_id: str, document_id: str, depth: str,
    scrubbed_md: str | None, source_path: str | None,
) -> CompileMsg:
    """构造文档级编译任务消息。

    input_hash 基于**脱敏后**内容计算,使缓存键与实际进入编译管线的内容一致:
    - 避免相同脱敏内容因密钥差异被当作不同输入反复重编(假性 cache miss);
    - 避免 hash 输入包含敏感数据(虽不可逆,但与治理层"密钥不进管线"一致)。
    """
    content = scrubbed_md or source_path or ""
    payload = {"source_path": source_path or "", "markdown": scrubbed_md or ""}
    return CompileMsg(
        job_id=f"job_{uuid.uuid4().hex[:12]}", tenant_id=tenant_id,
        document_id=document_id, level="L1", unit_id=document_id,
        input_hash=unit_hash(content, "v1", "ingest"),
        depth=depth, payload=payload)


class IngestReq(BaseModel):
    title: str
    source_path: str | None = None      # s3://... 或挂载路径(走 MinerU)
    markdown: str | None = None         # 或直接给 markdown
    depth: str = "D1"                    # D0 / D1 / D2


@app.post("/ingest")
async def ingest(req: IngestReq, authorization: str = Header(...)):
    ctx, role = auth_context(authorization)
    if role == "viewer":
        raise HTTPException(403, "viewer cannot ingest")
    if not await _auth.tenant_active(ctx.tenant_id):
        raise HTTPException(403, "tenant inactive")
    if not req.source_path and not req.markdown:
        raise HTTPException(400, "either source_path or markdown required")

    await _store.ensure_tenant_partition(ctx.tenant_id)
    document_id = f"doc_{uuid.uuid4().hex[:16]}"

    # 治理:入库前脱敏(剥除密钥/PII)+ 审计留痕
    from app.core.governance import scrub_sensitive, AuditLog
    scrubbed_md, hits = (scrub_sensitive(req.markdown) if req.markdown else (None, 0))
    audit = AuditLog(_store.pool)
    await audit.record(ctx.tenant_id, "ingest", user_id=ctx.user_id, target=document_id,
                       detail={"title": req.title, "depth": req.depth, "redactions": hits})

    async with _store.pool.acquire() as con:
        await con.execute(
            """INSERT INTO documents (document_id,tenant_id,title,source_uri,status,depth)
               VALUES ($1,$2,$3,$4,'uploaded',$5)""",
            document_id, ctx.tenant_id, req.title,
            req.source_path or "inline://markdown", req.depth)

    # 投递文档级编译任务到 compile:L1(run_worker 消费)
    msg = build_ingest_msg(
        tenant_id=ctx.tenant_id, document_id=document_id, depth=req.depth,
        scrubbed_md=scrubbed_md, source_path=req.source_path)
    await _bus.submit(msg)

    return {"document_id": document_id, "status": "queued", "depth": req.depth}


@app.get("/documents/{document_id}/status")
async def doc_status(document_id: str, authorization: str = Header(...)):
    ctx, _role = auth_context(authorization)
    async with _store.pool.acquire() as con:
        row = await con.fetchrow(
            "SELECT status,depth,page_count FROM documents WHERE tenant_id=$1 AND document_id=$2",
            ctx.tenant_id, document_id)
    if not row:
        raise HTTPException(404, "document not found in tenant scope")
    return dict(row)


@app.get("/health")
async def health():
    return {"ok": True}
