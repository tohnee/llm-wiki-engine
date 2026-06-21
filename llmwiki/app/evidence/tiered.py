"""分层检索(借自 obsidian-wiki 的 wiki-query)。

成本曲线随规模平坦的关键:从便宜到贵逐级升级,答得了就停。
  Tier-0  索引/摘要扫描:只读 chunk.summary(≤200字)与 section_path,不开任何 span。
          index-only 模式(用户说"快速回答")强制只走这一层,并标注"未读正文"。
  Tier-1  span 级混合检索(retrieval.Retriever),按重要度 tier 加权:core > supporting > peripheral。
  Tier-2  parent chunk 扩展(命中 span → 全 chunk 上下文)。

与 navigation-first 协同:navigate 圈 scope,tiered 在 scope 内从便宜层开始。
"""
from __future__ import annotations

import json
import re

from app.core.config import get_settings
from app.core.tenant import TenantContext
from app.db.store import Store
from app.evidence.retrieval import Retriever
from app.llm.gateway import get_gateway, Priority

_S = get_settings()

_TIER_WEIGHT = {"core": 1.0, "supporting": 0.7, "peripheral": 0.3, None: 0.7}

_SCAN_SYSTEM = """你只能看到若干页面的标题、章节路径与一句话摘要(未读正文)。
判断这些摘要是否足以回答问题。
只输出 JSON:{"answerable": true/false, "answer": "若能答则给出,并在结尾标注(索引级回答,未读正文)", "need_pages": ["可能需要深读的 section_path"]}"""


async def tier0_summary_scan(
    store: Store, tenant_id: str, query: str,
    document_ids: list[str] | None = None,
) -> dict:
    """只读 summary/section_path 尝试回答。返回 {answerable, answer, candidates}。"""
    async with store.pool.acquire() as con:
        if document_ids:
            rows = await con.fetch(
                "SELECT chunk_id,section_path,summary,tier FROM chunks "
                "WHERE tenant_id=$1 AND document_id=ANY($2) AND summary<>'' LIMIT 200",
                tenant_id, document_ids)
        else:
            rows = await con.fetch(
                "SELECT chunk_id,section_path,summary,tier FROM chunks "
                "WHERE tenant_id=$1 AND summary<>'' LIMIT 200", tenant_id)
    if not rows:
        return {"answerable": False, "answer": None, "candidates": []}

    # 按重要度排序后给模型扫描(core 优先)
    rows = sorted(rows, key=lambda r: _TIER_WEIGHT.get(r["tier"], 0.7), reverse=True)
    catalog = "\n".join(f"- [{r['section_path']}] {r['summary']}" for r in rows[:80])
    gw = get_gateway()
    resp = await gw.complete(
        tenant_id=tenant_id, model=_S.model_haiku, system=_SCAN_SYSTEM,
        user_content=f"问题:{query}\n\n可用页面摘要:\n{catalog}",
        priority=Priority.INTERACTIVE, max_tokens=512)
    t = "".join(b.text for b in resp.content if b.type == "text")
    try:
        d = json.loads(re.sub(r"^```json\s*|\s*```$", "", t.strip()))
        return {"answerable": bool(d.get("answerable")), "answer": d.get("answer"),
                "candidates": d.get("need_pages", [])}
    except json.JSONDecodeError:
        return {"answerable": False, "answer": None, "candidates": []}


async def tiered_search(
    store: Store, tenant_id: str, query: str,
    document_ids: list[str] | None = None,
    index_only: bool = False, final_k: int | None = None,
) -> dict:
    """完整分层检索。index_only=True 时强制只走 tier-0。"""
    scan = await tier0_summary_scan(store, tenant_id, query, document_ids)
    if scan["answerable"] or index_only:
        return {"tier": 0, "answer": scan["answer"], "spans": [],
                "note": "索引级回答,未读正文" if scan["answerable"] else "index-only 模式"}

    # tier-1: span 检索,按重要度 tier 重加权
    retr = Retriever(store)
    spans = await retr.search(tenant_id, query, document_ids=document_ids, final_k=(final_k or _S.retrieve_final_k) * 2)

    # 用所属 chunk 的 tier 给 span 重加权
    async with store.pool.acquire() as con:
        sid_list = [s.span_id for s in spans]
        trows = await con.fetch(
            "SELECT s.span_id, c.tier FROM spans s JOIN chunks c USING(tenant_id,chunk_id) "
            "WHERE s.tenant_id=$1 AND s.span_id=ANY($2)", tenant_id, sid_list)
    tier_of = {r["span_id"]: r["tier"] for r in trows}
    for s in spans:
        s.score *= _TIER_WEIGHT.get(tier_of.get(s.span_id), 0.7)
    spans.sort(key=lambda s: s.score, reverse=True)
    spans = spans[: (final_k or _S.retrieve_final_k)]
    return {"tier": 1, "answer": None, "spans": [s.model_dump() for s in spans], "note": ""}
