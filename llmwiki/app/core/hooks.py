"""事件钩子(借自 llm-wiki v2 的 Automation: event-driven)。

把"记账"自动化:在自然调用点触发事件,handler 异步执行。
文档定义的事件:
  on_source        新源入库后:抽实体/更图/更新索引(已由 compile 链路承担)
  on_session_start 会话开始:按近期活动加载相关上下文
  on_session_end   会话结束:压缩为观察、归档洞察(crystallize/consolidation)
  on_query         问答后:质量达标则回填(crystallize)
  on_memory_write  写记忆:检查矛盾→触发 supersession
  on_schedule      定时:lint / consolidation / retention decay

设计为进程内轻量注册表;跨进程可换成 Redis Streams 事件(与编译 DAG 同构)。
"""
from __future__ import annotations

import asyncio
from collections import defaultdict
from typing import Awaitable, Callable

Event = str
Handler = Callable[..., Awaitable[None]]

ON_SOURCE = "on_source"
ON_SESSION_START = "on_session_start"
ON_SESSION_END = "on_session_end"
ON_QUERY = "on_query"
ON_MEMORY_WRITE = "on_memory_write"
ON_SCHEDULE = "on_schedule"

_registry: dict[Event, list[Handler]] = defaultdict(list)


def on(event: Event):
    """装饰器:注册 handler。"""
    def deco(fn: Handler) -> Handler:
        _registry[event].append(fn)
        return fn
    return deco


def register(event: Event, handler: Handler) -> None:
    _registry[event].append(handler)


async def emit(event: Event, **kwargs) -> None:
    """触发事件;handler 失败不影响主流程(隔离 + 不抛)。"""
    handlers = _registry.get(event, [])
    if not handlers:
        return
    results = await asyncio.gather(
        *(h(**kwargs) for h in handlers), return_exceptions=True)
    for r in results:
        if isinstance(r, Exception):
            # 钩子失败仅记录,不影响主流程
            print(f"[hook:{event}] handler error: {r}")


def emit_background(event: Event, **kwargs) -> None:
    """即发即忘:不阻塞主流程(如问答后回填)。"""
    asyncio.create_task(emit(event, **kwargs))
