"""LLM Gateway。

职责:
- 模型分层调用(Haiku 抽取 / Sonnet 推理)
- prompt caching(cache_control 标注稳定前缀)
- 优先级队列:interactive > verify > compile-realtime > compile-batch
- 按租户 token bucket 限流
- Batch API 提交(离线编译走批处理,成本减半且不占交互配额)
"""
from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from enum import IntEnum
from typing import Any, Optional

from anthropic import AsyncAnthropic

from app.core.config import get_settings

_S = get_settings()


class Priority(IntEnum):
    INTERACTIVE = 0       # 数值越小优先级越高
    VERIFY = 1
    COMPILE_REALTIME = 2
    COMPILE_BATCH = 3


@dataclass(order=True)
class _Job:
    priority: int
    seq: int
    fut: asyncio.Future = field(compare=False)
    coro: Any = field(compare=False)


class TokenBucket:
    """每租户 token bucket(粗粒度按调用计;生产可换成按 token 数)。"""
    def __init__(self, rate_per_sec: float, capacity: float):
        self.rate = rate_per_sec
        self.capacity = capacity
        self.tokens = capacity
        self.ts = time.monotonic()

    def allow(self, cost: float = 1.0) -> bool:
        now = time.monotonic()
        self.tokens = min(self.capacity, self.tokens + (now - self.ts) * self.rate)
        self.ts = now
        if self.tokens >= cost:
            self.tokens -= cost
            return True
        return False


class LLMGateway:
    def __init__(self, concurrency: int = 16):
        kwargs = {"api_key": _S.anthropic_api_key}
        if _S.anthropic_base_url:
            kwargs["base_url"] = _S.anthropic_base_url
        self.client = AsyncAnthropic(**kwargs)
        self._pq: asyncio.PriorityQueue[_Job] = asyncio.PriorityQueue()
        self._seq = 0
        self._sem = asyncio.Semaphore(concurrency)
        self._buckets: dict[str, TokenBucket] = {}
        self._worker_task: Optional[asyncio.Task] = None
        self.cache_hits = 0
        self.calls = 0

    def start(self) -> None:
        if self._worker_task is None:
            self._worker_task = asyncio.create_task(self._dispatch())

    def _bucket(self, tenant_id: str) -> TokenBucket:
        if tenant_id not in self._buckets:
            self._buckets[tenant_id] = TokenBucket(rate_per_sec=20, capacity=100)
        return self._buckets[tenant_id]

    async def _dispatch(self) -> None:
        while True:
            job = await self._pq.get()
            await self._sem.acquire()          # 在并发槽位可用前阻塞,真正限流
            asyncio.create_task(self._run(job))

    async def _run(self, job: _Job) -> None:
        try:
            res = await job.coro
            job.fut.set_result(res)
        except Exception as e:  # noqa: BLE001
            job.fut.set_exception(e)
        finally:
            self._sem.release()                # 任务完成后才释放槽位

    async def _enqueue(self, priority: Priority, coro) -> Any:
        self._seq += 1
        fut: asyncio.Future = asyncio.get_running_loop().create_future()
        await self._pq.put(_Job(priority=int(priority), seq=self._seq, fut=fut, coro=coro))
        return await fut

    # ---------------- 实时调用 ----------------
    async def complete(
        self,
        *,
        tenant_id: str,
        model: str,
        system: str,
        cached_prefix: Optional[str] = None,   # 稳定前缀(原文),标 cache_control
        user_content: str,
        priority: Priority = Priority.INTERACTIVE,
        max_tokens: int = 2048,
        tools: Optional[list] = None,
        messages: Optional[list] = None,
    ) -> Any:
        if not self._bucket(tenant_id).allow():
            await asyncio.sleep(0.2)  # 简单退避;生产用排队 + 429 反压

        # 组织 prompt:稳定前缀进 system block 并标缓存断点
        sys_blocks: list[dict] = [{"type": "text", "text": system}]
        if cached_prefix:
            sys_blocks.append({
                "type": "text",
                "text": cached_prefix,
                "cache_control": {"type": "ephemeral"},
            })

        msgs = messages or [{"role": "user", "content": user_content}]

        async def _call():
            self.calls += 1
            kwargs: dict[str, Any] = dict(
                model=model, max_tokens=max_tokens, system=sys_blocks, messages=msgs
            )
            if tools:
                kwargs["tools"] = tools
            resp = await self.client.messages.create(**kwargs)
            usage = getattr(resp, "usage", None)
            if usage and getattr(usage, "cache_read_input_tokens", 0):
                self.cache_hits += 1
            return resp

        return await self._enqueue(priority, _call())

    # ---------------- Batch 提交(离线编译) ----------------
    async def submit_batch(self, requests: list[dict]) -> str:
        """requests: [{custom_id, params}]。返回 batch_id;轮询在 compile worker 内做。"""
        batch = await self.client.messages.batches.create(requests=requests)
        return batch.id

    async def poll_batch(self, batch_id: str) -> Optional[list[dict]]:
        b = await self.client.messages.batches.retrieve(batch_id)
        if b.processing_status != "ended":
            return None
        results = []
        async for r in self.client.messages.batches.results(batch_id):
            results.append({"custom_id": r.custom_id, "result": r.result})
        return results

    @property
    def cache_hit_rate(self) -> float:
        return self.cache_hits / self.calls if self.calls else 0.0


_gateway: Optional[LLMGateway] = None


def get_gateway() -> LLMGateway:
    global _gateway
    if _gateway is None:
        _gateway = LLMGateway()
        _gateway.start()
    return _gateway
