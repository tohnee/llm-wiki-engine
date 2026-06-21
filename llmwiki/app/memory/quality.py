"""质量与自愈(借自 llm-wiki v2 的 Quality and self-correction)。

- quality_score:对生成内容打分(结构/是否引用/与库一致),低于阈值标记。
- resolve_contradiction:对一组矛盾 fact,按 来源数 / 最近确认 / retention 提议胜者,
  其余 supersede 为 stale(从"检测"升级到"解决")。
- self_heal:孤立实体标记、stale 链接修复(自愈,而非只提示)。
"""
from __future__ import annotations

import re

from app.memory.lifecycle import decayed_confidence, supersede


def quality_score(text: str, require_citation: bool = True) -> dict:
    """轻量启发式质量分(0~1)。生产可换 LLM 二次评估。"""
    score, reasons = 1.0, []
    if len(text.strip()) < 20:
        score -= 0.4; reasons.append("too_short")
    has_cite = bool(re.search(r"\[[\w\-]+:[\w\-]+\]", text))
    if require_citation and not has_cite:
        score -= 0.4; reasons.append("no_citation")
    if not re.search(r"[。.!?！?]", text):
        score -= 0.1; reasons.append("no_sentence_boundary")
    return {"score": round(max(0.0, score), 2), "flags": reasons,
            "pass": score >= 0.6}


def resolve_contradiction(facts: list[dict]) -> dict:
    """输入一组互相矛盾的 fact(dict),提议胜者 + 对其余生成 supersede 补丁。
    判据优先级:source_count > last_confirmed > retention。人可覆盖。"""
    if len(facts) < 2:
        return {"winner": facts[0]["fact_id"] if facts else None, "supersede": []}

    def key(f):
        r, _c = decayed_confidence(f)
        return (int(f.get("source_count", 1)), f.get("last_confirmed", 0.0), r)

    ranked = sorted(facts, key=key, reverse=True)
    winner = ranked[0]
    patches = [supersede(f["fact_id"], winner["fact_id"]) for f in ranked[1:]]
    return {"winner": winner["fact_id"], "supersede": patches,
            "reason": f"src={winner.get('source_count')},recent,retention"}


def self_heal_plan(orphan_entity_ids: list[str], stale_fact_ids: list[str]) -> list[dict]:
    """生成自愈动作清单(供 daily 维护执行)。低风险自动、高风险入人审。"""
    actions = []
    for eid in orphan_entity_ids:
        actions.append({"action": "link_or_flag_orphan", "target": eid, "risk": "low"})
    for fid in stale_fact_ids:
        actions.append({"action": "mark_stale", "target": fid, "risk": "low"})
    return actions
