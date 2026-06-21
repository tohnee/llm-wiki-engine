"""知识健康审计(借自 obsidian-wiki 的 wiki-lint)。

离线扫描租户 KG,产出待修复清单,核心是**按 hub 度数加权的错误传播优先级**:
高度数实体(被大量关系引用)上的问题会经由链接扩散到全库,优先修。

规则(可配置阈值):
  R1 实体的 ambiguous fact 比例 > 15%  → 报警(来源互相打架)
  R2 inferred fact 且无 source_span_ids → "无源臆测"
  R3 Hub 实体(度数 top 10%)若 inferred 比例 > 20% → 加急(错误传播面最大)
输出按 priority 降序,priority = base_severity * (1 + hub_weight)。
不自动改写;高风险进人审队列,低风险可走 gated auto-fix(企业化:不照搬 obsidian-wiki 的"人确认默认")。
"""
from __future__ import annotations

from dataclasses import dataclass

from app.db.store import Store

R1_AMBIGUOUS_RATIO = 0.15
R2_FLAG_UNSOURCED_INFERRED = True
R3_HUB_INFERRED_RATIO = 0.20


@dataclass
class LintFinding:
    entity_id: str
    entity_name: str
    rule: str
    detail: str
    priority: float


async def audit_tenant(store: Store, tenant_id: str, schema=None) -> list[LintFinding]:
    findings: list[LintFinding] = []
    # schema 感知:阈值从租户 schema 读取,回退到模块默认常量
    r1_threshold = schema.lint_ambiguous_ratio if schema else R1_AMBIGUOUS_RATIO
    r3_threshold = schema.lint_hub_inferred_ratio if schema else R3_HUB_INFERRED_RATIO
    async with store.pool.acquire() as con:
        # 实体度数(被 relation 引用次数)→ hub 权重
        deg_rows = await con.fetch(
            """SELECT e.entity_id, e.name,
                      COALESCE(d.deg,0) AS deg
               FROM entities e
               LEFT JOIN (
                 SELECT ent, COUNT(*) deg FROM (
                   SELECT source_entity ent FROM relations WHERE tenant_id=$1
                   UNION ALL
                   SELECT target_entity ent FROM relations WHERE tenant_id=$1
                 ) u GROUP BY ent
               ) d ON d.ent = e.entity_id
               WHERE e.tenant_id=$1""",
            tenant_id)
        if not deg_rows:
            return findings
        degs = sorted((r["deg"] for r in deg_rows), reverse=True)
        hub_cut = degs[max(0, len(degs) // 10 - 1)] if len(degs) >= 10 else (degs[0] if degs else 0)

        for r in deg_rows:
            eid, name, deg = r["entity_id"], r["name"], r["deg"]
            hub_weight = deg / (degs[0] + 1e-9) if degs[0] else 0.0  # 归一化度数
            is_hub = deg >= hub_cut and deg > 0

            frows = await con.fetch(
                "SELECT provenance, source_span_ids FROM facts "
                "WHERE tenant_id=$1 AND subject_entity=$2", tenant_id, eid)
            if not frows:
                continue
            n = len(frows)
            n_amb = sum(1 for f in frows if f["provenance"] == "ambiguous")
            n_inf = sum(1 for f in frows if f["provenance"] == "inferred")
            n_unsourced_inf = sum(
                1 for f in frows
                if f["provenance"] == "inferred" and not f["source_span_ids"])

            if n_amb / n > r1_threshold:
                findings.append(LintFinding(
                    eid, name, "R1_ambiguous",
                    f"ambiguous {n_amb}/{n}={n_amb/n:.0%} 超阈值(来源矛盾)",
                    priority=(n_amb / n) * (1 + hub_weight)))
            if R2_FLAG_UNSOURCED_INFERRED and n_unsourced_inf > 0:
                findings.append(LintFinding(
                    eid, name, "R2_unsourced_inferred",
                    f"{n_unsourced_inf} 条无源推测(inferred 且无 span)",
                    priority=0.5 * (1 + hub_weight)))
            if is_hub and n_inf / n > r3_threshold:
                findings.append(LintFinding(
                    eid, name, "R3_hub_inferred",
                    f"Hub 节点(度数{deg})inferred {n_inf/n:.0%}>20%,错误会扩散,加急",
                    priority=(n_inf / n) * (1 + 2 * hub_weight)))  # hub 双倍权重

    findings.sort(key=lambda x: x.priority, reverse=True)
    return findings


async def wiki_status(store: Store, tenant_id: str) -> dict:
    """知识库洞察(对应 obsidian-wiki wiki-status):hubs / orphans / 规模。
    供前端健康面板与 daily 维护使用。"""
    async with store.pool.acquire() as con:
        n_ent = await con.fetchval("SELECT count(*) FROM entities WHERE tenant_id=$1", tenant_id)
        n_rel = await con.fetchval("SELECT count(*) FROM relations WHERE tenant_id=$1", tenant_id)
        n_fact = await con.fetchval("SELECT count(*) FROM facts WHERE tenant_id=$1", tenant_id)
        n_doc = await con.fetchval("SELECT count(*) FROM documents WHERE tenant_id=$1", tenant_id)
        amb = await con.fetchval(
            "SELECT count(*) FROM facts WHERE tenant_id=$1 AND provenance='ambiguous'", tenant_id)
        # hubs:度数最高的实体
        hubs = await con.fetch(
            """SELECT e.name, COALESCE(d.deg,0) deg FROM entities e
               LEFT JOIN (SELECT ent,count(*) deg FROM (
                 SELECT source_entity ent FROM relations WHERE tenant_id=$1
                 UNION ALL SELECT target_entity ent FROM relations WHERE tenant_id=$1) u
                 GROUP BY ent) d ON d.ent=e.entity_id
               WHERE e.tenant_id=$1 ORDER BY deg DESC LIMIT 10""", tenant_id)
        # orphans:无任何关系的实体数
        orphans = await con.fetchval(
            """SELECT count(*) FROM entities e WHERE e.tenant_id=$1
               AND NOT EXISTS (SELECT 1 FROM relations r WHERE r.tenant_id=$1
                 AND (r.source_entity=e.entity_id OR r.target_entity=e.entity_id))""",
            tenant_id)
    return {
        "documents": n_doc, "entities": n_ent, "relations": n_rel, "facts": n_fact,
        "ambiguous_facts": amb,
        "ambiguous_ratio": round(amb / n_fact, 3) if n_fact else 0.0,
        "orphan_entities": orphans,
        "hubs": [{"name": h["name"], "degree": h["deg"]} for h in hubs],
    }
