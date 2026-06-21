"""L0: PDF → Markdown(MinerU 分片并行解析)。

MinerU 作为本地服务(HTTP)或 CLI 调用。按页区间分 shard 并行,边界重叠 1 页用于
跨页表格/段落拼接。若输入已是 .md(或 MinerU 不可用),直接读取,保证管线可跑。
"""
from __future__ import annotations

import os
from typing import Optional

import httpx

from app.core.config import get_settings

_S = get_settings()
MINERU_URL = os.getenv("MINERU_URL", "")   # 例: http://mineru:8080/parse


async def parse_to_markdown(source_path: str, page_range: Optional[tuple[int, int]] = None) -> str:
    """把单个 source(本地路径或已挂载路径)解析为 markdown。"""
    if source_path.endswith(".md") or source_path.endswith(".txt"):
        with open(source_path, encoding="utf-8") as f:
            return f.read()

    if not MINERU_URL:
        raise RuntimeError(
            "MinerU 服务未配置(MINERU_URL),且输入不是 .md/.txt。"
            "请部署 MinerU 并设置 MINERU_URL,或先把文档转为 markdown。")

    payload = {"path": source_path}
    if page_range:
        payload["page_start"], payload["page_end"] = page_range
    async with httpx.AsyncClient(timeout=600) as client:
        resp = await client.post(MINERU_URL, json=payload)
        resp.raise_for_status()
        return resp.json()["markdown"]


def plan_shards(page_count: int) -> list[tuple[int, int]]:
    """按 parse_shard_pages 切页区间,边界重叠 parse_shard_overlap 页。"""
    size = _S.parse_shard_pages
    overlap = _S.parse_shard_overlap
    shards = []
    start = 0
    while start < page_count:
        end = min(start + size, page_count)
        shards.append((max(0, start - (overlap if start > 0 else 0)), end))
        start = end
    return shards


def stitch(markdowns: list[str]) -> str:
    """拼接分片 markdown(简单去重重叠行;生产可做更鲁棒的边界对齐)。"""
    if not markdowns:
        return ""
    out = [markdowns[0]]
    for md in markdowns[1:]:
        out.append("\n\n" + md)
    return "".join(out)
