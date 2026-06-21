"""治理层(借自 llm-wiki v2 的 Privacy and governance)。

- scrub_sensitive:入库前自动剥除密钥/令牌/PII(API key、Bearer、邮箱、手机号、身份证/SSN、私钥块)。
- AuditLog:每个写操作留痕(tenant/user/action/target/detail/ts),可追溯、可审计。
"""
from __future__ import annotations

import re
import time
from dataclasses import dataclass

import asyncpg

# 敏感模式(保守:命中即脱敏为占位符,不丢整段)
_PATTERNS = [
    (re.compile(r"(sk-[A-Za-z0-9]{16,})"), "[REDACTED_API_KEY]"),
    (re.compile(r"(?i)bearer\s+[A-Za-z0-9._\-]{16,}"), "[REDACTED_TOKEN]"),
    (re.compile(r"(?i)(password|passwd|secret|token|api[_-]?key)\s*[:=]\s*\S+"), r"\1: [REDACTED]"),
    (re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----[\s\S]*?-----END [A-Z ]*PRIVATE KEY-----"), "[REDACTED_PRIVATE_KEY]"),
    (re.compile(r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b"), "[REDACTED_EMAIL]"),
    (re.compile(r"\b(?:\+?86)?1[3-9]\d{9}\b"), "[REDACTED_PHONE]"),          # 中国手机号
    (re.compile(r"\b\d{17}[\dXx]\b"), "[REDACTED_ID]"),                       # 身份证
    (re.compile(r"\b\d{3}-\d{2}-\d{4}\b"), "[REDACTED_SSN]"),                 # SSN
]


def scrub_sensitive(text: str) -> tuple[str, int]:
    """返回 (脱敏后文本, 命中次数)。入库前调用。"""
    hits = 0
    for pat, repl in _PATTERNS:
        text, n = pat.subn(repl, text)
        hits += n
    return text, hits


@dataclass
class AuditLog:
    pool: asyncpg.Pool

    async def record(self, tenant_id: str, action: str, *, user_id: str = "system",
                     target: str = "", detail: dict | None = None) -> None:
        import json
        async with self.pool.acquire() as con:
            await con.execute(
                "INSERT INTO audit_log (tenant_id,user_id,action,target,detail) "
                "VALUES ($1,$2,$3,$4,$5)",
                tenant_id, user_id, action, target, json.dumps(detail or {}, ensure_ascii=False))

    async def recent(self, tenant_id: str, limit: int = 50) -> list[dict]:
        async with self.pool.acquire() as con:
            rows = await con.fetch(
                "SELECT user_id,action,target,detail,ts FROM audit_log "
                "WHERE tenant_id=$1 ORDER BY ts DESC LIMIT $2", tenant_id, limit)
            return [dict(r) for r in rows]
