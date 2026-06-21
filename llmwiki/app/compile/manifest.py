"""依赖 manifest(强化版增量,借自 obsidian-wiki 的 .manifest.json 思想)。

obsidian-wiki 记录"每个源文件产出了哪些 wiki 页面",改动时只重处理 delta。
我们做得更细:记录每个 chunk 产出了哪些 fact/entity/wiki 节点,
chunk 变化时不仅重抽该 chunk,还精确失效它派生的下游 KG/wiki 节点(否则会留下孤儿/陈旧节点)。

存储在 Redis hash:manifest:{tenant}:{chunk_id} -> {fact_ids, entity_ids, wiki_node_ids, hash}
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field

import redis.asyncio as aioredis

from app.core.config import get_settings

_S = get_settings()


@dataclass
class ChunkArtifacts:
    chunk_id: str
    content_hash: str
    fact_ids: list[str] = field(default_factory=list)
    entity_ids: list[str] = field(default_factory=list)
    wiki_node_ids: list[str] = field(default_factory=list)


class Manifest:
    def __init__(self, r: aioredis.Redis):
        self.r = r

    @classmethod
    async def connect(cls) -> "Manifest":
        return cls(aioredis.from_url(_S.redis_url, decode_responses=True))

    def _key(self, tenant_id: str, chunk_id: str) -> str:
        return f"manifest:{tenant_id}:{chunk_id}"

    async def record(self, tenant_id: str, art: ChunkArtifacts) -> None:
        await self.r.set(self._key(tenant_id, art.chunk_id), json.dumps({
            "content_hash": art.content_hash,
            "fact_ids": art.fact_ids,
            "entity_ids": art.entity_ids,
            "wiki_node_ids": art.wiki_node_ids,
        }))

    async def get(self, tenant_id: str, chunk_id: str) -> ChunkArtifacts | None:
        raw = await self.r.get(self._key(tenant_id, chunk_id))
        if not raw:
            return None
        d = json.loads(raw)
        return ChunkArtifacts(chunk_id=chunk_id, content_hash=d["content_hash"],
                              fact_ids=d["fact_ids"], entity_ids=d["entity_ids"],
                              wiki_node_ids=d["wiki_node_ids"])

    async def stale_artifacts(
        self, tenant_id: str, chunk_id: str, new_hash: str
    ) -> ChunkArtifacts | None:
        """chunk 变化时返回需要失效的旧派生产物;未变化返回 None。

        WARNING: 返回 None 有两种情况——
          1. chunk 真正未变化(prev 存在且 hash 一致)→ 跳过编译
          2. chunk 是全新的(prev 为 None,无旧产物需失效)→ **仍需编译**
        调用方若需判断"是否需要编译",应直接用 get() 检查 prev 是否存在,
        而非用本方法的返回值。本方法仅用于"变化时取出旧产物做失效"。
        """
        prev = await self.get(tenant_id, chunk_id)
        if prev and prev.content_hash == new_hash:
            return None       # 未变化,跳过(对应 obsidian-wiki 的 delta 跳过)
        return prev            # 变化或新增:prev 里的产物需被失效/替换(prev 可能为 None)
