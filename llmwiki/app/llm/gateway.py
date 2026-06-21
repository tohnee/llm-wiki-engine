"""LLM Gateway。

职责:
- 模型分层调用(Haiku 抽取 / Sonnet 推理)
- prompt caching(cache_control 标注稳定前缀)
- 优先级队列:interactive > verify > compile-realtime > compile-batch
- 按租户 token bucket 限流
- Batch API 提交(离线编译走批处理,成本减半且不占交互配额)
- 支持 Anthropic 原生 API 和 OpenAI 兼容 API(通过 LLM_PROVIDER 切换)
"""
from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from enum import IntEnum
from typing import Any, Optional

from app.core.config import get_settings

_S = get_settings()


class Priority(IntEnum):
    INTERACTIVE = 0       # 数值越小优先级越高
    VERIFY = 1
    COMPILE_REALTIME = 2
    COMPILE_BATCH = 3


@dataclass(order=True)
class _Job:
    priority: int
    seq: int
    fut: asyncio.Future = field(compare=False)
    coro: Any = field(compare=False)


class TokenBucket:
    """每租户 token bucket(粗粒度按调用计;生产可换成按 token 数)。"""
    def __init__(self, rate_per_sec: float, capacity: float):
        self.rate = rate_per_sec
        self.capacity = capacity
        self.tokens = capacity
        self.ts = time.monotonic()

    def allow(self, cost: float = 1.0) -> bool:
        now = time.monotonic()
        self.tokens = min(self.capacity, self.tokens + (now - self.ts) * self.rate)
        self.ts = now
        if self.tokens >= cost:
            self.tokens -= cost
            return True
        return False


