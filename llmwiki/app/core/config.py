"""全局配置。所有可调参数集中于此,通过环境变量覆盖。"""
from __future__ import annotations

import os
from functools import lru_cache
from pydantic import BaseModel


class Settings(BaseModel):
    # --- 基础设施 ---
    pg_dsn: str = os.getenv("PG_DSN", "postgresql://llmwiki:llmwiki@localhost:5432/llmwiki")
    redis_url: str = os.getenv("REDIS_URL", "redis://localhost:6379/0")
    s3_endpoint: str = os.getenv("S3_ENDPOINT", "http://localhost:9000")
    s3_bucket: str = os.getenv("S3_BUCKET", "llmwiki")

    # --- Anthropic ---
    anthropic_api_key: str = os.getenv("ANTHROPIC_API_KEY", "")
    anthropic_base_url: str = os.getenv("ANTHROPIC_BASE_URL", "")  # 可选:第三方兼容 API 地址
    model_haiku: str = os.getenv("MODEL_HAIKU", "claude-haiku-4-5-20251001")
    model_sonnet: str = os.getenv("MODEL_SONNET", "claude-sonnet-4-6")

    # --- 编译参数 ---
    chunk_target_tokens: int = 1200          # parent chunk 目标大小
    chunk_max_tokens: int = 2000
    span_target_tokens: int = 200            # 证据 span 目标大小(citation 落点)
    parse_shard_pages: int = 40              # MinerU 分片页数
    parse_shard_overlap: int = 1             # 分片重叠页(跨页表格/段落)

    # --- 检索参数 ---
    retrieve_candidate_k: int = 50           # 召回候选数(进 rerank 前)
    retrieve_final_k: int = 8                # rerank 后最终条数
    rrf_k: int = 60                          # RRF 平滑常数
    embed_dim: int = 1024                    # 向量维度(按所选 embedding 模型)

    # --- 取证循环 ---
    agent_max_tool_turns: int = 8            # agentic 取证最大轮数
    verify_nli_threshold: float = 0.5        # verify 通过阈值

    # --- 编译深度 ---
    default_compile_depth: str = "D1"        # D0 fast / D1 standard / D2 graph

    # --- prompt 版本(bump 触发选择性重编) ---
    prompt_version_extract: str = "v1"
    prompt_version_relation: str = "v1"
    prompt_version_wiki: str = "v1"


@lru_cache
def get_settings() -> Settings:
    return Settings()
