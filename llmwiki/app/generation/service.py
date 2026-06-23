"""生成服务(对外入口)。

POST /generate         基于指令(+可选 document_ids/已有证据)生成结构化产物
POST /generate/file    生成并渲染为文件(docx/xlsx/png/pptx),返回下载路径

鉴权与隔离同问答:JWT → tenant/user,证据走只读 Evidence API(服务端 ACL)。
生成 agent 不需要 sandbox——它只读取证 + 确定性渲染,不执行任意代码。
"""
from __future__ import annotations

import os
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from app.core.auth import auth_context
from app.generation.generate import generate
from app.generation import render as render_mod

OUTPUT_DIR = os.getenv("GENERATION_OUTPUT_DIR", "/tmp/llmwiki-generated")

# 启动期安全闸门:生产环境不允许带默认密钥上线
from app.core.security_guard import enforce_production_secrets  # noqa: E402
enforce_production_secrets(required_keys=("JWT_SECRET", "INTERNAL_HMAC_SECRET"))

app = FastAPI(title="LLM-Wiki Generation")

from app.core.observability import setup_logging, install_metrics_route  # noqa: E402
setup_logging("generation")
install_metrics_route(app)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class GenerateReq(BaseModel):
    instruction: str
    artifact_type: str = "report"        # report | chart | table | slides
    document_ids: list[str] | None = None
    evidence: list[dict] | None = None   # 可直接复用问答结果的 span 列表


@app.post("/generate")
async def gen(req: GenerateReq, authorization: str = Header(...)):
    ctx, role = auth_context(authorization)
    if role == "viewer":
        raise HTTPException(403, "viewer cannot generate")
    artifact = await generate(ctx, req.instruction, req.artifact_type,
                              document_ids=req.document_ids, evidence=req.evidence)
    return artifact


@app.post("/generate/file")
async def gen_file(req: GenerateReq, authorization: str = Header(...)):
    ctx, role = auth_context(authorization)
    if role == "viewer":
        raise HTTPException(403, "viewer cannot generate")
    artifact = await generate(ctx, req.instruction, req.artifact_type,
                              document_ids=req.document_ids, evidence=req.evidence)
    if artifact.get("format") == "json" and "error" in artifact.get("spec", {}):
        raise HTTPException(502, f"generation failed: {artifact['spec']['error']}")
    # 按租户隔离输出目录
    tenant_dir = os.path.join(OUTPUT_DIR, ctx.tenant_id)
    name = f"{req.artifact_type}_{uuid.uuid4().hex[:8]}"
    path = render_mod.render(artifact, tenant_dir, name)
    return {"type": artifact["type"], "file_path": path,
            "evidence_count": artifact.get("evidence_count")}


@app.get("/health")
async def health():
    return {"ok": True}