class LLMGateway:
    def __init__(self, concurrency: int = 16):
        self.provider = _S.llm_provider.lower()
        self.mock = _S.llm_mock
        if not self.mock:
            if self.provider == "openai":
                from openai import AsyncOpenAI
                kwargs: dict[str, Any] = {"api_key": _S.openai_api_key or _S.anthropic_api_key}
                if _S.openai_base_url or _S.anthropic_base_url:
                    kwargs["base_url"] = _S.openai_base_url or _S.anthropic_base_url
                self.client = AsyncOpenAI(**kwargs)
            else:
                from anthropic import AsyncAnthropic
                kwargs = {"api_key": _S.anthropic_api_key}
                if _S.anthropic_base_url:
                    kwargs["base_url"] = _S.anthropic_base_url
                self.client = AsyncAnthropic(**kwargs)
        else:
            self.client = None  # mock 模式不需要真实客户端
        self._pq: asyncio.PriorityQueue[_Job] = asyncio.PriorityQueue()
        self._seq = 0
        self._sem = asyncio.Semaphore(concurrency)
        self._buckets: dict[str, TokenBucket] = {}
        self._worker_task: Optional[asyncio.Task] = None
        self.cache_hits = 0
        self.calls = 0

    def start(self) -> None:
        if self._worker_task is None:
            self._worker_task = asyncio.create_task(self._dispatch())

    def _bucket(self, tenant_id: str) -> TokenBucket:
        if tenant_id not in self._buckets:
            self._buckets[tenant_id] = TokenBucket(rate_per_sec=20, capacity=100)
        return self._buckets[tenant_id]

    async def _dispatch(self) -> None:
        while True:
            job = await self._pq.get()
            await self._sem.acquire()          # 在并发槽位可用前阻塞,真正限流
            asyncio.create_task(self._run(job))

    async def _run(self, job: _Job) -> None:
        try:
            res = await job.coro
            if not job.fut.done():
                job.fut.set_result(res)
        except Exception as e:  # noqa: BLE001
            if not job.fut.done():
                job.fut.set_exception(e)
        finally:
            self._sem.release()                # 任务完成后才释放槽位

    async def _enqueue(self, priority: Priority, coro) -> Any:
        self._seq += 1
        fut: asyncio.Future = asyncio.get_running_loop().create_future()
        await self._pq.put(_Job(priority=int(priority), seq=self._seq, fut=fut, coro=coro))
        return await fut

    # ---------------- 实时调用 ----------------
    async def complete(
        self,
        *,
        tenant_id: str,
        model: str,
        system: str,
        cached_prefix: Optional[str] = None,   # 稳定前缀(原文),标 cache_control
        user_content: str,
        priority: Priority = Priority.INTERACTIVE,
        max_tokens: int = 2048,
        tools: Optional[list] = None,
        messages: Optional[list] = None,
        retries: int = 5,                      # 失败重试次数(含 429 限流)
        timeout_sec: float = 300.0,            # 单次调用超时(秒)
    ) -> Any:
        if not self._bucket(tenant_id).allow():
            await asyncio.sleep(0.5)

        msgs = messages or [{"role": "user", "content": user_content}]

        # Mock 模式
        if self.mock:
            return await self._mock_complete(system, user_content, msgs, priority)

        last_exc = None
        for attempt in range(1 + retries):
            try:
                if self.provider == "openai":
                    return await asyncio.wait_for(
                        self._complete_openai(model, system, cached_prefix, msgs, priority, max_tokens, tools),
                        timeout=timeout_sec,
                    )
                return await asyncio.wait_for(
                    self._complete_anthropic(model, system, cached_prefix, msgs, priority, max_tokens, tools),
                    timeout=timeout_sec,
                )
            except (asyncio.TimeoutError, Exception) as e:
                last_exc = e
                if attempt < retries:
                    # 429 限流:指数退避,初始等待更长
                    err_msg = str(e)
                    if "429" in err_msg or "rate" in err_msg.lower() or "limit" in err_msg.lower():
                        base_delay = 5.0
                    else:
                        base_delay = 2.0
                    backoff = base_delay * (2 ** attempt)  # 指数退避:5,10,20,40,80
                    cap = min(backoff, 60.0)                # capped 60s
                    print(f"[gateway] {model} call attempt {attempt+1} failed (429/rate), retrying in {cap:.0f}s", flush=True)
                    await asyncio.sleep(cap)
                else:
                    raise last_exc

        raise RuntimeError("unreachable")

    async def _complete_anthropic(
        self, model, system, cached_prefix, msgs, priority, max_tokens, tools
    ) -> Any:
        sys_blocks: list[dict] = [{"type": "text", "text": system}]
        if cached_prefix:
            sys_blocks.append({
                "type": "text", "text": cached_prefix,
                "cache_control": {"type": "ephemeral"},
            })

        async def _call():
            self.calls += 1
            kwargs: dict[str, Any] = dict(
                model=model, max_tokens=max_tokens, system=sys_blocks, messages=msgs)
            if tools:
                kwargs["tools"] = tools
            resp = await self.client.messages.create(**kwargs)
            usage = getattr(resp, "usage", None)
            if usage and getattr(usage, "cache_read_input_tokens", 0):
                self.cache_hits += 1
            return resp

        return await self._enqueue(priority, _call())

    async def _complete_openai(
        self, model, system, cached_prefix, msgs, priority, max_tokens, tools
    ) -> Any:
        """OpenAI 兼容 API 调用。

        将 Anthropic 风格的 system + messages 转换为 OpenAI chat 格式。
        返回一个与 Anthropic response 结构兼容的包装对象,使调用方代码无需改动。
        """
        full_system = system
        if cached_prefix:
            full_system = f"{system}\n\n{cached_prefix}"

        # 转换 messages:确保有 system message 在最前
        oai_msgs: list[dict] = []
        if full_system:
            oai_msgs.append({"role": "system", "content": full_system})
        for m in msgs:
            role = m.get("role", "user")
            content = m.get("content", "")
            # Anthropic content 可能是 list[{type:text,text:...}],展平为字符串
            if isinstance(content, list):
                content = "\n".join(
                    b.get("text", "") for b in content if b.get("type") == "text")
            oai_msgs.append({"role": role, "content": content})

        async def _call():
            self.calls += 1
            kwargs: dict[str, Any] = dict(
                model=model, max_tokens=max_tokens, messages=oai_msgs)
            # OpenAI tool calling(格式不同,简化处理:仅在无 tools 时走纯文本)
            resp = await self.client.chat.completions.create(**kwargs)
            return _OAIResponseWrapper(resp)

        return await self._enqueue(priority, _call())

    async def _mock_complete(self, system, user_content, msgs, priority) -> Any:
        """Mock LLM 响应:根据 system prompt 类型返回结构化结果。

        支持:L2 抽取(facts/entities JSON)、路由(simple/complex)、
        验证(NLI JSON)、摘要、问答。
        """
        import json as _json
        import re as _re

        # 提取用户消息文本
        text = user_content
        if not text and msgs:
            last = msgs[-1]
            c = last.get("content", "")
            if isinstance(c, list):
                text = "\n".join(b.get("text", "") for b in c if b.get("type") == "text")
            else:
                text = str(c)

        # 根据 system prompt 判断响应类型
        sys_lower = system.lower() if system else ""

        if "fact" in sys_lower and "entit" in sys_lower:
            # L2 抽取:返回空但合法的 JSON(无 fact/entity)
            # 尝试从文本中简单提取"X是Y"模式的事实
            facts = []
            entities = []
            for m in _re.finditer(r"([^\s,，。.]{2,10})的?(?:预算|支出|费用|价值|金额)为?(\d+万?元?)", text):
                subj, obj = m.group(1), m.group(2)
                facts.append({"subject": subj, "predicate": "预算", "object": obj,
                              "qualifiers": {}, "source_span_index": [0]})
                entities.append({"name": subj, "type": "project", "span_index": [0]})
            for m in _re.finditer(r"([^\s,，。.]{2,5})的?(?:负责人|领导|主管)是([^\s,，。.]{2,5})", text):
                subj, obj = m.group(1), m.group(2)
                facts.append({"subject": subj, "predicate": "负责人", "object": obj,
                              "qualifiers": {}, "source_span_index": [0]})
                entities.append({"name": subj, "type": "project", "span_index": [0]})
                entities.append({"name": obj, "type": "person", "span_index": [0]})
            for m in _re.finditer(r"([^\s,，。.]{2,5})的?(?:供应商|合作方)是([^\s,，。.]{2,10})", text):
                subj, obj = m.group(1), m.group(2)
                facts.append({"subject": subj, "predicate": "供应商", "object": obj,
                              "qualifiers": {}, "source_span_index": [0]})
                entities.append({"name": subj, "type": "project", "span_index": [0]})
                entities.append({"name": obj, "type": "organization", "span_index": [0]})
            for m in _re.finditer(r"([^\s,，。.]{2,5})的?团队有(\d+)名?", text):
                subj, obj = m.group(1), m.group(2)
                facts.append({"subject": subj, "predicate": "团队规模", "object": obj + "人",
                              "qualifiers": {}, "source_span_index": [0]})
                entities.append({"name": subj, "type": "project", "span_index": [0]})

            result = _json.dumps({"facts": facts, "entities": entities}, ensure_ascii=False)
            return _MockResponse(result)

        if "simple" in sys_lower and "complex" in sys_lower:
            # 路由判断
            return _MockResponse("simple")

        if "entailed" in sys_lower or "nli" in sys_lower:
            # NLI 验证
            return _MockResponse(_json.dumps({"entailed": True, "score": 0.9}))

        if "摘要" in system or "summary" in sys_lower or "summarize" in sys_lower:
            # 摘要:返回文本前200字
            return _MockResponse(text[:200] + "..." if len(text) > 200 else text)

        # 默认:问答
        return _MockResponse(f"基于文档内容的回答(模拟):{text[:100]}")

    # ---------------- Batch 提交(离线编译) ----------------
    async def submit_batch(self, requests: list[dict]) -> str:
        """requests: [{custom_id, params}]。返回 batch_id;轮询在 compile worker 内做。

        OpenAI 兼容模式下不支持 batch,调用方应走实时路径。
        """
        if self.provider == "openai":
            raise RuntimeError("batch API not supported in OpenAI-compatible mode")
        batch = await self.client.messages.batches.create(requests=requests)
        return batch.id

    async def poll_batch(self, batch_id: str) -> Optional[list[dict]]:
        if self.provider == "openai":
            raise RuntimeError("batch API not supported in OpenAI-compatible mode")
        b = await self.client.messages.batches.retrieve(batch_id)
        if b.processing_status != "ended":
            return None
        results = []
        async for r in self.client.messages.batches.results(batch_id):
            results.append({"custom_id": r.custom_id, "result": r.result})
        return results

    @property
    def cache_hit_rate(self) -> float:
        return self.cache_hits / self.calls if self.calls else 0.0


