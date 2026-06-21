"""评测 harness:分层指标。

golden QA(JSONL): {id, bucket, question, answer, golden_span_ids:[...]}
分桶:detail / table / multi_doc / long_doc / summary
分层指标:
  - retrieval recall@k:golden span 是否进入检索召回(定位损失在检索层)
  - answer faithfulness:回答的 claim 是否被引用 span 支持(定位损失在生成层)
接 CI:每次 prompt/索引/schema 变更必跑,出按桶 diff。
"""
from __future__ import annotations

import json
import re
import sys
from collections import defaultdict

from app.core.tenant import TenantContext
from app.evidence.retrieval import Retriever
from app.db.store import Store
from app.query.pipeline import answer

_CITE = re.compile(r"\[([\w\-]+):([\w\-]+)\]")


async def eval_retrieval(store: Store, tenant_id: str, dataset: list[dict], k: int = 8) -> dict:
    retr = Retriever(store)
    by_bucket = defaultdict(lambda: {"hit": 0, "total": 0, "mrr": 0.0})
    for ex in dataset:
        spans = await retr.search(tenant_id, ex["question"], final_k=k)
        got = [s.span_id for s in spans]
        gold = set(ex["golden_span_ids"])
        b = by_bucket[ex["bucket"]]
        b["total"] += 1
        hit_rank = next((i for i, sid in enumerate(got) if sid in gold), None)
        if hit_rank is not None:
            b["hit"] += 1
            b["mrr"] += 1.0 / (hit_rank + 1)
    return {
        bucket: {
            "recall@k": v["hit"] / v["total"] if v["total"] else 0,
            "mrr": v["mrr"] / v["total"] if v["total"] else 0,
            "n": v["total"],
        } for bucket, v in by_bucket.items()
    }


async def eval_answers(ctx: TenantContext, dataset: list[dict]) -> dict:
    by_bucket = defaultdict(lambda: {"faith": 0.0, "n": 0})
    for ex in dataset:
        res = await answer(ctx, ex["question"])
        v = res.get("verify", {})
        b = by_bucket[ex["bucket"]]
        b["faith"] += v.get("verified_ratio", 0.0)
        b["n"] += 1
    return {
        bucket: {"faithfulness": v["faith"] / v["n"] if v["n"] else 0, "n": v["n"]}
        for bucket, v in by_bucket.items()
    }


async def main(path: str, tenant_id: str):
    dataset = [json.loads(l) for l in open(path) if l.strip()]
    store = await Store.connect()
    ctx = TenantContext(tenant_id=tenant_id, user_id="eval", session_id="eval")
    print("=== retrieval ===")
    print(json.dumps(await eval_retrieval(store, tenant_id, dataset), indent=2, ensure_ascii=False))
    print("=== answers ===")
    print(json.dumps(await eval_answers(ctx, dataset), indent=2, ensure_ascii=False))


if __name__ == "__main__":
    import asyncio
    asyncio.run(main(sys.argv[1], sys.argv[2]))
