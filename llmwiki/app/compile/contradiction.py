"""矛盾检测 + 溯源三态标记(借自 obsidian-wiki 的 extracted/inferred/ambiguous)。

merge 时:同一 (subject_entity, predicate) 的多个 fact,若 object 不一致 → 互相标 ambiguous
并记录 contradicts。单来源直接陈述 → extracted;跨多 span/多文档归纳出且无单一 span 支撑 → inferred。

这是企业多文档场景(合同 vs 邮件 vs 纪要 口径不一)最需要的能力:
不是悄悄选一个,而是显式把矛盾暴露给用户。
"""
from __future__ import annotations

import json
import re
from collections import defaultdict

from app.core.config import get_settings
from app.llm.gateway import get_gateway, Priority
from app.models.schema import Fact, Provenance

_S = get_settings()

_CONFLICT_SYSTEM = """判断两个关于同一主语和谓词的陈述是否事实矛盾(而非互补/不同侧面)。
只输出 JSON:{"contradict": true/false}"""


def assign_provenance_basic(fact: Fact) -> Fact:
    """规则版溯源:有单一 span 支撑 → extracted;无 span 但有内容 → inferred。"""
    if fact.provenance is not None:
        return fact
    if fact.source_span_ids:
        fact.provenance = Provenance.EXTRACTED
    else:
        fact.provenance = Provenance.INFERRED
    return fact


async def detect_contradictions(tenant_id: str, facts: list[Fact]) -> list[Fact]:
    """对同 (subject, predicate) 分组,object 不一致的组做 LLM 矛盾确认,标 ambiguous。"""
    gw = get_gateway()
    groups: dict[tuple[str, str], list[Fact]] = defaultdict(list)
    for f in facts:
        assign_provenance_basic(f)
        groups[(f.subject_entity.lower(), f.predicate.lower())].append(f)

    for (_subj, _pred), grp in groups.items():
        if len(grp) < 2:
            continue
        objs = {f.object_value.strip().lower() for f in grp}
        if len(objs) < 2:
            continue  # object 一致,无矛盾
        # 两两确认(组内通常很小;大组可先按 object 去重)
        for i in range(len(grp)):
            for j in range(i + 1, len(grp)):
                a, b = grp[i], grp[j]
                if a.object_value.strip().lower() == b.object_value.strip().lower():
                    continue
                resp = await gw.complete(
                    tenant_id=tenant_id, model=_S.model_haiku, system=_CONFLICT_SYSTEM,
                    user_content=json.dumps({
                        "subject": a.subject_entity, "predicate": a.predicate,
                        "value_a": a.object_value, "value_b": b.object_value,
                    }, ensure_ascii=False),
                    priority=Priority.COMPILE_BATCH, max_tokens=32)
                t = "".join(x.text for x in resp.content if x.type == "text")
                try:
                    if json.loads(re.sub(r"^```json\s*|\s*```$", "", t.strip())).get("contradict"):
                        a.provenance = Provenance.AMBIGUOUS
                        b.provenance = Provenance.AMBIGUOUS
                        a.contradicts.append(b.fact_id)
                        b.contradicts.append(a.fact_id)
                except json.JSONDecodeError:
                    pass
    return facts
