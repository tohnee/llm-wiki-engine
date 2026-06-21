"""结晶(借自 llm-wiki v2 的 Crystallization)。

把一段完成的工作(一次问答/研究线程)蒸馏成结构化摘要,作为一等 wiki 页落库,
并把其中的结论抽成 fact(provenance=inferred,回链原问答引用的 span)回填知识库,
强化或挑战已有事实。探索结果本身也是一种"源"。

只在质量达标时回填(避免噪声污染),由 on_query 钩子异步触发。
"""
from __future__ import annotations

import json
import re
import time
import uuid

from app.core.config import get_settings
from app.llm.gateway import get_gateway, Priority
from app.models.schema import Fact, WikiNode, Provenance, Tier, content_hash

_S = get_settings()

_CRYSTALLIZE_SYS = """把一次问答蒸馏为知识摘要。输出 JSON:
{"title":"", "digest":"3-5句话的中文摘要", 
 "facts":[{"subject":"","predicate":"","object":"","source_span_ids":[]}]}
facts 是从答案中提炼的可复用结论;source_span_ids 取答案引用的 [doc:span] 里的 span 部分。
不编造,只提炼答案中有证据支撑的结论。只输出 JSON。"""

_CITE = re.compile(r"\[([\w\-]+):([\w\-]+)\]")


def _strip(t: str) -> str:
    return re.sub(r"^```json\s*|\s*```$", "", t.strip())


async def crystallize(tenant_id: str, question: str, answer: str, verified_ratio: float):
    """返回 (WikiNode, list[Fact]) 或 None(质量不达标不回填)。"""
    if verified_ratio is not None and verified_ratio < 0.6:
        return None  # 质量门控:证据校验不足不回填
    gw = get_gateway()
    resp = await gw.complete(
        tenant_id=tenant_id, model=_S.model_sonnet, system=_CRYSTALLIZE_SYS,
        user_content=f"问题:{question}\n\n答案:\n{answer}",
        priority=Priority.COMPILE_BATCH, max_tokens=1024)
    text = "".join(b.text for b in resp.content if b.type == "text")
    try:
        data = json.loads(_strip(text))
    except json.JSONDecodeError:
        return None

    now = time.time()
    facts = []
    for f in data.get("facts", []):
        if not f.get("subject") or not f.get("object"):
            continue
        facts.append(Fact(
            fact_id=f"ft_{uuid.uuid4().hex[:16]}", tenant_id=tenant_id,
            document_id="crystallized",
            subject_entity=f.get("subject", ""), predicate=f.get("predicate", ""),
            object_value=f.get("object", ""),
            provenance=Provenance.INFERRED,           # 探索蒸馏 = 推断,非源文直述
            source_span_ids=f.get("source_span_ids", []),
            source_count=1, created_at=now, last_confirmed=now, retention=1.0,
            source_hash=content_hash(question + answer, "crystallize"),
        ))
    node = WikiNode(
        node_id=f"wk_{uuid.uuid4().hex[:16]}", tenant_id=tenant_id,
        title=data.get("title", question[:40]),
        content=data.get("digest", ""),
        tier=Tier.SUPPORTING)
    return node, facts
