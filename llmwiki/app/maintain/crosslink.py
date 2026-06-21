"""Cross-linker(借自 obsidian-wiki):周期性发现未链接的实体提及并织入。

对每个实体,在全租户 span 中用其名做 BM25/ILIKE 命中,把尚未记录的 span 加入
entity.mention_span_ids;同一 span 内共现的两个实体之间补 co_mention 关系。
这是 Karpathy 说的"记账"——交叉引用维护,交给 AI 定时做。
"""
from __future__ import annotations

import uuid

from app.db.store import Store
from app.models.schema import Relation


def eligible_for_match(name: str) -> bool:
    """实体名是否适合做跨文档子串匹配。

    过短的纯 ASCII 名(如 "AI"/"IT"/"OK")会大量误命中普通英文单词的子串
    (available/email/trail…),污染 mention_span_ids。因此对纯 ASCII 名要求
    ≥3 字符;含 CJK 的名字每个字符信息密度高,2 字符即有意义。
    """
    if not name or not name.strip():
        return False
    has_cjk = any("\u4e00" <= ch <= "\u9fff" for ch in name)
    return len(name) >= (2 if has_cjk else 3)


async def crosslink_tenant(store: Store, tenant_id: str, max_entities: int = 500) -> dict:
    added_mentions = 0
    added_relations = 0
    async with store.pool.acquire() as con:
        ents = await con.fetch(
            "SELECT entity_id,name,mention_span_ids FROM entities WHERE tenant_id=$1 LIMIT $2",
            tenant_id, max_entities)
        # 名字 → entity_id,用于共现关系
        name_to_id = {e["name"].lower(): e["entity_id"] for e in ents}
        span_entities: dict[str, set[str]] = {}

        for e in ents:
            eid, name = e["entity_id"], e["name"]
            if not eligible_for_match(name):
                continue
            rows = await con.fetch(
                "SELECT span_id FROM spans WHERE tenant_id=$1 AND content ILIKE '%'||$2||'%' LIMIT 200",
                tenant_id, name)
            hit = [r["span_id"] for r in rows]
            existing = set(e["mention_span_ids"] or [])
            new_hits = [s for s in hit if s not in existing]
            if new_hits:
                merged = list(existing | set(new_hits))
                await con.execute(
                    "UPDATE entities SET mention_span_ids=$3 WHERE tenant_id=$1 AND entity_id=$2",
                    tenant_id, eid, merged)
                added_mentions += len(new_hits)
            for s in hit:
                span_entities.setdefault(s, set()).add(eid)

    # 共现 → co_mention 关系(同 span 出现的实体对)
    rels: list[Relation] = []
    seen_pairs = set()
    for span_id, eids in span_entities.items():
        eids = list(eids)
        for i in range(len(eids)):
            for j in range(i + 1, len(eids)):
                pair = tuple(sorted((eids[i], eids[j])))
                if pair in seen_pairs:
                    continue
                seen_pairs.add(pair)
                rels.append(Relation(
                    relation_id=f"rl_{uuid.uuid4().hex[:16]}", tenant_id=tenant_id,
                    source_entity=pair[0], relation_type="co_mention",
                    target_entity=pair[1], source_span_ids=[span_id]))
    if rels:
        await store.upsert_relations(tenant_id, rels)
        added_relations = len(rels)

    return {"added_mentions": added_mentions, "added_relations": added_relations}
