"""Embedding 与 reranker 封装(可插拔)。

默认支持:
1. OpenAI 兼容 API(如 DeepSeek/GLM/Qwen) → 通过 EMBED_API_KEY/BASE_URL 配置
2. local sentence-transformers → 需要本地下载模型(不配置 EMBED_API_KEY 时)
支持 EMBED_MOCK=1 环境变量,返回零向量(用于测试/CI)。
"""
from __future__ import annotations

import os
import math
from functools import lru_cache
from typing import Optional

import httpx

from app.core.config import get_settings

_S = get_settings()

_MOCK_EMBED = os.environ.get("EMBED_MOCK", "0") == "1"
_EMBED_API_KEY = os.environ.get("EMBED_API_KEY", "") or os.environ.get("EMBEDDING_API_KEY", "")
_EMBED_BASE_URL = os.environ.get("EMBED_BASE_URL", "") or os.environ.get("EMBEDDING_BASE_URL", "")
# 默认模型:BAAI/bge-m3(1024 维),与 schema.sql 的 vector(1024) 对齐。
# 注意:DeepSeek 当前没有 embedding 接口;阿里百炼/硅基流动/Jina/Cohere 均提供 1024 维兼容选项。
_EMBED_MODEL = os.environ.get("EMBED_MODEL", "BAAI/bge-m3")

# 默认 fallback: 复用 LLM provider 的 API key/base_url(仅当未单独配置 embedding 时)
if not _EMBED_API_KEY:
    _EMBED_API_KEY = _S.openai_api_key or _S.anthropic_api_key
if not _EMBED_BASE_URL:
    _EMBED_BASE_URL = _S.openai_base_url or _S.anthropic_base_url

# 缓存 embedding HTTP 客户端
_embed_client: Optional[httpx.AsyncClient] = None


def _get_embed_client() -> httpx.AsyncClient:
    global _embed_client
    if _embed_client is None:
        _embed_client = httpx.AsyncClient(
            base_url=_EMBED_BASE_URL.rstrip("/"),
            timeout=10.0,  # 短超时:embedding 不可用时快速降级
        )
    return _embed_client


async def _embed_openai(texts: list[str]) -> list[list[float]]:
    """通过 OpenAI 兼容 API 获取 embedding。

    支持:
      - OpenAI 官方:base_url=https://api.openai.com/v1
      - 硅基流动:base_url=https://api.siliconflow.cn/v1
      - 阿里百炼:base_url=https://dashscope.aliyuncs.com/compatible-mode/v1
      - 自部署 vLLM/Ollama:任意 OpenAI 兼容前缀
    URL 拼接规则(避免 //v1/v1):
      - base 以 /v1 结尾 → 直接拼 /embeddings
      - base 中已含 /v1/ → 直接拼 /embeddings
      - 其余 → 拼 /v1/embeddings
    """
    dim = _S.embed_dim or 1024
    client = _get_embed_client()

    base = _EMBED_BASE_URL.rstrip("/")
    if not base:
        # 未配置 base_url,降级到零向量(避免抛错)
        return [[0.0] * dim for _ in texts]
    if base.endswith("/v1") or "/v1/" in base:
        url = f"{base}/embeddings" if base.endswith("/v1") else f"{base.rstrip('/')}/embeddings"
    else:
        url = f"{base}/v1/embeddings"

    try:
        resp = await client.post(
            url,
            json={"model": _EMBED_MODEL, "input": texts},
            headers={"Authorization": f"Bearer {_EMBED_API_KEY}"},
        )
        resp.raise_for_status()
        data = resp.json()
        by_index = {d["index"]: d["embedding"] for d in data.get("data", [])}
        # 维度校验:首次返回的向量维度若与 embed_dim 不一致,记录警告(易踩坑)
        vecs = [by_index.get(i, [0.0] * dim) for i in range(len(texts))]
        if vecs and len(vecs[0]) != dim:
            print(f"[embed] WARNING: model {_EMBED_MODEL} returns dim={len(vecs[0])} "
                  f"but schema expects {dim}; vector search will be incorrect. "
                  f"请换 1024 维模型(如 BAAI/bge-m3)或同步修改 schema.sql + embed_dim。",
                  flush=True)
        return vecs
    except Exception as e:
        print(f"[embed] API call failed, fallback to zero vectors: {e}", flush=True)
        return [[0.0] * dim for _ in texts]


@lru_cache
def _embedder():
    if _MOCK_EMBED:
        return None
    # 如果配置了 API key,走 API 模式(不需要本地模型)
    if _EMBED_API_KEY:
        return "api"
    # 否则尝试加载本地模型
    try:
        from sentence_transformers import SentenceTransformer
        return SentenceTransformer("BAAI/bge-m3")
    except Exception:
        return None


@lru_cache
def _reranker():
    if _MOCK_EMBED:
        return None
    if _EMBED_API_KEY:
        return "api"  # 可选的 reranker API,暂不实现
    try:
        from sentence_transformers import CrossEncoder
        return CrossEncoder("BAAI/bge-reranker-v2-m3")
    except Exception:
        return None


async def embed(texts: list[str]) -> list[list[float]]:
    """异步 embedding。支持 API 模式和本地模型。"""
    if not texts:
        return []
    dim = _S.embed_dim or 1024
    if _MOCK_EMBED:
        return [[0.0] * dim for _ in texts]
    
    embedder = _embedder()
    if embedder == "api":
        return await _embed_openai(texts)
    if embedder is None:
        return [[0.0] * dim for _ in texts]
    # 本地模型(同步,但很快)
    vecs = embedder.encode(texts, normalize_embeddings=True)
    return [v.tolist() for v in vecs]


def embed_sync(texts: list[str]) -> list[list[float]]:
    """同步 embedding(用于 sync 上下文中,如 l1_chunk_span)。"""
    if not texts:
        return []
    dim = _S.embed_dim or 1024
    if _MOCK_EMBED:
        return [[0.0] * dim for _ in texts]
    embedder = _embedder()
    if embedder == "api" or embedder is None:
        # sync 模式下 API 不可用,返回零向量
        return [[0.0] * dim for _ in texts]
    vecs = embedder.encode(texts, normalize_embeddings=True)
    return [v.tolist() for v in vecs]


def rerank(query: str, candidates: list[tuple[str, str]]) -> list[tuple[str, float]]:
    """candidates: [(span_id, content)] → [(span_id, score)] 按分降序。
    注意:rerank 目前仅支持本地模型;API 模式下返回等分。"""
    if not candidates:
        return []
    if _MOCK_EMBED:
        n = len(candidates)
        score = 1.0 / n if n > 0 else 0.0
        return [(sid, score) for sid, _ in candidates]
    r = _reranker()
    if r is None or r == "api":
        # API 模式暂不支持 rerank,按原始顺序等分返回
        n = len(candidates)
        score = 1.0 / n if n > 0 else 0.0
        return [(sid, score) for sid, _ in candidates]
    pairs = [(query, c) for _, c in candidates]
    scores = r.predict(pairs)
    ranked = sorted(
        ((sid, float(s)) for (sid, _), s in zip(candidates, scores)),
        key=lambda x: x[1], reverse=True,
    )
    return ranked
