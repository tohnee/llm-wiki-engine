"""编译 DAG 编排:Redis Streams + 完成协调。

拓扑:
  compile:L0  parse_shard      MinerU 分片并行解析
  compile:L1  chunk_span       切 chunk/span + embedding(+ D0 路由摘要)
  compile:L2  extract          Fact + Entity 抽取(Haiku Batch)
  compile:L3  resolve_relation Entity Resolution + Relation 抽取
  compile:L4  wiki_render      KG → Wiki(D2 才执行)

单元 hash = sha256(content + prompt_version + model_id),增量编译与 prompt 升级共用失效机制。
层间协调:Redis hash 计数器 per (job, level),子单元全部完成 → 投递父单元消息。
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass, asdict
from typing import Optional

import redis.asyncio as aioredis

from app.core.config import get_settings

_S = get_settings()

LEVELS = ["L0", "L1", "L2", "L3", "L4"]
STREAM = "compile:{level}"
DLQ = "compile:dlq"
GROUP = "workers"


@dataclass
class CompileMsg:
    job_id: str
    tenant_id: str
    document_id: str
    level: str
    unit_id: str                 # shard_id / chunk_id / entity_block ...
    input_hash: str
    depth: str = "D1"            # D0 / D1 / D2
    priority: int = 2
    attempt: int = 0
    payload: dict = None         # 该层特定数据(如页区间、原文指针)

    def encode(self) -> dict:
        d = asdict(self)
        d["payload"] = json.dumps(self.payload or {})
        return {k: str(v) for k, v in d.items()}

    @staticmethod
    def decode(fields: dict) -> "CompileMsg":
        return CompileMsg(
            job_id=fields["job_id"], tenant_id=fields["tenant_id"],
            document_id=fields["document_id"], level=fields["level"],
            unit_id=fields["unit_id"], input_hash=fields["input_hash"],
            depth=fields.get("depth", "D1"), priority=int(fields.get("priority", 2)),
            attempt=int(fields.get("attempt", 0)),
            payload=json.loads(fields.get("payload", "{}")),
        )


class CompileBus:
    def __init__(self, r: aioredis.Redis):
        self.r = r

    @classmethod
    async def connect(cls) -> "CompileBus":
        r = aioredis.from_url(
            _S.redis_url, decode_responses=True,
            socket_keepalive=True, socket_timeout=None,
        )
        bus = cls(r)
        await bus._ensure_groups()
        return bus

    async def _ensure_groups(self) -> None:
        for lvl in LEVELS:
            stream = STREAM.format(level=lvl)
            try:
                await self.r.xgroup_create(stream, GROUP, id="0", mkstream=True)
            except aioredis.ResponseError as e:
                if "BUSYGROUP" not in str(e):
                    raise

    # ---------------- 投递 / 消费 ----------------
    async def submit(self, msg: CompileMsg) -> None:
        await self.r.xadd(STREAM.format(level=msg.level), msg.encode())

    async def read(self, level: str, consumer: str, count: int = 8, block_ms: int = 5000):
        stream = STREAM.format(level=level)
        res = await self.r.xreadgroup(GROUP, consumer, {stream: ">"}, count=count, block=block_ms)
        out = []
        if res:
            for _stream, entries in res:
                for msg_id, fields in entries:
                    out.append((msg_id, CompileMsg.decode(fields)))
        return out

    async def ack(self, level: str, msg_id: str) -> None:
        await self.r.xack(STREAM.format(level=level), GROUP, msg_id)

    async def retry_or_dlq(self, level: str, msg_id: str, msg: CompileMsg) -> None:
        await self.ack(level, msg_id)
        if msg.attempt + 1 >= 3:
            await self.r.xadd(DLQ, {**msg.encode(), "failed_level": level})
        else:
            msg.attempt += 1
            await self.submit(msg)

    # ---------------- 完成协调(计数器) ----------------
    async def expect(self, job_id: str, level: str, n: int) -> None:
        """登记某层预期完成的单元数。"""
        await self.r.hset(f"compile:expect:{job_id}", level, n)

    async def complete_one(self, job_id: str, level: str) -> bool:
        """标记一个单元完成,返回该层是否全部完成。"""
        done = await self.r.hincrby(f"compile:done:{job_id}", level, 1)
        expect = int(await self.r.hget(f"compile:expect:{job_id}", level) or 0)
        return expect > 0 and done >= expect

    # ---------------- 增量:hash 寻址跳过 ----------------
    async def already_compiled(self, tenant_id: str, unit_id: str, input_hash: str) -> bool:
        key = f"compile:hash:{tenant_id}:{unit_id}"
        prev = await self.r.get(key)
        return prev == input_hash

    async def mark_compiled(self, tenant_id: str, unit_id: str, input_hash: str) -> None:
        await self.r.set(f"compile:hash:{tenant_id}:{unit_id}", input_hash)


def unit_hash(content: str, prompt_version: str, model_id: str) -> str:
    import hashlib
    h = hashlib.sha256()
    for p in (content, prompt_version, model_id):
        h.update(p.encode()); h.update(b"\x00")
    return h.hexdigest()
