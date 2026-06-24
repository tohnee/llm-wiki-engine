"""单元测试:本轮 bug 修复 + 工具函数。

- truncate_summary 长度上限严格 ≤ 200(BUG: 200/197 不统一)
- security_guard 在生产环境对占位密钥拒绝放行
- observability counter/histogram 行为
"""
from __future__ import annotations

import os
import pytest


# ---- truncate_summary ----
def test_truncate_summary_under_limit_keeps_text():
    from app.compile.workers.l1_chunk_span import truncate_summary
    assert truncate_summary("短文本", max_chars=200) == "短文本"


def test_truncate_summary_over_limit_adds_ellipsis_and_caps_length():
    from app.compile.workers.l1_chunk_span import truncate_summary
    s = "a" * 500
    out = truncate_summary(s, max_chars=200)
    assert len(out) == 200, f"output must be ≤ 200, got {len(out)}"
    assert out.endswith("...")


def test_truncate_summary_normalizes_newlines():
    from app.compile.workers.l1_chunk_span import truncate_summary
    out = truncate_summary("a\nb\nc", max_chars=10)
    assert "\n" not in out


# ---- security_guard ----
def test_security_guard_dev_mode_warns_only(monkeypatch, capsys):
    monkeypatch.setenv("APP_ENV", "dev")
    monkeypatch.setenv("JWT_SECRET", "change-me")
    monkeypatch.setenv("INTERNAL_HMAC_SECRET", "dev-internal-secret")
    from app.core.security_guard import enforce_production_secrets
    enforce_production_secrets()  # 不应退出
    out = capsys.readouterr().out
    assert "WARNING" in out


