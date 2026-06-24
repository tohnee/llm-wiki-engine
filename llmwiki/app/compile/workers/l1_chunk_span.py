"""L1: Markdown → Chunk(parent) + Span(child) + embedding。

切分原则:优先按 MinerU 输出的标题层级(章 > 节 > 段),而非固定 token。
chunk ~1200 token(上下文单元),span ~200 token(citation 落点)。
增量:chunk content_hash 未变化则跳过,并跳过其 DAG 下游。
"""
from __future__ import annotations

import re
import hashlib

from app.core.config import get_settings
from app.models.schema import Chunk, Span, SpanType, content_hash
from app.llm.embed import embed_sync


def truncate_summary(text: str, max_chars: int = 200, ellipsis: str = "...") -> str:
    """统一摘要截断:超过 max_chars 截断并加省略号(省略号计入上限)。
    schema.summary_max_chars 控制硬上限,默认 200;summarize.py 与 l1_chunk_span.py 都用本函数。"""
    s = (text or "").strip().replace("\n", " ")
    if len(s) <= max_chars:
        return s
    keep = max(1, max_chars - len(ellipsis))
    return s[:keep] + ellipsis

_S = get_settings()

# 粗略 token 估计(中英混合):字符数 / 2.5;生产换 tiktoken-like 计数
def _est_tokens(text: str) -> int:
    return int(len(text) / 2.5)


def _split_by_headings(md: str) -> list[tuple[str, str]]:
    """返回 [(section_path, body)]。按 markdown 标题切。"""
    lines = md.splitlines()
    sections: list[tuple[str, str]] = []
    stack: list[str] = []
    buf: list[str] = []

    def flush():
        if buf:
            sections.append((" > ".join(stack), "\n".join(buf).strip()))

    for ln in lines:
        m = re.match(r"^(#{1,6})\s+(.*)", ln)
        if m:
            flush()
            buf.clear()
            level = len(m.group(1))
            title = m.group(2).strip()
            stack = stack[: level - 1] + [title]
        else:
            buf.append(ln)
    flush()
    return [(p, b) for p, b in sections if b]


def _pack_chunks(section_path: str, body: str, target: int, hard_max: int) -> list[str]:
    """把一节切成多个 chunk,尽量按段落边界,控制在 target 附近。"""
    paras = [p for p in re.split(r"\n\s*\n", body) if p.strip()]
    chunks, cur, cur_tok = [], [], 0
    for p in paras:
        t = _est_tokens(p)
        if cur and cur_tok + t > target:
            chunks.append("\n\n".join(cur))
            cur, cur_tok = [], 0
        cur.append(p)
        cur_tok += t
        if cur_tok >= hard_max:
            chunks.append("\n\n".join(cur)); cur, cur_tok = [], 0
    if cur:
        chunks.append("\n\n".join(cur))
    return chunks


def _split_spans(chunk_text: str, target: int) -> list[tuple[str, SpanType]]:
    """chunk → spans。表格行单独成 span;其余按句/小段。"""
    spans: list[tuple[str, SpanType]] = []
    for block in re.split(r"\n\s*\n", chunk_text):
        block = block.strip()
        if not block:
            continue
        if "|" in block and block.count("\n") >= 1 and re.search(r"\|.*\|", block):
            # markdown 表格:表头 + 每行单独成 span
            rows = [r for r in block.splitlines() if r.strip()]
            header = rows[0] if rows else ""
            for r in rows[1:]:
                if set(r.replace("|", "").strip()) <= {"-", " ", ":"}:
                    continue  # 分隔行
                spans.append((f"{header}\n{r}", SpanType.TABLE_ROW))
        else:
            # 按句聚合到 ~target token
            sents = re.split(r"(?<=[。.!?！？])\s*", block)
            cur, cur_tok = [], 0
            for s in sents:
                if not s.strip():
                    continue
                if cur and cur_tok + _est_tokens(s) > target:
                    spans.append(("".join(cur), SpanType.TEXT)); cur, cur_tok = [], 0
                cur.append(s); cur_tok += _est_tokens(s)
            if cur:
                spans.append(("".join(cur), SpanType.TEXT))
    return spans


def _stable_id(prefix: str, *parts: object) -> str:
    h = hashlib.sha256()
    for p in parts:
        h.update(str(p).encode("utf-8")); h.update(b"\x00")
    return f"{prefix}_{h.hexdigest()[:16]}"


def _page_for_offset(page_map, offset: int) -> int:
    """把字符偏移映射到页码。支持 {offset: page} 或 [(offset,page)]。"""
    if not page_map:
        return 1
    items = page_map.items() if isinstance(page_map, dict) else page_map
    page = 1
    for start, p in sorted((int(k), int(v)) for k, v in items):
        if start <= offset:
            page = p
        else:
            break
    return max(1, page)


def build_chunks_and_spans(
    tenant_id: str, document_id: str, md: str, page_map: dict[int, int] | list[tuple[int, int]] | None = None
) -> tuple[list[Chunk], list[Span]]:
    """Markdown → 稳定 chunk/span。

    chunk_id 基于 document_id + section_path + chunk 序号,内容不变或小改时可被
    manifest 稳定命中;content_hash 单独表达内容变化。page_map 为 MinerU 字符偏移→页码。
    """
    chunks: list[Chunk] = []
    spans: list[Span] = []
    span_texts: list[str] = []
    span_objs: list[Span] = []
    search_from = 0
    section_ord: dict[str, int] = {}

    for section_path, body in _split_by_headings(md):
        sec_idx = section_ord.get(section_path, 0)
        section_ord[section_path] = sec_idx + 1
        chunk_ord = 0
        for ctext in _pack_chunks(section_path, body, _S.chunk_target_tokens, _S.chunk_max_tokens):
            start = md.find(ctext, search_from)
            if start < 0:
                start = md.find(ctext)
            if start < 0:
                start = search_from
            end = start + len(ctext)
            search_from = max(search_from, end)
            page_start = _page_for_offset(page_map, start)
            page_end = _page_for_offset(page_map, end)
            chunk_id = _stable_id("ch", document_id, section_path, sec_idx, chunk_ord)
            chash = content_hash(ctext, _S.prompt_version_extract)
            chunk = Chunk(
                chunk_id=chunk_id, tenant_id=tenant_id, document_id=document_id,
                content=ctext, page_start=page_start, page_end=page_end,
                section_path=section_path, content_hash=chash,
                summary=truncate_summary(ctext, max_chars=200),
            )
            sp_ids = []
            span_ord = 0
            local_from = 0
            for stext, stype in _split_spans(ctext, _S.span_target_tokens):
                rel = ctext.find(stext, local_from)
                if rel < 0:
                    rel = ctext.find(stext)
                if rel < 0:
                    rel = 0
                local_from = max(local_from, rel + len(stext))
                page = _page_for_offset(page_map, start + rel)
                span_id = _stable_id("sp", chunk_id, span_ord, content_hash(stext))
                sp = Span(
                    span_id=span_id, chunk_id=chunk_id, document_id=document_id,
                    tenant_id=tenant_id, content=stext, page=page, span_type=stype,
                )
                span_objs.append(sp); span_texts.append(stext); sp_ids.append(span_id)
                span_ord += 1
            chunk.span_ids = sp_ids
            chunks.append(chunk)
            chunk_ord += 1

    vecs = embed_sync(span_texts)
    for sp, v in zip(span_objs, vecs):
        sp.embedding = v
    spans = span_objs
    return chunks, spans
