"""租户安全上下文。

不变量:tenant_id 永远由网关从鉴权 JWT 解出,经 HMAC 签名的内部 header 传递,
服务端解析后强制注入所有存储查询。任何来自 agent / 文档内容 / 客户端 body 的
tenant 参数一律忽略。这是数据隔离的根基。
"""
from __future__ import annotations

import hashlib
import hmac
import os
import time
from dataclasses import dataclass

_INTERNAL_SECRET = os.getenv("INTERNAL_HMAC_SECRET", "change-me-in-prod").encode()


@dataclass(frozen=True)
class TenantContext:
    tenant_id: str
    user_id: str
    session_id: str


def sign_internal_header(tenant_id: str, user_id: str, session_id: str) -> str:
    """网关侧:鉴权通过后生成内部签名 header 值。"""
    ts = str(int(time.time()))
    payload = f"{tenant_id}:{user_id}:{session_id}:{ts}"
    mac = hmac.new(_INTERNAL_SECRET, payload.encode(), hashlib.sha256).hexdigest()
    return f"{payload}:{mac}"


def verify_internal_header(value: str, max_age_sec: int = 300) -> TenantContext:
    """下游服务侧:校验并解出 TenantContext。校验失败抛异常 → 拒绝请求。"""
    try:
        tenant_id, user_id, session_id, ts, mac = value.rsplit(":", 4)
    except ValueError as e:
        raise PermissionError("malformed internal auth header") from e

    payload = f"{tenant_id}:{user_id}:{session_id}:{ts}"
    expected = hmac.new(_INTERNAL_SECRET, payload.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(mac, expected):
        raise PermissionError("internal auth signature mismatch")
    if int(time.time()) - int(ts) > max_age_sec:
        raise PermissionError("internal auth header expired")
    return TenantContext(tenant_id=tenant_id, user_id=user_id, session_id=session_id)