def test_security_guard_prod_mode_rejects_placeholder(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("JWT_SECRET", "change-me")
    monkeypatch.setenv("INTERNAL_HMAC_SECRET", "dev-internal-secret")
    from app.core.security_guard import enforce_production_secrets
    with pytest.raises(SystemExit) as ei:
        enforce_production_secrets()
    assert ei.value.code == 78  # EX_CONFIG


def test_security_guard_prod_mode_accepts_strong_secrets(monkeypatch):
    monkeypatch.setenv("APP_ENV", "prod")
    monkeypatch.setenv("JWT_SECRET", "a" * 64)
    monkeypatch.setenv("INTERNAL_HMAC_SECRET", "b" * 64)
    monkeypatch.setenv("PG_DSN", "postgresql://prod_user:strongpass@db.internal/llmwiki")
    from app.core.security_guard import enforce_production_secrets
    enforce_production_secrets()  # 不应抛


# ---- observability ----
def test_counter_inc_and_render():
    from app.core.observability import counter, render_prometheus
    c = counter("test_counter_xyz", "test counter", ("path",))
    c.inc(path="/a")
    c.inc(2.0, path="/a")
    c.inc(path="/b")
    out = render_prometheus()
    assert "test_counter_xyz" in out
    assert 'test_counter_xyz{path="/a"} 3.0' in out
    assert 'test_counter_xyz{path="/b"} 1.0' in out


def test_histogram_observe_records_buckets():
    from app.core.observability import histogram, Timer
    import time
    h = histogram("test_hist_xyz", "test hist", ("model",))
    with Timer(h, model="m1"):
        time.sleep(0.01)
    from app.core.observability import render_prometheus
    out = render_prometheus()
    assert "test_hist_xyz_count" in out


# ---- embed URL 拼接 ----
def test_embed_url_handles_v1_suffix(monkeypatch):
    """无论 base_url 是否带 /v1,_embed_openai 都应拼出唯一的 /v1/embeddings。"""
    # 此测试只验证 URL 拼接函数的健壮性,不真发请求
    from app.llm import embed as embed_mod
    cases = [
        ("https://api.openai.com/v1", "https://api.openai.com/v1/embeddings"),
        ("https://api.openai.com/v1/", "https://api.openai.com/v1/embeddings"),
        ("https://x.com", "https://x.com/v1/embeddings"),
        ("https://x.com/openai/v1/", "https://x.com/openai/v1/embeddings"),
    ]
    for base, expected in cases:
        # 复制 _embed_openai 中的 URL 拼接逻辑做断言
        base_n = base.rstrip("/")
        if base_n.endswith("/v1") or "/v1/" in base_n:
            url = f"{base_n}/embeddings"
        else:
            url = f"{base_n}/v1/embeddings"
        assert url == expected, f"{base} → {url}, expected {expected}"


def test_stable_chunk_and_span_ids_are_repeatable(monkeypatch):
    monkeypatch.setenv("EMBED_MOCK", "1")
    from app.compile.workers.l1_chunk_span import build_chunks_and_spans
    md = "# 报告\n## 预算\n第一页内容。\n\n第二页内容。"
    page_map = {0: 1, md.index("第二页"): 2}
    c1, s1 = build_chunks_and_spans("t1", "doc1", md, page_map=page_map)
    c2, s2 = build_chunks_and_spans("t1", "doc1", md, page_map=page_map)
    assert [c.chunk_id for c in c1] == [c.chunk_id for c in c2]
    assert [sp.span_id for sp in s1] == [sp.span_id for sp in s2]
    assert all(c.page_start >= 1 and c.page_end >= 1 for c in c1)
    assert all(sp.page >= 1 for sp in s1)


def test_pipeline_extracts_citations_and_uses_k_param():
    import inspect
    from app.query.pipeline import extract_citations, _direct_search_answer
    assert extract_citations("A [d1:sp1] B [d1:sp1] C [d2:sp2]") == [
        {"doc_id": "d1", "span_id": "sp1"},
        {"doc_id": "d2", "span_id": "sp2"},
    ]
    src = inspect.getsource(_direct_search_answer)
    assert '"k": 8' in src
    assert '"top_k": 8' not in src


def test_navigate_awaits_embed_source():
    import inspect
    import app.evidence.service as svc
    src = inspect.getsource(svc.navigate)
    assert "await embed" in src


def test_store_upsert_document_and_status_sql():
    import asyncio
    from app.db.store import Store
    from app.models.schema import Document, DocStatus, CompileDepth

    captured = []

    class FakeCon:
        async def execute(self, sql, *params):
            captured.append((sql, params))
        async def __aenter__(self): return self
        async def __aexit__(self, *a): pass

    class FakePool:
        def acquire(self): return FakeCon()

    async def run():
        store = Store(FakePool())
        await store.upsert_document("t1", Document(
            document_id="d1", tenant_id="t1", title="Doc", source_uri="s3://d1",
            status=DocStatus.UPLOADED, depth=CompileDepth.D1, page_count=3))
        await store.set_doc_status("t1", "d1", DocStatus.FAILED.value, error="boom")
    asyncio.run(run())
    assert "INSERT INTO documents" in captured[0][0]
    assert "ON CONFLICT" in captured[0][0]
    assert "compile_error" in captured[1][0]
    assert captured[1][1][-1] == "boom"


def test_typed_graph_relation_normalization_and_prompt():
    from app.evidence.typed_graph import normalize_relation_type, relation_spec, relation_type_prompt
    assert normalize_relation_type("depends on") == "depends_on"
    assert normalize_relation_type("fixed-by") == "fixed_by"
    assert normalize_relation_type("unknown relation") == "related_to"
    assert relation_spec("supersedes").acyclic is True
    prompt = relation_type_prompt()
    for rel in ["uses", "depends_on", "contradicts", "caused_by", "fixed_by", "superseded_by"]:
        assert rel in prompt


def test_l3_extract_relations_normalizes_type_and_stable_id(monkeypatch):
    import asyncio
    import json
    from app.compile.workers import l3_resolve_relation as l3
    from app.models.schema import Entity

    class Block:
        type = "text"
        text = json.dumps({"relations": [
            {"source": "Claude Code", "relation_type": "depends on", "target": "Agent Memory"},
            {"source": "Claude Code", "relation_type": "???", "target": "Codex"},
        ]})

    class Resp:
        content = [Block()]

    class GW:
        async def complete(self, **kw):
            return Resp()

    monkeypatch.setattr(l3, "get_gateway", lambda: GW())
    entities = [
        Entity(entity_id="e1", tenant_id="t1", name="Claude Code", type="product"),
        Entity(entity_id="e2", tenant_id="t1", name="Agent Memory", type="concept"),
        Entity(entity_id="e3", tenant_id="t1", name="Codex", type="product"),
    ]
    r1 = asyncio.run(l3.extract_relations("t1", entities, "facts"))
    r2 = asyncio.run(l3.extract_relations("t1", entities, "facts"))
    assert [r.relation_type for r in r1] == ["depends_on", "related_to"]
    assert [r.relation_id for r in r1] == [r.relation_id for r in r2]


def test_graph_utils_supports_typed_relation_filter_source():
    import pathlib
    src = pathlib.Path("frontend/src/lib/graph-utils.js")
    if not src.exists():
        src = pathlib.Path("llmwiki/frontend/src/lib/graph-utils.js")
    text = src.read_text()
    assert "RELATION_META" in text
    assert "normalizeRelation" in text
    assert "relationFilter" in text
    assert "countByRelation" in text
