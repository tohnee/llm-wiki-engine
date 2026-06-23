"""统一日志 + 指标。

日志:结构化 JSON,带 service / tenant_id / request_id;stdlib logging,无新依赖。
指标:轻量内存 counter / histogram + 文本格式 /metrics 输出(Prometheus 兼容),
     无 prometheus_client 依赖,生产可平替为官方 client(API 兼容)。
"""
from __future__ import annotations

import json
import logging
import os
import sys
import time
import threading
from typing import Any


# ============ 结构化日志 ============
class JsonFormatter(logging.Formatter):
    """每行一个 JSON 对象,字段:ts/level/service/logger/msg/extra*"""

    def __init__(self, service: str):
        super().__init__()
        self.service = service

    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": int(record.created * 1000),
            "level": record.levelname,
            "service": self.service,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        # 透传 logger.info(..., extra={...}) 注入的字段(tenant_id/request_id/...)
        for k, v in record.__dict__.items():
            if k in {"args", "msg", "levelname", "levelno", "name", "msecs",
                     "created", "pathname", "filename", "module", "exc_info",
                     "exc_text", "stack_info", "lineno", "funcName",
                     "relativeCreated", "thread", "threadName", "processName",
                     "process", "taskName"}:
                continue
            try:
                json.dumps(v)
                payload[k] = v
            except (TypeError, ValueError):
                payload[k] = str(v)
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False)


def setup_logging(service: str, level: str | int | None = None) -> logging.Logger:
    """幂等地配置 root logger 为 JSON 输出。各服务启动时调用一次。
    LEVEL 优先级:参数 > 环境 LOG_LEVEL > INFO。"""
    lvl = level or os.getenv("LOG_LEVEL", "INFO")
    if isinstance(lvl, str):
        lvl = logging.getLevelName(lvl.upper())
    root = logging.getLogger()
    # 清掉重复 handler 避免重复行
    for h in list(root.handlers):
        root.removeHandler(h)
    h = logging.StreamHandler(sys.stdout)
    h.setFormatter(JsonFormatter(service))
    root.addHandler(h)
    root.setLevel(lvl)
    return logging.getLogger(service)


# ============ 指标(轻量,无新依赖) ============
class _Counter:
    __slots__ = ("name", "help", "labelnames", "_values", "_lock")

    def __init__(self, name: str, help: str, labelnames: tuple[str, ...] = ()):
        self.name = name
        self.help = help
        self.labelnames = labelnames
        self._values: dict[tuple, float] = {}
        self._lock = threading.Lock()

    def inc(self, amount: float = 1.0, **labels: str) -> None:
        key = tuple(labels.get(k, "") for k in self.labelnames)
        with self._lock:
            self._values[key] = self._values.get(key, 0.0) + amount

    def collect(self) -> str:
        lines = [f"# HELP {self.name} {self.help}", f"# TYPE {self.name} counter"]
        with self._lock:
            for key, val in self._values.items():
                if self.labelnames:
                    labels = ",".join(f'{k}="{v}"' for k, v in zip(self.labelnames, key))
                    lines.append(f"{self.name}{{{labels}}} {val}")
                else:
                    lines.append(f"{self.name} {val}")
        return "\n".join(lines) + "\n"


class _Histogram:
    """简化直方图:固定桶 [0.1, 0.5, 1, 2, 5, 10, 30, 60, +Inf](秒)。"""
    _BUCKETS = (0.1, 0.5, 1.0, 2.0, 5.0, 10.0, 30.0, 60.0)

    def __init__(self, name: str, help: str, labelnames: tuple[str, ...] = ()):
        self.name = name
        self.help = help
        self.labelnames = labelnames
        self._counts: dict[tuple, list[int]] = {}
        self._sum: dict[tuple, float] = {}
        self._n: dict[tuple, int] = {}
        self._lock = threading.Lock()

    def observe(self, value: float, **labels: str) -> None:
        key = tuple(labels.get(k, "") for k in self.labelnames)
        with self._lock:
            counts = self._counts.setdefault(key, [0] * (len(self._BUCKETS) + 1))
            for i, b in enumerate(self._BUCKETS):
                if value <= b:
                    counts[i] += 1
            counts[-1] += 1  # +Inf
            self._sum[key] = self._sum.get(key, 0.0) + value
            self._n[key] = self._n.get(key, 0) + 1

    def collect(self) -> str:
        lines = [f"# HELP {self.name} {self.help}", f"# TYPE {self.name} histogram"]
        with self._lock:
            for key, counts in self._counts.items():
                label_str = ""
                if self.labelnames:
                    label_str = ",".join(f'{k}="{v}"' for k, v in zip(self.labelnames, key))
                sep = "," if label_str else ""
                for i, b in enumerate(self._BUCKETS):
                    le = 'le="{}"'.format(b)
                    lines.append("{}_bucket{{{}{}{}}} {}".format(
                        self.name, label_str, sep, le, counts[i]))
                le_inf = 'le="+Inf"'
                lines.append("{}_bucket{{{}{}{}}} {}".format(
                    self.name, label_str, sep, le_inf, counts[-1]))
                lines.append("{}_sum{{{}}} {}".format(
                    self.name, label_str, self._sum.get(key, 0.0)))
                lines.append("{}_count{{{}}} {}".format(
                    self.name, label_str, self._n.get(key, 0)))
        return "\n".join(lines) + "\n"


# ============ 全局注册表 ============
_METRICS: list[Any] = []


def counter(name: str, help: str, labelnames: tuple[str, ...] = ()) -> _Counter:
    c = _Counter(name, help, labelnames)
    _METRICS.append(c)
    return c


def histogram(name: str, help: str, labelnames: tuple[str, ...] = ()) -> _Histogram:
    h = _Histogram(name, help, labelnames)
    _METRICS.append(h)
    return h


def render_prometheus() -> str:
    """渲染所有注册指标为 Prometheus 文本格式。"""
    return "\n".join(m.collect() for m in _METRICS)


# ============ 内置指标(各服务统一使用) ============
LLM_CALLS = counter(
    "llmwiki_llm_calls_total", "LLM gateway calls", ("model", "priority", "status"))
LLM_LATENCY = histogram(
    "llmwiki_llm_latency_seconds", "LLM gateway latency", ("model",))
LLM_CACHE_HITS = counter(
    "llmwiki_llm_cache_hits_total", "LLM prompt cache hits", ("model",))
RETRIEVE_LATENCY = histogram(
    "llmwiki_retrieve_latency_seconds", "Hybrid retrieval latency", ("path",))
COMPILE_DOC = counter(
    "llmwiki_compile_documents_total", "Documents compiled by depth/status", ("depth", "status"))
HOOK_FIRES = counter(
    "llmwiki_hook_fires_total", "Hook events fired by event/status", ("event", "status"))


# ============ FastAPI /metrics 路由(可选挂载) ============
def install_metrics_route(app, path: str = "/metrics") -> None:
    """在 FastAPI app 上挂载 /metrics 端点(Prometheus 文本格式)。"""
    from fastapi import Response

    @app.get(path)
    async def _metrics():  # noqa: ANN202
        return Response(render_prometheus(), media_type="text/plain; version=0.0.4")


# ============ 简易计时器(上下文管理器) ============
class Timer:
    def __init__(self, hist: _Histogram, **labels: str):
        self.hist = hist
        self.labels = labels
        self._t0 = 0.0

    def __enter__(self) -> "Timer":
        self._t0 = time.perf_counter()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.hist.observe(time.perf_counter() - self._t0, **self.labels)
