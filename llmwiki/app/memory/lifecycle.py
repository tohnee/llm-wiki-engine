"""记忆生命周期(借自 llm-wiki v2 的"missing layer")。

把扁平的等权事实升级为有生命周期的活模型:
- confidence:来源数 + 最近确认 + 是否被矛盾 共同决定
- forgetting:Ebbinghaus 指数衰减,retention = exp(-Δt / τ);每次强化(新来源/访问)重置
- reinforcement:同一事实再次被抽到 → source_count++、last_confirmed 刷新、retention 重置
- supersession:新事实取代旧事实(版本化:旧的保留但 stale + superseded_by 链接)

τ(半衰期)按内容类型区分:架构决策衰减慢,瞬时 bug 衰减快(此处用谓词启发式)。
"""
from __future__ import annotations

import math
import time

# 半衰期(天),按谓词类别启发式区分衰减速度
_TAU_SLOW = 365.0    # 架构/定义类:衰减慢
_TAU_FAST = 30.0     # 瞬时/状态类:衰减快
_SLOW_PREDICATES = {"is_a", "defined_as", "architecture", "depends_on", "part_of", "owns", "develops"}


def _tau_days(predicate: str) -> float:
    p = (predicate or "").lower()
    return _TAU_SLOW if any(k in p for k in _SLOW_PREDICATES) else _TAU_FAST


def retention_now(last_confirmed: float, predicate: str, now: float | None = None) -> float:
    """Ebbinghaus:retention = exp(-Δt / τ)。Δt 为距上次确认的天数。"""
    now = now or time.time()
    if last_confirmed <= 0:
        return 1.0
    dt_days = max(0.0, (now - last_confirmed) / 86400.0)
    tau = _tau_days(predicate)
    return math.exp(-dt_days / tau)


def confidence_score(source_count: int, retention: float, contradicted: bool, stale: bool) -> float:
    """综合置信度 ∈ [0,1]。来源越多越高;retention 越低越低;矛盾/过时大幅降权。"""
    base = 1.0 - 1.0 / (1.0 + source_count)        # 1源≈0.5, 2源≈0.67, 3源≈0.75 …
    score = base * retention
    if contradicted:
        score *= 0.5
    if stale:
        score *= 0.3
    return round(min(1.0, max(0.0, score)), 3)


def reinforce(fact: dict, now: float | None = None) -> dict:
    """同一事实被再次确认:来源+1、刷新确认时间、retention 重置为 1。"""
    now = now or time.time()
    fact["source_count"] = int(fact.get("source_count", 1)) + 1
    fact["last_confirmed"] = now
    fact["retention"] = 1.0
    fact["confidence"] = confidence_score(
        fact["source_count"], 1.0, bool(fact.get("contradicts")), bool(fact.get("stale")))
    return fact


def supersede(old_fact_id: str, new_fact_id: str) -> dict:
    """返回对旧事实的更新补丁:标记被取代 + stale(保留不删,版本化)。"""
    return {"fact_id": old_fact_id, "superseded_by": new_fact_id, "stale": True}


def decayed_confidence(fact: dict, now: float | None = None) -> tuple[float, float]:
    """计算当前 retention 与 confidence(供定时 decay 与查询期降权用)。"""
    r = retention_now(fact.get("last_confirmed", 0.0), fact.get("predicate", ""), now)
    c = confidence_score(int(fact.get("source_count", 1)), r,
                         bool(fact.get("contradicts")), bool(fact.get("stale")))
    return round(r, 3), c
