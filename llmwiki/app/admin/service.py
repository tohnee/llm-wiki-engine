"""管理与登录服务。

- POST /admin/tenants    创建租户(需 platform admin key)
- POST /admin/users      在租户下创建用户(需 platform admin key)
- POST /auth/login       邮箱+密码 → JWT(含 tenant_id/user_id/role)

platform admin key 用于初始化;生产应换成完整的控制台 + RBAC。
"""
from __future__ import annotations

import os
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, ConfigDict, Field

from app.db.store import Store
from app.db.auth_store import AuthStore
from app.core.auth import hash_password, verify_password, issue_jwt

PLATFORM_ADMIN_KEY = os.getenv("PLATFORM_ADMIN_KEY", "change-me-admin")

_store: Store | None = None
_auth: AuthStore | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _store, _auth
    from app.core.security_guard import enforce_production_secrets
    enforce_production_secrets(
        required_keys=("JWT_SECRET",),
        extra_required=("PLATFORM_ADMIN_KEY",),
    )
    _store = await Store.connect()
    _auth = AuthStore(_store.pool)
    yield


app = FastAPI(title="LLM-Wiki Admin/Auth", lifespan=lifespan)

from app.core.observability import setup_logging, install_metrics_route  # noqa: E402
setup_logging("admin")
install_metrics_route(app)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _require_platform_admin(x_admin_key: str):
    if x_admin_key != PLATFORM_ADMIN_KEY:
        raise HTTPException(403, "platform admin key required")


class CreateTenantReq(BaseModel):
    tenant_id: str
    name: str

class CreateUserReq(BaseModel):
    tenant_id: str
    email: str
    password: str
    role: str = "member"

class LoginReq(BaseModel):
    email: str
    password: str


@app.post("/admin/tenants")
async def create_tenant(req: CreateTenantReq, x_admin_key: str = Header(...)):
    _require_platform_admin(x_admin_key)
    await _auth.create_tenant(req.tenant_id, req.name)
    await _store.ensure_tenant_partition(req.tenant_id)   # 建物理分区
    return {"tenant_id": req.tenant_id, "status": "active"}


@app.post("/admin/users")
async def create_user(req: CreateUserReq, x_admin_key: str = Header(...)):
    _require_platform_admin(x_admin_key)
    if not await _auth.tenant_active(req.tenant_id):
        raise HTTPException(400, "tenant not active")
    if await _auth.get_user_by_email(req.email):
        raise HTTPException(409, "email already exists")
    user_id = f"u_{uuid.uuid4().hex[:16]}"
    await _auth.create_user(req.tenant_id, user_id, req.email,
                            hash_password(req.password), req.role)
    return {"user_id": user_id, "tenant_id": req.tenant_id, "role": req.role}


@app.post("/auth/login")
async def login(req: LoginReq):
    user = await _auth.get_user_by_email(req.email)
    if not user or not verify_password(req.password, user["password_hash"]):
        raise HTTPException(401, "invalid credentials")
    if user["status"] != "active" or not await _auth.tenant_active(user["tenant_id"]):
        raise HTTPException(403, "account or tenant inactive")
    token = issue_jwt(user["tenant_id"], user["user_id"], user["role"])
    return {"access_token": token, "token_type": "bearer",
            "tenant_id": user["tenant_id"], "user_id": user["user_id"]}


@app.get("/health")
async def health():
    return {"ok": True}


# ---- 租户 Schema 层(taxonomy / lint 阈值 / 自定义规则) ----
from app.core.schema_layer import SchemaStore, TenantSchema  # noqa: E402


class SchemaUpdateReq(BaseModel):
    """PUT /admin/schema/{tenant} 请求体。

    所有字段可选以支持部分更新;tenant_id 由路径参数提供,禁止在 body 传入。
    严格校验类型与取值范围,拒绝未知字段(防拼写错误静默写入)。
    """
    model_config = ConfigDict(extra="forbid")

    entity_types: list[str] | None = None
    relation_types: list[str] | None = None
    lint_ambiguous_ratio: float | None = Field(None, ge=0.0, le=1.0)
    lint_inferred_ratio: float | None = Field(None, ge=0.0, le=1.0)
    lint_hub_inferred_ratio: float | None = Field(None, ge=0.0, le=1.0)
    default_depth: str | None = None
    summary_max_chars: int | None = Field(None, ge=1, le=2000)
    custom_rules: str | None = None


_schema: SchemaStore | None = None


@app.get("/admin/schema/{tenant_id}")
async def get_schema(tenant_id: str, x_admin_key: str = Header(...)):
    _require_platform_admin(x_admin_key)
    global _schema
    if _schema is None:
        _schema = await SchemaStore.connect()
    s = await _schema.get(tenant_id)
    from dataclasses import asdict
    return asdict(s)


@app.put("/admin/schema/{tenant_id}")
async def set_schema(tenant_id: str, req: SchemaUpdateReq, x_admin_key: str = Header(...)):
    _require_platform_admin(x_admin_key)
    global _schema
    if _schema is None:
        _schema = await SchemaStore.connect()
    await _schema.set(TenantSchema(tenant_id=tenant_id, **req.model_dump(exclude_none=True)))
    return {"ok": True, "tenant_id": tenant_id}
