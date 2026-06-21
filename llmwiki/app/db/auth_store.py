"""鉴权/管理相关存储(全局表 + 会话持久化)。与 Store 共用连接池。"""
from __future__ import annotations

import json
from typing import Optional

import asyncpg


class AuthStore:
    def __init__(self, pool: asyncpg.Pool):
        self.pool = pool

    async def create_tenant(self, tenant_id: str, name: str) -> None:
        async with self.pool.acquire() as con:
            await con.execute(
                "INSERT INTO tenants (tenant_id,name) VALUES ($1,$2) ON CONFLICT DO NOTHING",
                tenant_id, name)

    async def create_user(self, tenant_id: str, user_id: str, email: str,
                          password_hash: str, role: str = "member") -> None:
        async with self.pool.acquire() as con:
            await con.execute(
                """INSERT INTO users (user_id,tenant_id,email,password_hash,role)
                   VALUES ($1,$2,$3,$4,$5)""",
                user_id, tenant_id, email, password_hash, role)

    async def get_user_by_email(self, email: str) -> Optional[dict]:
        async with self.pool.acquire() as con:
            row = await con.fetchrow("SELECT * FROM users WHERE email=$1", email)
            return dict(row) if row else None

    async def tenant_active(self, tenant_id: str) -> bool:
        async with self.pool.acquire() as con:
            row = await con.fetchrow("SELECT status FROM tenants WHERE tenant_id=$1", tenant_id)
            return bool(row) and row["status"] == "active"

    # ---- 会话持久化(隔离键:tenant+user+session) ----
    async def load_turns(self, tenant_id: str, user_id: str, session_id: str) -> list[dict]:
        async with self.pool.acquire() as con:
            row = await con.fetchrow(
                "SELECT turns FROM conversations WHERE tenant_id=$1 AND user_id=$2 AND session_id=$3",
                tenant_id, user_id, session_id)
            return json.loads(row["turns"]) if row else []

    async def save_turns(self, tenant_id: str, user_id: str, session_id: str, turns: list[dict]) -> None:
        async with self.pool.acquire() as con:
            await con.execute(
                """INSERT INTO conversations (tenant_id,user_id,session_id,turns,updated_at)
                   VALUES ($1,$2,$3,$4,now())
                   ON CONFLICT (tenant_id,user_id,session_id)
                   DO UPDATE SET turns=EXCLUDED.turns, updated_at=now()""",
                tenant_id, user_id, session_id, json.dumps(turns))

    async def purge_tenant(self, tenant_id: str) -> None:
        """租户数据生命周期:删除会话 + 用户(分区数据由 Store.drop_tenant 处理)。"""
        async with self.pool.acquire() as con:
            await con.execute("DELETE FROM conversations WHERE tenant_id=$1", tenant_id)
            await con.execute("DELETE FROM users WHERE tenant_id=$1", tenant_id)
            await con.execute("UPDATE tenants SET status='suspended' WHERE tenant_id=$1", tenant_id)
