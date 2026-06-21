"""Embedding 与 reranker 封装(可插拔)。

默认用 sentence-transformers 的多语言模型;生产可换成自部署 bge-m3 / 商用 API。
支持 EMBED_MOCK=1 环境变量,跳过模型下载,返回零向量(用于测试/CI/前端联调)。
"""
from __future__ import annotations

import os
import math
from functools import lru_cache
from typing import Optional

from app.core.config import get_settings

_S = get_settings()

# 如果设置了 HF_ENDPOINT 环境变量,在导入 sentence-transformers 前设置
_hf_endpoint = os.environ.get("HF_ENDPOINT") or os.environ.get("HF_MIRROR")
if _hf_endpoint:
    os.environ.setdefault("HF_ENDPOINT", _hf_endpoint)

_MOCK_EMBED = os.environ.get("EMBED_MOCK", "0") == "1"


@lru_cache
def _embedder():
    if _MOCK_EMBED:
        return None
    from sentence_transformers import SentenceTransformer
    return SentenceTransformer("BAAI/bge-m3")


@lru_cache
def _reranker():
    if _MOCK_EMBED:
        return None
    from sentence_transformers import CrossEncoder
    return CrossEncoder("BAAI/bge-reranker-v2-m3")


def embed(texts: list[str]) -> list[list[float]]:
    if not texts:
        return []
    dim = _S.embed_dim or 1024
    if _MOCK_EMBED or _embedder() is None:
        # mock: 返回 dim 维零向量(测试/联调用,检索效果差但流程可跑通)
        return [[0.0] * dim for _ in texts]
    vecs = _embedder().encode(texts, normalize_embeddings=True)
    return [v.tolist() for v in vecs]


def rerank(query: str, candidates: list[tuple[str, str]]) -> list[tuple[str, float]]:
    """candidates: [(span_id, content)] → [(span_id, score)] 按分降序。"""
    if not candidates:
        return []
    if _MOCK_EMBED or _reranker() is None:
        # mock: 返回等分(1.0 / n),排序不变
        n = len(candidates)
        score = 1.0 / n if n > 0 else 0.0
        return [(sid, score) for sid, _ in candidates]
    pairs = [(query, c) for _, c in candidates]
    scores = _reranker().predict(pairs)
    ranked = sorted(
        ((sid, float(s)) for (sid, _), s in zip(candidates, scores)),
        key=lambda x: x[1], reverse=True,
    )
    return ranked
