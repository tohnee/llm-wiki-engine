"""查询路径:复杂度路由 + Fast QA + Agentic QA。

- Router(Haiku):simple / complex / summary,把 70~85% 流量分到 Fast 路径。
- Fast QA:自写 Messages API tool-use loop,单次/少量检索即可答,P50 < 4s。
- Agentic QA:多轮取证(Plan→Navigate→Collect→Reason),用 SDK 的工具循环编排。
  本实现用 Messages API 的 tool loop 直接编排(不强依赖 Agent SDK,便于替换)。
- 两条路径都接 Verify。
- OpenAI 兼容模式:不支持 Anthropic tool_use,走直接检索+生成路径。
"""
from __future__ import annotations

import json
import re

from app.core.config import get_settings
from app.core.tenant import TenantContext
from app.llm.gateway import get_gateway, Priority
from app.query.tools import EvidenceClient, TOOLS
from app.query.verify import verify_answer

_S = get_settings()

ROUTER_SYSTEM = """判断问题复杂度,只输出一个词:
simple  = 单文档、单点、一次检索即可答
complex = 多跳推理 / 跨多个文档 / 需要比对
summary = 概述/综述类
只输出 simple 或 complex 或 summary。"""

ANSWER_SYSTEM = """你基于检索到的证据 span 回答问题。严格要求:
1. 只用工具返回的 span 内容作答,不引入外部知识。
2. 每个具体结论后用 [doc_id:span_id] 标注其证据来源。
3. 多跳/跨文档问题:先 navigate 定位范围,再在范围内 search,必要时 read_span 取原文。
4. 证据不足时明确说"文档中未找到明确依据",不要编造。"""


async def route(tenant_id: str, question: str) -> str:
    gw = get_gateway()
    resp = await gw.complete(
        tenant_id=tenant_id, model=_S.model_haiku, system=ROUTER_SYSTEM,
        user_content=question, priority=Priority.INTERACTIVE, max_tokens=8)
    text = "".join(b.text for b in resp.content if b.type == "text").strip().lower()
    for k in ("simple", "complex", "summary"):
        if k in text:
            return k
    return "complex"


async def _tool_loop(ctx: TenantContext, question: str, model: str, max_turns: int,
                     history: list[dict] | None = None) -> dict:
    """通用 tool-use 循环。Fast 与 Agentic 共用,区别仅在 model 与 max_turns。
    history: 该 (tenant,user,session) 的历史文本轮次,注入上下文(隔离已由 key 保证)。"""
    gw = get_gateway()
    client = EvidenceClient(ctx)
    messages = list(history or [])
    messages.append({"role": "user", "content": question})
    try:
        for _ in range(max_turns):
            resp = await gw.complete(
                tenant_id=ctx.tenant_id, model=model, system=ANSWER_SYSTEM,
                user_content="", messages=messages, tools=TOOLS,
                priority=Priority.INTERACTIVE, max_tokens=2048)
            messages.append({"role": "assistant", "content": resp.content})

            tool_uses = [b for b in resp.content if b.type == "tool_use"]
            if not tool_uses:
                answer = "".join(b.text for b in resp.content if b.type == "text")
                return {"answer": answer, "messages": messages}

            tool_results = []
            for tu in tool_uses:
                try:
                    out = await client.call(tu.name, tu.input)
                except Exception as e:  # noqa: BLE001
                    out = {"error": str(e)}
                tool_results.append({
                    "type": "tool_result", "tool_use_id": tu.id,
                    "content": json.dumps(out, ensure_ascii=False)[:8000]})
            messages.append({"role": "user", "content": tool_results})

        # 超出轮数,强制收口
        resp = await gw.complete(
            tenant_id=ctx.tenant_id, model=model, system=ANSWER_SYSTEM,
            user_content="", messages=messages + [
                {"role": "user", "content": "请基于已有证据给出最终回答,若不足请说明。"}],
            priority=Priority.INTERACTIVE, max_tokens=1024)
        return {"answer": "".join(b.text for b in resp.content if b.type == "text"),
                "messages": messages}
    finally:
        await client.aclose()


