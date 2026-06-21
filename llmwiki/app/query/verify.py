"""Verify Pass:回答生成后的幻觉拦截。

逐 claim 校验:(a) 引用 span 存在且属本租户;(b) span 内容是否蕴含该 claim(NLI 式)。
不通过的 claim 标记为 unverified;若有效 claim 比例过低 → sufficient=False(触发升级)。
用 Haiku,成本低。
"""
from __future__ import annotations

import asyncio
import json
import re

from app.core.config import get_settings
from app.core.tenant import TenantContext
from app.llm.gateway import get_gateway, Priority
from app.query.tools import EvidenceClient

_S = get_settings()

VERIFY_SYSTEM = """你是事实校验器。给定一句结论和它引用的原文证据,判断证据是否支持该结论。
只输出 JSON:{"entailed": true/false, "score": 0.0~1.0}"""

_CITE = re.compile(r"\[([\w\-]+):([\w\-]+)\]")


def _split_claims(answer: str) -> list[tuple[str, list[tuple[str, str]]]]:
    """把回答按句切,提取每句的 [doc:span] 引用。"""
    claims = []
    for sent in re.split(r"(?<=[。.!?！？])\s*", answer):
        sent = sent.strip()
        if not sent:
            continue
        cites = _CITE.findall(sent)
        claims.append((sent, cites))
    return claims


async def _verify_one_claim(gw, client, tenant_id: str, text: str,
                            cites: list[tuple[str, str]]) -> dict:
    """校验单条 claim:逐个引用取证 + NLI,首个蕴含即通过(短路)。"""
    if not cites:
        return {"claim": text, "verified": None, "reason": "no_citation"}
    ok = False
    for doc_id, span_id in cites:
        try:
            span = await client.call("read_span", {"doc_id": doc_id, "span_id": span_id})
        except Exception:
            continue  # 引用不存在/越权 → 不计为通过
        # evidence 返回的 span 可能用 "content" 或 "text" 字段
        evidence_text = span.get("content") or span.get("text") or ""
        if not evidence_text:
            continue
        resp = await gw.complete(
            tenant_id=tenant_id, model=_S.model_haiku, system=VERIFY_SYSTEM,
            user_content=json.dumps(
                {"claim": text, "evidence": evidence_text}, ensure_ascii=False),
            priority=Priority.VERIFY, max_tokens=64)
        t = "".join(b.text for b in resp.content if b.type == "text")
        try:
            d = json.loads(re.sub(r"^```json\s*|\s*```$", "", t.strip()))
            if d.get("entailed") and d.get("score", 0) >= _S.verify_nli_threshold:
                ok = True
                break
        except json.JSONDecodeError:
            pass
    return {"claim": text, "verified": ok}


async def verify_answer(ctx: TenantContext, answer: str) -> dict:
    gw = get_gateway()
    client = EvidenceClient(ctx)
    claims = _split_claims(answer)
    try:
        # 各 claim 互相独立 → 并发校验;gather 保序,结果与串行一致。
        results = list(await asyncio.gather(
            *[_verify_one_claim(gw, client, ctx.tenant_id, text, cites)
              for text, cites in claims]
        ))
    finally:
        await client.aclose()

    cited = [r for r in results if r.get("verified") is not None]
    verified = [r for r in cited if r["verified"]]
    ratio = len(verified) / len(cited) if cited else 0.0
    return {
        "claims": results,
        "verified_ratio": ratio,
        "sufficient": bool(cited) and ratio >= 0.6,
    }
