"""为 chunk 生成 ≤200 字摘要(提升 tier-0 摘要扫描质量)。

L1 默认用首 200 字启发式;此模块用 Haiku 生成语义摘要,并行 + 缓存前缀。
在 orchestrator 的 D0/D1 路径对变化 chunk 调用,覆盖 chunk.summary。
"""
from __future__ import annotations

import asyncio

from app.core.config import get_settings
from app.llm.gateway import get_gateway, Priority
from app.models.schema import Chunk

_S = get_settings()
_SYS = "用一句不超过80字的中文摘要概括以下片段的核心内容,只输出摘要本身,不要前缀。"


async def generate_summaries(tenant_id: str, chunks: list[Chunk], concurrency: int = 4) -> None:
    gw = get_gateway()
    sem = asyncio.Semaphore(concurrency)

    async def _one(c: Chunk):
        async with sem:
            try:
                resp = await gw.complete(
                    tenant_id=tenant_id, model=_S.model_haiku, system=_SYS,
                    user_content=c.content[:3000],
                    priority=Priority.COMPILE_REALTIME, max_tokens=128)
                txt = "".join(b.text for b in resp.content if b.type == "text").strip()
                if txt:
                    c.summary = txt[:197]
            except Exception as e:
                print(f"[summarize] chunk {c.chunk_id} failed: {e}, keeping default summary", flush=True)

    await asyncio.gather(*[_one(c) for c in chunks])
