"""L4: KG(Entity + Facts + Relations)→ WikiNode(仅导航视图)。

每个核心实体渲染一页,事实陈述附 [span:ID] 回链,前置 provenance_mix 比例。
Wiki 不是引用源——下游回答仍走 span 取证。
"""
from __future__ import annotations

import uuid
from collections import Counter

from app.core.config import get_settings
from app.compile.prompts import WIKI_SYSTEM
from app.llm.gateway import get_gateway, Priority
from app.models.schema import Fact, Entity, WikiNode, Tier

_S = get_settings()


def _provenance_mix(facts: list[Fact]) -> dict:
    if not facts:
        return {}
    c = Counter((f.provenance.value if f.provenance else "extracted") for f in facts)
    n = len(facts)
    return {k: round(v / n, 3) for k, v in c.items()}


async def render_wiki_node(
    tenant_id: str, entity: Entity, facts: list[Fact], relations: list,
) -> WikiNode:
    gw = get_gateway()
    fact_block = "\n".join(
        f"- {f.subject_entity} {f.predicate} {f.object_value} "
        f"[span:{','.join(f.source_span_ids[:2])}]"
        f"{' ⚠矛盾' if (f.provenance and f.provenance.value == 'ambiguous') else ''}"
        for f in facts[:60]
    )
    rel_block = "\n".join(f"- {r.source_entity} {r.relation_type} {r.target_entity}" for r in relations[:30])
    resp = await gw.complete(
        tenant_id=tenant_id, model=_S.model_sonnet, system=WIKI_SYSTEM,
        user_content=f"实体: {entity.name} ({entity.type})\n\n事实:\n{fact_block}\n\n关系:\n{rel_block}",
        priority=Priority.COMPILE_REALTIME, max_tokens=2048)
    content = "".join(b.text for b in resp.content if b.type == "text")

    mix = _provenance_mix(facts)
    # 重要度:被关系引用越多越 core
    deg = sum(1 for r in relations if entity.entity_id in (r.source_entity, r.target_entity))
    tier = Tier.CORE if deg >= 5 else (Tier.SUPPORTING if deg >= 1 else Tier.PERIPHERAL)

    return WikiNode(
        node_id=f"wk_{uuid.uuid4().hex[:16]}", tenant_id=tenant_id,
        title=entity.name, content=content, entity_id=entity.entity_id,
        provenance_mix=mix, tier=tier)
