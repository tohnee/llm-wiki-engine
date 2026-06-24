"""查询 API 网关(对外入口)。

JWT 鉴权 → 解出 tenant/user/role → 注入会话记忆(按 tenant+user+session 隔离)→ 调用 pipeline。
tenant_id/user_id 只从 JWT 取,绝不从 body 取。
"""
from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from app.core.auth import auth_context
from app.db.store import Store
from app.db.auth_store import AuthStore
from app.query.memory import MemoryStore
from app.query.pipeline import answer

_memory: MemoryStore | None = None
_auth: AuthStore | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _memory, _auth
    # 启动期安全闸门:生产环境不允许带默认密钥上线
    from app.core.security_guard import enforce_production_secrets
    enforce_production_secrets(required_keys=("JWT_SECRET", "INTERNAL_HMAC_SECRET"))
    store = await Store.connect()
    _auth = AuthStore(store.pool)
    _memory = await MemoryStore.connect(auth_store=_auth)
    import app.core.hook_handlers  # noqa: F401  注册 v2 事件钩子
    yield


app = FastAPI(title="LLM-Wiki Query Gateway", lifespan=lifespan)

# 可观测性:结构化日志 + /metrics
from app.core.observability import setup_logging, install_metrics_route  # noqa: E402
setup_logging("query-gateway")
install_metrics_route(app)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class AskReq(BaseModel):
    question: str
    session_id: str


@app.post("/ask")
async def ask(req: AskReq, authorization: str = Header(...)):
    ctx, _role = auth_context(authorization, session_id=req.session_id)
    if not await _auth.tenant_active(ctx.tenant_id):
        raise HTTPException(403, "tenant inactive")
    result = await answer(ctx, req.question, memory=_memory)
    return {
        "answer": result["answer"],
        "verified_ratio": result.get("verify", {}).get("verified_ratio"),
        "escalated": result.get("escalated", False),
        "citations": result.get("citations", []),
        "claims": result.get("verify", {}).get("claims", []),
        "tool_trace": result.get("tool_trace", []),
    }


@app.get("/health")
async def health():
    return {"ok": True}


# ---- 透传 evidence 只读接口(带内部签名 header),供前端图谱/健康面板用 ----
import httpx  # noqa: E402
import os  # noqa: E402
from app.core.tenant import sign_internal_header  # noqa: E402

_EVIDENCE = os.getenv("EVIDENCE_URL", "http://localhost:8001")


def _signed(ctx):
    return {"x-internal-auth": sign_internal_header(ctx.tenant_id, ctx.user_id, ctx.session_id)}


@app.get("/graph")
async def graph(fmt: str = "json", authorization: str = Header(...)):
    ctx, _ = auth_context(authorization, session_id="graph")
    try:
        async with httpx.AsyncClient(timeout=30) as c:
            r = await c.get(f"{_EVIDENCE}/graph/export", params={"fmt": fmt}, headers=_signed(ctx))
            r.raise_for_status()
            return r.json()
    except httpx.ConnectError:
        raise HTTPException(503, f"evidence service unavailable at {_EVIDENCE}")
    except httpx.HTTPStatusError as e:
        raise HTTPException(e.response.status_code, f"evidence error: {e.response.text[:200]}")


@app.get("/status")
async def status(authorization: str = Header(...)):
    ctx, _ = auth_context(authorization, session_id="status")
    try:
        async with httpx.AsyncClient(timeout=30) as c:
            r = await c.get(f"{_EVIDENCE}/status", headers=_signed(ctx))
            r.raise_for_status()
            return r.json()
    except httpx.ConnectError:
        raise HTTPException(503, f"evidence service unavailable at {_EVIDENCE}")
    except httpx.HTTPStatusError as e:
        raise HTTPException(e.response.status_code, f"evidence error: {e.response.text[:200]}")