class _OAIResponseWrapper:
    """将 OpenAI chat completion 响应包装为 Anthropic Messages response 兼容结构。

    调用方(如 l2_extract.parse_extract_result)主要读取 resp.content[0].text,
    此 wrapper 提供该访问路径。
    """

    def __init__(self, oai_resp):
        choice = oai_resp.choices[0]
        text = choice.message.content or ""
        self.content = [_OAIContentBlock(text=text)]
        self.model = oai_resp.model
        self.role = "assistant"
        self.stop_reason = choice.finish_reason
        self.usage = _OAIUsage(oai_resp.usage)

    def __getattr__(self, name):
        return None


class _OAIContentBlock:
    def __init__(self, text: str):
        self.type = "text"
        self.text = text


class _OAIUsage:
    def __init__(self, usage):
        self.input_tokens = getattr(usage, "prompt_tokens", 0) if usage else 0
        self.output_tokens = getattr(usage, "completion_tokens", 0) if usage else 0
        self.cache_read_input_tokens = 0


class _MockResponse:
    """Mock LLM 响应,兼容 Anthropic Messages response 结构。"""
    def __init__(self, text: str):
        self.content = [_OAIContentBlock(text=text)]
        self.model = "mock"
        self.role = "assistant"
        self.stop_reason = "end_turn"
        self.usage = _OAIUsage(None)


_gateway: Optional[LLMGateway] = None


def get_gateway() -> LLMGateway:
    global _gateway
    if _gateway is None:
        _gateway = LLMGateway()
        _gateway.start()
    return _gateway
