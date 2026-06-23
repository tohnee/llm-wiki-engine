"""pytest 共享 fixtures:统一 stub 重依赖,使纯逻辑测试无需安装 asyncpg/redis/anthropic。

凡 test_*.py 用纯算法/数据结构的测试都默认进入 smoke 集合。
需要真实基础设施的测试用 `@pytest.mark.integration` 显式标注,默认 CI 不跑。
"""
from __future__ import annotations

import sys
import types

import pytest


@pytest.fixture(scope="session", autouse=True)
def _stub_heavy_deps():
    """stub 重依赖。在最早期完成,避免 import 链失败。"""
    if "asyncpg" not in sys.modules:
        sys.modules["asyncpg"] = types.ModuleType("asyncpg")
    if "anthropic" not in sys.modules:
        m = types.ModuleType("anthropic")
        m.AsyncAnthropic = object
        sys.modules["anthropic"] = m
    if "redis" not in sys.modules:
        r = types.ModuleType("redis")
        ra = types.ModuleType("redis.asyncio")
        ra.Redis = object
        ra.from_url = lambda *a, **k: None
        ra.ResponseError = Exception
        sys.modules["redis"] = r
        sys.modules["redis.asyncio"] = ra
    if "app.llm.embed" not in sys.modules:
        e = types.ModuleType("app.llm.embed")
        async def _embed(texts):
            return [[0.0] * 1024 for _ in texts]
        e.embed = _embed
        e.embed_sync = lambda texts: [[0.0] * 1024 for _ in texts]
        e.rerank = lambda q, c: [(s, 1.0) for s, _ in c]
        sys.modules["app.llm.embed"] = e
    yield
