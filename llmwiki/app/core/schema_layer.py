"""租户级 Schema 层(对应 obsidian-wiki V2 的"schema layer / CLAUDE.md")。

V2 三层架构:raw(原文,不可变)/ wiki(AI 生成)/ **schema(规则文件,治理 wiki 如何维护)**。
此前规则散落在 prompts.py + config.py(全局硬编码);本模块把它提升为**每租户可配置**的一等层:
- 实体类型表(taxonomy)、关系类型表
- lint 阈值(ambiguous / inferred / hub)
- 分级编译默认深度、摘要长度
编译/审计运行时读取它,使不同租户可定制知识组织规则。
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict

import redis.asyncio as aioredis

from app.core.config import get_settings

_S = get_settings()


@dataclass
class TenantSchema:
    tenant_id: str
    entity_types: list[str] = field(default_factory=lambda: [
        "org", "person", "product", "project", "location", "time", "concept"])
    relation_types: list[str] = field(default_factory=lambda: [
        "works_for", "owns", "develops", "depends_on", "references",
        "belongs_to", "part_of", "causes", "co_mention"])
    lint_ambiguous_ratio: float = 0.15
    lint_inferred_ratio: float = 0.40
    lint_hub_inferred_ratio: float = 0.20
    default_depth: str = "D1"
    # 摘要硬上限(字符);生成时若超出会截断并加 "..." 后缀(后缀计入上限)
    summary_max_chars: int = 200
    # 自定义维护规则(自由文本,注入编译 prompt,等价于 CLAUDE.md 里的自然语言规则)
    custom_rules: str = ""

    def to_json(self) -> str:
        return json.dumps(asdict(self), ensure_ascii=False)


class SchemaStore:
    """schema 存 Redis(热)。键 schema:{tenant}。简单、低频读写。"""
    def __init__(self, r: aioredis.Redis):
        self.r = r

    @classmethod
    async def connect(cls) -> "SchemaStore":
        return cls(aioredis.from_url(_S.redis_url, decode_responses=True))

    async def get(self, tenant_id: str) -> TenantSchema:
        raw = await self.r.get(f"schema:{tenant_id}")
        if not raw:
            return TenantSchema(tenant_id=tenant_id)   # 默认
        d = json.loads(raw)
        d["tenant_id"] = tenant_id
        return TenantSchema(**d)

    async def set(self, schema: TenantSchema) -> None:
        await self.r.set(f"schema:{schema.tenant_id}", schema.to_json())