async def _direct_search_answer(ctx: TenantContext, question: str, model: str,
                                 history: list[dict] | None = None) -> dict:
    """OpenAI 兼容模式:直接检索 + 生成(不走 tool-use loop)。

    1. 用 EvidenceClient.search 检索相关 span
    2. 把 span 内容拼入 prompt,让 LLM 基于证据回答
    """
    gw = get_gateway()
    client = EvidenceClient(ctx)
    try:
        evidence = await client.call("search", {"query": question, "top_k": 8})
        if "error" in evidence:
            return {"answer": f"检索失败:{evidence['error']}", "messages": []}

        # tier-0 命中:索引级回答(summary 可答),直接使用
        if evidence.get("tier") == 0 and evidence.get("answer"):
            return {"answer": evidence["answer"], "messages": []}

        spans = evidence.get("spans") or evidence.get("results") or []
        evidence_text = "\n\n".join(
            f"[{s.get('document_id','?')}:{s.get('span_id','?')}] {s.get('content','')}"
            for s in spans[:8])

        user_msg = f"问题:{question}\n\n检索到的证据:\n{evidence_text}\n\n请基于以上证据回答,每个结论后标注 [doc_id:span_id]。"
        messages = list(history or [])
        messages.append({"role": "user", "content": user_msg})

        resp = await gw.complete(
            tenant_id=ctx.tenant_id, model=model, system=ANSWER_SYSTEM,
            user_content="", messages=messages,
            priority=Priority.INTERACTIVE, max_tokens=2048)
        answer = "".join(b.text for b in resp.content if b.type == "text")
        return {"answer": answer, "messages": messages}
    finally:
        await client.aclose()


async def _load_session_context(ctx: TenantContext) -> str | None:
    """读取 on_session_start 钩子写入 Redis 的会话上下文。"""
    try:
        import redis.asyncio as aioredis
        from app.core.config import get_settings
        r = aioredis.from_url(get_settings().redis_url, decode_responses=True)
        ctx_str = await r.get(f"sess_ctx:{ctx.tenant_id}:{ctx.user_id}:{ctx.session_id}")
        await r.aclose()
        return ctx_str
    except Exception:
        return None


async def answer(ctx: TenantContext, question: str, memory=None) -> dict:
    """对外主入口:路由 → 取证 → verify(不足则升级 Agentic 重答)。
    memory: 可选 MemoryStore;提供时按 (tenant,user,session) 注入并持久化历史。"""
    history = await memory.history_messages(ctx) if memory else None

    # OpenAI 兼容模式:走直接检索+生成路径(不支持 tool-use loop)
    if _S.llm_provider.lower() == "openai":
        res = await _direct_search_answer(ctx, question, _S.model_sonnet, history)
        verdict = await verify_answer(ctx, res["answer"])
        res["verify"] = verdict
        if memory:
            await memory.append(ctx, "user", question)
            await memory.append(ctx, "assistant", res["answer"])
        from app.core import hooks
        hooks.emit_background(hooks.ON_QUERY, ctx=ctx, question=question,
                              answer=res["answer"],
                              verified_ratio=res.get("verify", {}).get("verified_ratio"))
        return res

    mode = await route(ctx.tenant_id, question)

    if mode == "simple":
        res = await _tool_loop(ctx, question, _S.model_haiku, max_turns=3, history=history)
    else:  # complex / summary
        res = await _tool_loop(ctx, question, _S.model_sonnet,
                               max_turns=_S.agent_max_tool_turns, history=history)

    verdict = await verify_answer(ctx, res["answer"])
    res["verify"] = verdict

    # 兜底:simple 路径证据不足 → 升级 Agentic 重答一次
    if mode == "simple" and not verdict["sufficient"]:
        res = await _tool_loop(ctx, question, _S.model_sonnet,
                               max_turns=_S.agent_max_tool_turns, history=history)
        res["verify"] = await verify_answer(ctx, res["answer"])
        res["escalated"] = True

    # 持久化本轮(仅文本轮次;隔离由 memory key 保证)
    if memory:
        await memory.append(ctx, "user", question)
        await memory.append(ctx, "assistant", res["answer"])

    # on_query 钩子:质量达标则结晶回填(即发即忘,不阻塞回答)
    from app.core import hooks
    hooks.emit_background(hooks.ON_QUERY, ctx=ctx, question=question,
                          answer=res["answer"],
                          verified_ratio=res.get("verify", {}).get("verified_ratio"))

    return res
