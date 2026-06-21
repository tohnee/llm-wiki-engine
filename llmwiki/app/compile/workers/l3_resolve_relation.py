"""L3: Entity Resolution(blocking 4 级)+ Relation 抽取。

Resolution 避免 O(n^2):先按 blocking key 分桶,只在桶内比较。
L1 exact → L2 alias/编辑距离 → L3 embedding cosine → L4 LLM verify(仅候选对)。
"""
from __future__ import annotations

import asyncio
import json
import re
import uuid
from difflib import SequenceMatcher

import numpy as np

from app.core.config import get_settings
from app.compile.prompts import RESOLVE_SYSTEM, RELATION_SYSTEM, build_relation_system
from app.llm.gateway import get_gateway, Priority
from app.models.schema import Entity, Relation

_S = get_settings()


def _sim(a: str, b: str) -> float:
    return SequenceMatcher(None, a.lower(), b.lower()).ratio()


def _cos(a: list[float], b: list[float]) -> float:
    va, vb = np.array(a), np.array(b)
    return float(va @ vb / (np.linalg.norm(va) * np.linalg.norm(vb) + 1e-9))


async def resolve_entity(
    tenant_id: str, new: Entity, candidates: list[dict]
) -> tuple[str, bool]:
    """返回 (canonical_entity_id, is_new)。candidates 为同 blocking 桶内已有实体。"""
    # L1 exact
    for c in candidates:
        if c["name"].lower() == new.name.lower():
            return c["entity_id"], False
    # L2 alias / 高相似
    for c in candidates:
        if new.name.lower() in [a.lower() for a in (c["aliases"] or [])]:
            return c["entity_id"], False
        if _sim(new.name, c["name"]) > 0.92:
            return c["entity_id"], False
    # L3 embedding 候选
    emb_cands = []
    if new.embedding:
        for c in candidates:
            if c.get("embedding"):
                cs = _cos(new.embedding, c["embedding"])
                if cs > 0.85:
                    emb_cands.append((c, cs))
    emb_cands.sort(key=lambda x: x[1], reverse=True)
    # L4 LLM verify 仅 top 候选
    gw = get_gateway()
    for c, _cs in emb_cands[:2]:
        resp = await gw.complete(
            tenant_id=tenant_id, model=_S.model_haiku, system=RESOLVE_SYSTEM,
            user_content=json.dumps({
                "a": {"name": new.name, "type": new.type},
                "b": {"name": c["name"], "aliases": c["aliases"]},
            }, ensure_ascii=False),
            priority=Priority.COMPILE_BATCH, max_tokens=256,
        )
        text = "".join(b.text for b in resp.content if b.type == "text")
        try:
            d = json.loads(re.sub(r"^```json\s*|\s*```$", "", text.strip()))
            if d.get("merge"):
                return c["entity_id"], False
        except json.JSONDecodeError:
            pass
    return new.entity_id, True


async def extract_relations(
    tenant_id: str, entities: list[Entity], facts_summary: str, schema=None,
) -> list[Relation]:
    if not entities:
        return []
    system_text = build_relation_system(schema.relation_types, schema.custom_rules) if schema else RELATION_SYSTEM
    gw = get_gateway()
    ent_block = "\n".join(f"- {e.name} ({e.type})" for e in entities)
    try:
        resp = await asyncio.wait_for(
            gw.complete(
                tenant_id=tenant_id, model=_S.model_sonnet, system=system_text,
                user_content=f"entities:\n{ent_block}\n\nfacts:\n{facts_summary}",
                priority=Priority.COMPILE_BATCH, max_tokens=1024,
            ),
            timeout=60.0,
        )
    except Exception as e:
        print(f"[relation] extract_relations failed for doc, skipping L4: {e}", flush=True)
        return []
    text = "".join(b.text for b in resp.content if b.type == "text")
    name_to_id = {e.name.lower(): e.entity_id for e in entities}
    rels: list[Relation] = []
    try:
        data = json.loads(re.sub(r"^```json\s*|\s*```$", "", text.strip()))
        for r in data.get("relations", []):
            src = name_to_id.get(r.get("source", "").lower())
            tgt = name_to_id.get(r.get("target", "").lower())
            if src and tgt:
                rels.append(Relation(
                    relation_id=f"rl_{uuid.uuid4().hex[:16]}", tenant_id=tenant_id,
                    source_entity=src, relation_type=r.get("relation_type", "references"),
                    target_entity=tgt,
                ))
    except json.JSONDecodeError:
        pass
    return rels
