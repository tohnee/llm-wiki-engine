"""会话记忆:Redis 热副本(TTL)+ Postgres 持久副本。

隔离键严格为 (tenant_id, user_id, session_id) —— 不同用户/租户的记忆物理分键,
不可能交叉。worker 无状态:任意实例按键恢复会话,支持 P3 水平扩展。

存储的是"对话轮次摘要"(role + 文本),不是完整工具调用轨迹(那部分每次重新取证)。
"""
from __future__ import annotations

import json
import time

import redis.asyncio as aioredis

from app.core.config import get_settings
from app.core.tenant import TenantContext

_S = get_settings()
_TTL = 60 * 60 * 24 * 7          # 热副本 7 天
_MAX_TURNS = 20                  # 注入上下文的最大历史轮数


class MemoryStore:
    def __init__(self, r: aioredis.Redis, auth_store=None):
        self.r = r
        self.auth_store = auth_store   # 可选:AuthStore 做持久副本

    @classmethod
    async def connect(cls, auth_store=None) -> "MemoryStore":
        return cls(aioredis.from_url(_S.redis_url, decode_responses=True), auth_store)

    def _key(self, ctx: TenantContext) -> str:
        return f"mem:{ctx.tenant_id}:{ctx.user_id}:{ctx.session_id}"

    async def load(self, ctx: TenantContext) -> list[dict]:
        raw = await self.r.get(self._key(ctx))
        if raw is not None:
            return json.loads(raw)
        # 冷启动:从 PG 持久副本恢复
        if self.auth_store:
            turns = await self.auth_store.load_turns(ctx.tenant_id, ctx.user_id, ctx.session_id)
            if turns:
                await self.r.set(self._key(ctx), json.dumps(turns), ex=_TTL)
            return turns
        return []

    async def append(self, ctx: TenantContext, role: str, content: str) -> None:
        turns = await self.load(ctx)
        turns.append({"role": role, "content": content, "ts": int(time.time())})
        turns = turns[-_MAX_TURNS:]
        await self.r.set(self._key(ctx), json.dumps(turns), ex=_TTL)
        if self.auth_store:
            await self.auth_store.save_turns(ctx.tenant_id, ctx.user_id, ctx.session_id, turns)

    async def history_messages(self, ctx: TenantContext) -> list[dict]:
        """转成 Anthropic messages 历史(仅文本轮次)。"""
        return [{"role": t["role"], "content": t["content"]} for t in await self.load(ctx)]
