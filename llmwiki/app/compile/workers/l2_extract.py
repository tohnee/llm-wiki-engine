"""L2: Chunk + 其 spans → Fact + Entity(单次 Haiku 调用,共享缓存前缀)。

Fact 强制携带 source_span_ids(回链原文)。Entity 带 mention span 与 blocking key。
离线场景走 Batch;此处给实时单元调用版本(渐进编译/小文档用)。
"""
from __future__ import annotations

import json
import re
import uuid

from app.core.config import get_settings
from app.compile.prompts import EXTRACT_SYSTEM, build_extract_system
from app.llm.gateway import get_gateway, Priority
from app.models.schema import Fact, Entity, Span, content_hash

_S = get_settings()


def _norm_block_key(name: str, etype: str) -> str:
    """Entity Resolution blocking key:归一化首 token + 类型。"""
    tok = re.sub(r"[^\w]", "", name.lower().split()[0]) if name.split() else name.lower()
    return f"{tok[:8]}|{etype}"


def _extract_json(text: str) -> dict:
    text = text.strip()
    text = re.sub(r"^```json\s*|\s*```$", "", text)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        # fallback 1: 取首尾 {} 之间的最大子串
        m = re.search(r"\{.*\}", text, re.S)
        if m:
            inner = m.group(0)
            try:
                return json.loads(inner)
            except json.JSONDecodeError:
                # fallback 2: 清理常见 LLM JSON 错误(尾随逗号 / 换行字面值 / 单引号)
                cleaned = re.sub(r",\s*([}\]])", r"\1", inner)   # 去尾随逗号
                cleaned = cleaned.replace("\n", " ").replace("\r", " ")
                try:
                    return json.loads(cleaned)
                except json.JSONDecodeError as e:
                    print(f"[l2_extract] JSON parse failed even after cleanup: {e}", flush=True)
        return {"facts": [], "entities": []}


def _build_extract_messages(
    chunk_text: str, spans: list[Span], system_text: str = EXTRACT_SYSTEM,
) -> tuple[list[dict], str]:
    """构造 fact/entity 抽取的 system blocks 与 user 文本(供实时与 Batch 共用)。
    system_text 可由调用方注入 schema 感知版本。"""
    span_block = "\n".join(f"[{i}] {s.content}" for i, s in enumerate(spans))
    sys_blocks = [
        {"type": "text", "text": system_text},
        {"type": "text", "text": chunk_text, "cache_control": {"type": "ephemeral"}},
    ]
    user = f"spans:\n{span_block}\n\n请抽取 facts 与 entities。"
    return sys_blocks, user


def parse_extract_result(
    tenant_id: str, document_id: str, chunk_text: str, spans: list[Span], text: str,
) -> tuple[list[Fact], list[Entity]]:
    """把模型返回文本解析为 Fact/Entity(实时与 Batch 共用)。"""
    data = _extract_json(text)
    facts: list[Fact] = []
    for f in data.get("facts", []):
        idxs = f.get("source_span_index", [])
        span_ids = [spans[i].span_id for i in idxs if 0 <= i < len(spans)]
        facts.append(Fact(
            fact_id=f"ft_{uuid.uuid4().hex[:16]}", tenant_id=tenant_id,
            document_id=document_id, subject_entity=f.get("subject", ""),
            predicate=f.get("predicate", ""), object_value=f.get("object", ""),
            qualifiers=f.get("qualifiers", {}),
            source_span_ids=span_ids,
            source_hash=content_hash(chunk_text, _S.prompt_version_extract),
        ))
    entities: list[Entity] = []
    for e in data.get("entities", []):
        idxs = e.get("span_index", [])
        span_ids = [spans[i].span_id for i in idxs if 0 <= i < len(spans)]
        name, etype = e.get("name", ""), e.get("type", "concept")
        if not name:
            continue
        entities.append(Entity(
            entity_id=f"en_{uuid.uuid4().hex[:16]}", tenant_id=tenant_id,
            name=name, type=etype, mention_span_ids=span_ids,
            document_ids=[document_id],
        ))
    return facts, entities


