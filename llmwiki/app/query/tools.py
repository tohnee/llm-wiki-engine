"""Evidence Service 的 HTTP 客户端 + Anthropic tool 定义。

Fast QA 与 Agentic QA 共用同一组工具。客户端在请求中带上内部签名 header,
tenant 由调用方上下文决定,绝不由 LLM 传入。
"""
from __future__ import annotations

import os
import httpx

from app.core.tenant import sign_internal_header, TenantContext

EVIDENCE_URL = os.getenv("EVIDENCE_URL", "http://localhost:8001")

# 暴露给 LLM 的工具 schema(只读、无 tenant 字段)
TOOLS = [
    {"name": "navigate", "description": "定位问题相关的实体与文档范围(KG 入口),并返回实体间关系边。多文档/多跳问题先调用它缩小检索范围;hops 调大可拉入更多关联文档。",
     "input_schema": {"type": "object", "properties": {
         "query": {"type": "string"}, "hops": {"type": "integer"}}, "required": ["query"]}},
    {"name": "neighbors", "description": "给定实体 ID,返回其在知识图谱中的 hops 跳邻域(关系子图)。用于多跳推理:先 navigate 拿到实体,再沿关系扩展找关联证据。",
     "input_schema": {"type": "object", "properties": {
         "entity_ids": {"type": "array", "items": {"type": "string"}},
         "hops": {"type": "integer"}}, "required": ["entity_ids"]}},
    {"name": "typed_edges", "description": "按关系类型查询 typed knowledge graph 边。用于回答 uses/depends_on/contradicts/caused_by/fixed_by/superseded_by 等‘怎么相关’的问题。",
     "input_schema": {"type": "object", "properties": {
         "relation_types": {"type": "array", "items": {"type": "string"}},
         "entity_ids": {"type": "array", "items": {"type": "string"}},
         "limit": {"type": "integer"}}}},
    {"name": "search", "description": "在指定文档范围内做 span 级混合检索,返回候选证据。",
     "input_schema": {"type": "object", "properties": {
         "query": {"type": "string"},
         "document_ids": {"type": "array", "items": {"type": "string"}},
         "span_types": {"type": "array", "items": {"type": "string"}},
         "k": {"type": "integer"}}, "required": ["query"]}},
    {"name": "read_span", "description": "读取某个 span 的原文(citation 的最终落点)。",
     "input_schema": {"type": "object", "properties": {
         "doc_id": {"type": "string"}, "span_id": {"type": "string"}}, "required": ["doc_id", "span_id"]}},
    {"name": "expand", "description": "把 span 扩展到所属 chunk 获取更多上下文。",
     "input_schema": {"type": "object", "properties": {"span_id": {"type": "string"}}, "required": ["span_id"]}},
    {"name": "lookup_entity", "description": "查实体卡片与其跨文档提及。",
     "input_schema": {"type": "object", "properties": {
         "name": {"type": "string"}, "entity_id": {"type": "string"}}}},
    {"name": "get_toc", "description": "获取文档章节结构,长文档先定位章节再下钻。",
     "input_schema": {"type": "object", "properties": {"doc_id": {"type": "string"}}, "required": ["doc_id"]}},
]


class EvidenceClient:
    def __init__(self, ctx: TenantContext):
        self.ctx = ctx
        self._client = httpx.AsyncClient(base_url=EVIDENCE_URL, timeout=120)

    def _headers(self) -> dict:
        return {"x-internal-auth": sign_internal_header(
            self.ctx.tenant_id, self.ctx.user_id, self.ctx.session_id)}

    async def call(self, tool_name: str, tool_input: dict) -> dict:
        # 防御:剥除 LLM 可能注入的 tenant 字段
        tool_input = {k: v for k, v in tool_input.items() if k != "tenant_id"}
        try:
            resp = await self._client.post(f"/{tool_name}", json=tool_input, headers=self._headers())
            resp.raise_for_status()
            return resp.json()
        except httpx.ConnectError as e:
            # evidence 服务不可用时返回结构化错误,让 LLM 能给出有意义的回答
            return {"error": f"evidence service unavailable ({EVIDENCE_URL}), cannot retrieve evidence",
                    "detail": str(e)}
        except httpx.HTTPStatusError as e:
            return {"error": f"evidence service returned {e.response.status_code}",
                    "detail": e.response.text[:500]}

    async def aclose(self):
        await self._client.aclose()
