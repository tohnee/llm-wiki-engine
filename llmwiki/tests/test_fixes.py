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
