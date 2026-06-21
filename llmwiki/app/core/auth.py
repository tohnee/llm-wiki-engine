"""鉴权核心:密码哈希(stdlib pbkdf2)+ JWT 签发/校验 + FastAPI 依赖。

生产建议把 pbkdf2 换成 argon2/bcrypt(passlib);此处用 stdlib 零额外依赖,保证可跑。
JWT 载荷含 tenant_id / user_id / role,下游据此做租户与角色判定。
"""
from __future__ import annotations

import hashlib
import hmac
import os
import secrets
import time

import jwt
from fastapi import Header, HTTPException

from app.core.tenant import TenantContext

JWT_SECRET = os.getenv("JWT_SECRET", "change-me")
JWT_TTL = int(os.getenv("JWT_TTL_SEC", "3600"))
_PBKDF2_ITER = 200_000


def hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), _PBKDF2_ITER)
    return f"pbkdf2${_PBKDF2_ITER}${salt}${dk.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        _algo, iters, salt, want = stored.split("$")
        dk = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), int(iters))
        return hmac.compare_digest(dk.hex(), want)
    except (ValueError, TypeError):
        return False


def issue_jwt(tenant_id: str, user_id: str, role: str = "member") -> str:
    now = int(time.time())
    return jwt.encode(
        {"tenant_id": tenant_id, "sub": user_id, "role": role,
         "iat": now, "exp": now + JWT_TTL},
        JWT_SECRET, algorithm="HS256")


def decode_jwt(token: str) -> dict:
    return jwt.decode(token, JWT_SECRET, algorithms=["HS256"])


def auth_context(authorization: str, session_id: str = "") -> tuple[TenantContext, str]:
    """从 Bearer token 解出 (TenantContext, role)。tenant/user 只来自 token。"""
    if not authorization.startswith("Bearer "):
        raise HTTPException(401, "missing bearer token")
    try:
        claims = decode_jwt(authorization[7:])
    except jwt.PyJWTError as e:
        raise HTTPException(401, f"invalid token: {e}")
    ctx = TenantContext(tenant_id=claims["tenant_id"], user_id=claims["sub"],
                        session_id=session_id)
    return ctx, claims.get("role", "member")