async def extract_chunk(
    tenant_id: str, document_id: str, chunk_text: str, spans: list[Span],
    priority: Priority = Priority.COMPILE_REALTIME, schema=None,
) -> tuple[list[Fact], list[Entity]]:
    """实时单 chunk 抽取(渐进编译/小文档)。大文档走 batch_extract_document。
    schema: 可选 TenantSchema,提供则用其 entity_types/custom_rules 构建系统 prompt。"""
    system_text = build_extract_system(schema.entity_types, schema.custom_rules) if schema else EXTRACT_SYSTEM
    # 强化:明确要求严格 JSON,避免 LLM 返回 markdown 围栏 / 解释文字
    system_text = (
        system_text
        + "\n\n[严格输出要求] 只输出一个 JSON 对象,无任何解释、无 markdown 围栏。"
        "字段必须为 {\"facts\":[...],\"entities\":[...]};末尾不能有逗号;字符串使用双引号。"
    )
    gw = get_gateway()
    span_block = "\n".join(f"[{i}] {s.content}" for i, s in enumerate(spans))
    resp = await gw.complete(
        tenant_id=tenant_id, model=_S.model_haiku, system=system_text,
        cached_prefix=chunk_text,
        user_content=f"spans:\n{span_block}\n\n请抽取 facts 与 entities。",
        priority=priority, max_tokens=2048,
        # 注意: 火山方舟 glm-5.2 不支持 response_format=json_object(返回 400);
        # kimi-k2.7-code 支持但偶发返回空。当前依靠 [严格输出要求] prompt 与
        # _extract_json 的多层 fallback 保证可靠性。如确认 LLM 支持,可在调用处加
        # response_format={"type": "json_object"}。
    )
    text = "".join(b.text for b in resp.content if b.type == "text")
    return parse_extract_result(tenant_id, document_id, chunk_text, spans, text)


def block_key(name: str, etype: str) -> str:
    return _norm_block_key(name, etype)


async def batch_extract_document(
    tenant_id: str, document_id: str,
    chunks_spans: list[tuple[str, str, list]],   # [(chunk_id, chunk_text, spans)]
    poll_interval: float = 10.0, max_wait: float = 3600.0,
    schema=None,
) -> dict[str, tuple[list, list]]:
    """Batch 化抽取:把一个文档的所有 chunk 组成单个 Batch job 提交,
    异步轮询,返回 {chunk_id: (facts, entities)}。

    相比逐 chunk 实时调用:成本再降一半、不占交互配额。代价是延迟(分钟级),
    适合后台全量编译;渐进编译的 D0 已先让文档可问,故延迟可接受。
    """
    import asyncio
    gw = get_gateway()
    # 构造 Batch requests:每个 chunk 一个 request,custom_id = chunk_id
    requests = []
    span_map: dict[str, tuple[str, list]] = {}
    # schema 感知:用租户 schema 的实体类型表替换硬编码类型
    if schema is not None:
        system_text = build_extract_system(schema.entity_types, schema.custom_rules)
    else:
        system_text = EXTRACT_SYSTEM
    for chunk_id, chunk_text, spans in chunks_spans:
        sys_blocks, user = _build_extract_messages(chunk_text, spans, system_text=system_text)
        requests.append({
            "custom_id": chunk_id,
            "params": {
                "model": _S.model_haiku, "max_tokens": 2048,
                "system": sys_blocks,
                "messages": [{"role": "user", "content": user}],
            },
        })
        span_map[chunk_id] = (chunk_text, spans)

    if not requests:
        return {}

    batch_id = await gw.submit_batch(requests)
    waited = 0.0
    results = None
    while waited < max_wait:
        results = await gw.poll_batch(batch_id)
        if results is not None:
            break
        await asyncio.sleep(poll_interval)
        waited += poll_interval
    if results is None:
        raise TimeoutError(f"batch {batch_id} not finished within {max_wait}s")

    out: dict[str, tuple[list, list]] = {}
    for r in results:
        chunk_id = r["custom_id"]
        chunk_text, spans = span_map.get(chunk_id, ("", []))
        res = r["result"]
        # Batch 结果结构: {type: 'succeeded'|'errored', message: {...}}
        if getattr(res, "type", None) != "succeeded" and (isinstance(res, dict) and res.get("type") != "succeeded"):
            out[chunk_id] = ([], [])
            continue
        msg = res.message if hasattr(res, "message") else res["message"]
        content = msg.content if hasattr(msg, "content") else msg["content"]
        text = "".join(
            (b.text if hasattr(b, "text") else b.get("text", ""))
            for b in content
            if (getattr(b, "type", None) or (isinstance(b, dict) and b.get("type"))) == "text")
        out[chunk_id] = parse_extract_result(tenant_id, document_id, chunk_text, spans, text)
    return out
