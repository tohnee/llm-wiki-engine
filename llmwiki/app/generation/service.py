"""生成服务(对外入口)。

POST /generate         基于指令(+可选 document_ids/已有证据)生成结构化产物
POST /generate/file    生成并渲染为文件(docx/xlsx/png/pptx),返回下载路径

鉴权与隔离同问答:JWT → tenant/user,证据走只读 Evidence API(服务端 ACL)。
生成 agent 不需要 sandbox——它只读取证 + 确定性渲染,不执行任意代码。
"""
from __future__ import annotations

import os
import uuid
import json
import time
from pathlib import Path
from fastapi.responses import FileResponse
from contextlib import asynccontextmanager

from fastapi import FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from app.core.auth import auth_context
from app.generation.generate import generate
from app.generation import render as render_mod

OUTPUT_DIR = os.getenv("GENERATION_OUTPUT_DIR", "/tmp/llmwiki-generated")


def _tenant_dir(tenant_id: str) -> str:
    return os.path.join(OUTPUT_DIR, tenant_id)


def _history_path(tenant_id: str) -> str:
    return os.path.join(_tenant_dir(tenant_id), "history.jsonl")


def _safe_name(name: str) -> str:
    return "".join(c for c in name if c.isalnum() or c in "._-")


def _record_history(tenant_id: str, item: dict) -> None:
    os.makedirs(_tenant_dir(tenant_id), exist_ok=True)
    item = {**item, "created_at": int(time.time())}
    with open(_history_path(tenant_id), "a", encoding="utf-8") as f:
        f.write(json.dumps(item, ensure_ascii=False) + "\n")


def _read_history(tenant_id: str, limit: int = 50) -> list[dict]:
    path = _history_path(tenant_id)
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8") as f:
        rows = [json.loads(line) for line in f if line.strip()]
    return list(reversed(rows[-limit:]))

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
    _record_history(ctx.tenant_id, {
        "artifact_id": f"gen_{uuid.uuid4().hex[:12]}", "user_id": ctx.user_id,
        "instruction": req.instruction, "artifact_type": req.artifact_type,
        "format": artifact.get("format"), "evidence_count": artifact.get("evidence_count"),
        "preview": (artifact.get("content") or json.dumps(artifact.get("spec", {}), ensure_ascii=False))[:300],
    })
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
    tenant_dir = _tenant_dir(ctx.tenant_id)
    name = f"{req.artifact_type}_{uuid.uuid4().hex[:8]}"
    path = render_mod.render(artifact, tenant_dir, name)
    file_name = os.path.basename(path)
    artifact_id = f"gen_{uuid.uuid4().hex[:12]}"
    _record_history(ctx.tenant_id, {
        "artifact_id": artifact_id, "user_id": ctx.user_id,
        "instruction": req.instruction, "artifact_type": req.artifact_type,
        "type": artifact["type"], "file_name": file_name,
        "download_url": f"/api/gen/files/{file_name}",
        "evidence_count": artifact.get("evidence_count"),
    })
    return {"artifact_id": artifact_id, "type": artifact["type"], "file_path": path,
            "file_name": file_name, "download_url": f"/api/gen/files/{file_name}",
            "evidence_count": artifact.get("evidence_count")}


@app.get("/history")
async def history(authorization: str = Header(...)):
    ctx, _role = auth_context(authorization)
    return {"items": _read_history(ctx.tenant_id)}


@app.get("/files/{file_name}")
async def file_download(file_name: str, authorization: str = Header(...)):
    ctx, _role = auth_context(authorization)
    safe = _safe_name(file_name)
    path = Path(_tenant_dir(ctx.tenant_id)) / safe
    if not path.exists() or not path.is_file():
        raise HTTPException(404, "file not found in tenant scope")
    return FileResponse(str(path), filename=safe)


@app.get("/health")
async def health():
    return {"ok": True}
