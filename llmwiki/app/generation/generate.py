"""生成核心:基于问答证据或指定文档,用 Messages API 产出结构化内容。

设计原则:模型只产出"内容/数据规范"(markdown 报告、图表 spec、表格 JSON),
不直接产出 PPTX/XLSX 二进制——那由 render.py 的确定性渲染层完成。
证据仍走只读 Evidence API 取证,生成产物可回链 span(报告里保留 [doc:span])。

artifact_type: report(markdown) | chart(图表 spec) | table(表格 JSON) | slides(PPT 大纲)
"""
from __future__ import annotations

import json
import re

from app.core.config import get_settings
from app.core.tenant import TenantContext
from app.llm.gateway import get_gateway, Priority
from app.query.tools import EvidenceClient

_S = get_settings()

_REPORT_SYS = """你基于提供的证据 span 撰写结构化中文报告(markdown)。
要求:1) 只用证据内容,不引入外部知识;2) 关键结论后保留 [doc_id:span_id] 引用;
3) 结构清晰(标题/小节/要点);4) 不编造数字,证据不足处明确说明。只输出 markdown。"""

_CHART_SYS = """你基于证据抽取可用于绘图的数据,输出 Vega-Lite 风格的图表规范 JSON。
只输出 JSON,格式:
{"chart_type":"bar|line|pie","title":"","x_field":"","y_field":"",
 "data":[{"x":"","y":0}], "source_span_ids":[]}
数字必须来自证据,不得编造。"""

_TABLE_SYS = """你基于证据整理为表格,只输出 JSON:
{"columns":["列1","列2"], "rows":[["",""]], "source_span_ids":[]}
单元格内容必须来自证据。"""

_SLIDES_SYS = """你基于证据生成演示大纲,只输出 JSON:
{"title":"", "slides":[{"title":"","bullets":["",""],"source_span_ids":[]}]}
每条要点须有证据支撑,不编造。"""

_SYS = {"report": _REPORT_SYS, "chart": _CHART_SYS, "table": _TABLE_SYS, "slides": _SLIDES_SYS}


def _strip_json(t: str) -> str:
    return re.sub(r"^```json\s*|\s*```$", "", t.strip())


async def _gather_evidence(ctx: TenantContext, query: str, document_ids: list[str] | None) -> list[dict]:
    """复用只读 Evidence API 取证:navigate 圈 scope → search 取 span。"""
    client = EvidenceClient(ctx)
    try:
        scope = document_ids
        if not scope:
            nav = await client.call("navigate", {"query": query, "hops": 1})
            scope = nav.get("scope_document_ids") or None
        res = await client.call("search", {"query": query, "document_ids": scope, "k": 12})
        if res.get("tier") == 0:           # tier-0 摘要级,需要落正文则强制 tier-1
            res = await client.call("search", {"query": query, "document_ids": scope, "k": 12, "index_only": False})
        return res.get("results", [])
    finally:
        await client.aclose()


async def generate(
    ctx: TenantContext, instruction: str, artifact_type: str = "report",
    document_ids: list[str] | None = None, evidence: list[dict] | None = None,
) -> dict:
    """生成结构化产物。evidence 可由调用方直接传入(复用问答结果),否则自行取证。"""
    if artifact_type not in _SYS:
        raise ValueError(f"unsupported artifact_type: {artifact_type}")
    spans = evidence if evidence is not None else await _gather_evidence(ctx, instruction, document_ids)
    ev_block = "\n".join(
        f"[{s.get('doc_id', s.get('document_id'))}:{s['span_id']}] {s['content']}"
        for s in spans)

    gw = get_gateway()
    resp = await gw.complete(
        tenant_id=ctx.tenant_id, model=_S.model_sonnet, system=_SYS[artifact_type],
        user_content=f"任务:{instruction}\n\n证据:\n{ev_block}",
        priority=Priority.INTERACTIVE, max_tokens=4096)
    text = "".join(b.text for b in resp.content if b.type == "text")

    if artifact_type == "report":
        return {"type": "report", "format": "markdown", "content": text,
                "evidence_count": len(spans)}
    try:
        spec = json.loads(_strip_json(text))
    except json.JSONDecodeError:
        spec = {"error": "model did not return valid JSON", "raw": text[:500]}
    return {"type": artifact_type, "format": "json", "spec": spec, "evidence_count": len(spans)}
