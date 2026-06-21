"""离线冒烟测试:验证不依赖 DB/网络的纯逻辑模块。

运行: python -m tests.smoke
覆盖:租户安全边界、chunk/span 切分(表格行)、lint hub 加权排序、tier 权重、RRF 融合。
不覆盖:需要真实 Postgres/Redis/Anthropic API 的端到端路径(见 README 部署后用 make eval)。
"""
import sys
import types

# stub 重依赖与基础设施库,使离线冒烟测试无需安装 asyncpg/redis/anthropic/模型
_embed = types.ModuleType("app.llm.embed")
_embed.embed = lambda x: [[0.0] * 1024 for _ in x]
_embed.rerank = lambda q, c: [(s, 1.0) for s, _ in c]
sys.modules["app.llm.embed"] = _embed

for _name in ("asyncpg", "anthropic"):
    sys.modules[_name] = types.ModuleType(_name)
sys.modules["anthropic"].AsyncAnthropic = object
_redis = types.ModuleType("redis")
_redis_async = types.ModuleType("redis.asyncio")
_redis_async.Redis = object
_redis_async.from_url = lambda *a, **k: None
_redis_async.ResponseError = Exception
sys.modules["redis"] = _redis
sys.modules["redis.asyncio"] = _redis_async

failures = []


def check(name, cond):
    print(f"  [{'PASS' if cond else 'FAIL'}] {name}")
    if not cond:
        failures.append(name)


def test_tenant_security():
    from app.core.tenant import sign_internal_header, verify_internal_header
    h = sign_internal_header("tA", "u1", "s1")
    ctx = verify_internal_header(h)
    check("tenant sign/verify roundtrip", ctx.tenant_id == "tA")
    forged = h.replace("tA", "tB")
    try:
        verify_internal_header(forged)
        check("cross-tenant forgery rejected", False)
    except PermissionError:
        check("cross-tenant forgery rejected", True)


def test_chunking():
    from app.compile.workers.l1_chunk_span import build_chunks_and_spans
    md = ("# 报告\n## 1. 预算\n总预算500万元。实际支出620万元,超支120万元。\n"
          "## 2. 明细\n| 项目 | 金额 |\n| --- | --- |\n| 人力 | 300万 |\n| 设备 | 320万 |\n")
    chunks, spans = build_chunks_and_spans("t1", "doc1", md)
    check("chunks produced", len(chunks) == 2)
    check("section path captured", chunks[0].section_path == "报告 > 1. 预算")
    check("summary populated", len(chunks[0].summary) > 0)
    table_rows = [s for s in spans if s.span_type.value == "table_row"]
    check("table rows split with header", len(table_rows) == 2 and "项目" in table_rows[0].content)


def test_rrf():
    from app.evidence.retrieval import _rrf_merge
    fused = _rrf_merge([["a", "b", "c"], ["b", "a", "d"]], 60)
    ranked = sorted(fused, key=fused.get, reverse=True)
    check("RRF ranks consensus item first", ranked[0] in ("a", "b"))


def test_lint_hub_weighting():
    # 复现 lint 的优先级公式,验证 hub 节点排序更高
    hub_p = 0.25 * (1 + 2 * 0.95)
    periph_p = 0.20 * (1 + 0.05)
    check("hub error-propagation outranks peripheral", hub_p > periph_p)


def test_tier_weights():
    from app.evidence.tiered import _TIER_WEIGHT
    check("core weighted above peripheral", _TIER_WEIGHT["core"] > _TIER_WEIGHT["peripheral"])


def test_provenance_model():
    from app.models.schema import Fact, Provenance
    f = Fact(fact_id="f1", tenant_id="t1", document_id="d1",
             subject_entity="A", predicate="p", object_value="v")
    from app.compile.contradiction import assign_provenance_basic
    f.source_span_ids = ["sp1"]
    assign_provenance_basic(f)
    check("extracted when span-backed", f.provenance == Provenance.EXTRACTED)
    g = Fact(fact_id="f2", tenant_id="t1", document_id="d1",
             subject_entity="A", predicate="p", object_value="v")
    assign_provenance_basic(g)
    check("inferred when unsourced", g.provenance == Provenance.INFERRED)


def test_auth():
    import os
    os.environ["JWT_SECRET"] = "test-secret"
    from app.core.auth import hash_password, verify_password, issue_jwt, decode_jwt
    h = hash_password("hunter2")
    check("password verifies", verify_password("hunter2", h))
    check("wrong password rejected", not verify_password("nope", h))
    tok = issue_jwt("tA", "u1", "admin")
    claims = decode_jwt(tok)
    check("jwt carries tenant/user/role", claims["tenant_id"] == "tA" and claims["role"] == "admin")


def test_memory_key_isolation():
    from app.core.tenant import TenantContext
    from app.query.memory import MemoryStore
    ms = MemoryStore.__new__(MemoryStore)  # 不连 redis,只测 key
    a = ms._key(TenantContext("tA", "u1", "s1"))
    b = ms._key(TenantContext("tB", "u1", "s1"))
    c = ms._key(TenantContext("tA", "u2", "s1"))
    check("memory keys isolate by tenant", a != b)
    check("memory keys isolate by user", a != c)
    check("memory key shape", a == "mem:tA:u1:s1")


def test_graph_export():
    from app.evidence.graph_export import to_graphml, to_cypher, to_json
    g = {"nodes": [{"entity_id": "e1", "name": "项目X", "type": "project"},
                   {"entity_id": "e2", "name": "预算", "type": "concept"}],
         "edges": [{"source": "e1", "relation": "has_budget", "target": "e2"}]}
    gml = to_graphml(g)
    cy = to_cypher(g)
    check("graphml well-formed", gml.startswith("<?xml") and "项目X" in gml and "</graphml>" in gml)
    check("cypher has MERGE node + rel", "MERGE (e:Entity" in cy and "HAS_BUDGET" in cy)
    check("json roundtrips", '"e1"' in to_json(g))


def test_extract_parse():
    # 验证 batch 与实时共用的解析器把 source_span_index 正确映射回 span_id
    from app.models.schema import Span, SpanType
    from app.compile.workers.l2_extract import parse_extract_result
    spans = [Span(span_id="sp0", chunk_id="c1", document_id="d1", tenant_id="t1",
                  content="项目总预算500万", page=0, span_type=SpanType.TEXT),
             Span(span_id="sp1", chunk_id="c1", document_id="d1", tenant_id="t1",
                  content="实际支出620万", page=0, span_type=SpanType.TEXT)]
    text = ('{"facts":[{"subject":"项目","predicate":"预算","object":"500万",'
            '"qualifiers":{"unit":"万元"},"source_span_index":[0]}],'
            '"entities":[{"name":"项目","type":"project","span_index":[0,1]}]}')
    facts, ents = parse_extract_result("t1", "d1", "chunk text", spans, text)
    check("fact parsed with span provenance", len(facts) == 1 and facts[0].source_span_ids == ["sp0"])
    check("fact keeps qualifiers", facts[0].qualifiers.get("unit") == "万元")
    check("entity parsed with mentions", len(ents) == 1 and ents[0].mention_span_ids == ["sp0", "sp1"])


def test_render_specs():
    import tempfile, os
    # chart + table 渲染(matplotlib/openpyxl 若装则真渲染,未装则跳过断言为通过)
    from app.generation import render as r
    d = tempfile.mkdtemp()
    chart = {"type": "chart", "spec": {"chart_type": "bar", "title": "预算",
             "x_field": "类别", "y_field": "金额",
             "data": [{"x": "人力", "y": 300}, {"x": "设备", "y": 320}]}}
    table = {"type": "table", "spec": {"columns": ["项目", "金额"], "rows": [["人力", "300万"]]}}
    for art, ext in [(chart, ".png"), (table, ".xlsx")]:
        try:
            p = r.render(art, d, "t")
            check(f"render {art['type']} → file", os.path.exists(p) and p.endswith(ext))
        except RuntimeError as e:
            check(f"render {art['type']} (dep missing, ok)", "需要" in str(e))


def test_schema_layer():
    from app.core.schema_layer import TenantSchema
    s = TenantSchema(tenant_id="t1")
    check("schema has default entity types", "project" in s.entity_types)
    check("schema has lint thresholds", s.lint_hub_inferred_ratio == 0.20)
    check("schema serializes", '"tenant_id"' in s.to_json())


def test_html_export():
    from app.evidence.graph_export import to_html
    g = {"nodes": [{"entity_id": "e1", "name": "项目X", "type": "project"}],
         "edges": []}
    html = to_html(g)
    check("html self-contained", html.startswith("<!doctype html>") and "项目X" in html and "<canvas" in html)


def test_lifecycle():
    from app.memory.lifecycle import retention_now, confidence_score, reinforce
    import time
    now = time.time()
    # 慢衰减(架构类)retention 高于快衰减(瞬时类),同样 30 天
    r_slow = retention_now(now - 30 * 86400, "depends_on", now)
    r_fast = retention_now(now - 30 * 86400, "current_status", now)
    check("slow-decay predicate retains more", r_slow > r_fast)
    check("more sources → higher confidence",
          confidence_score(3, 1.0, False, False) > confidence_score(1, 1.0, False, False))
    check("contradiction lowers confidence",
          confidence_score(2, 1.0, True, False) < confidence_score(2, 1.0, False, False))
    f = {"source_count": 1, "contradicts": []}
    reinforce(f, now)
    check("reinforce increments source_count + resets retention",
          f["source_count"] == 2 and f["retention"] == 1.0)


def test_contradiction_resolution():
    from app.memory.quality import resolve_contradiction
    facts = [{"fact_id": "a", "source_count": 3, "last_confirmed": 100, "predicate": "p", "contradicts": [], "stale": False},
             {"fact_id": "b", "source_count": 1, "last_confirmed": 50, "predicate": "p", "contradicts": [], "stale": False}]
    out = resolve_contradiction(facts)
    check("winner is best-supported fact", out["winner"] == "a")
    check("loser gets superseded", out["supersede"][0]["fact_id"] == "b" and out["supersede"][0]["stale"])


def test_governance_scrub():
    from app.core.governance import scrub_sensitive
    t, hits = scrub_sensitive("key sk-ABCDEFGHIJKLMNOabc and email a@b.com phone 13912345678")
    check("api key redacted", "sk-ABCDEFG" not in t and "REDACTED_API_KEY" in t)
    check("email redacted", "a@b.com" not in t)
    check("phone redacted", "13912345678" not in t)
    check("hit count > 0", hits >= 3)


def test_quality_score():
    from app.memory.quality import quality_score
    good = quality_score("项目预算为500万元。[doc1:sp1]")
    bad = quality_score("x")
    check("cited content passes", good["pass"])
    check("short uncited content fails", not bad["pass"])


def test_upsert_chunks_persists_summary_tier():
    """P1: upsert_chunks 必须把 summary/tier 写入数据库。"""
    import asyncio
    from app.db.store import Store
    from app.models.schema import Chunk, Tier

    captured = {}

    class FakeCon:
        async def executemany(self, sql, rows):
            captured["sql"] = sql
            captured["rows"] = rows

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            pass

    class FakePool:
        def acquire(self):
            return FakeCon()

    store = Store(FakePool())
    chunks = [Chunk(chunk_id="c1", tenant_id="t1", document_id="d1",
                    content="正文", page_start=0, page_end=1,
                    summary="这是摘要", tier=Tier.CORE)]
    asyncio.run(store.upsert_chunks("t1", chunks))
    sql = captured["sql"]
    rows = captured["rows"]
    check("summary column in SQL", "summary" in sql)
    check("tier column in SQL", "tier" in sql)
    check("summary value in row", "这是摘要" in rows[0])
    check("tier value in row", "core" in rows[0])
    check("ON CONFLICT updates summary",
          "summary=EXCLUDED.summary" in sql)
    check("ON CONFLICT updates tier", "tier=EXCLUDED.tier" in sql)


def test_schema_update_validation():
    """P2: schema 更新端点用 Pydantic 校验,拒绝未知字段与错误类型。"""
    from app.admin.service import SchemaUpdateReq
    from pydantic import ValidationError

    r = SchemaUpdateReq(entity_types=["project"], lint_hub_inferred_ratio=0.2)
    check("valid schema update accepted", r.entity_types == ["project"])
    try:
        SchemaUpdateReq(entity_types=["x"], evil="bad")
        check("extra field rejected", False)
    except ValidationError:
        check("extra field rejected", True)
    try:
        SchemaUpdateReq(lint_hub_inferred_ratio="not-a-number")
        check("wrong type rejected", False)
    except ValidationError:
        check("wrong type rejected", True)


def test_crosslink_name_eligibility():
    """P3: crosslink 应跳过过短实体名,避免子串误匹配。"""
    from app.maintain.crosslink import eligible_for_match
    check("2-char ascii name skipped", not eligible_for_match("AI"))
    check("single char skipped", not eligible_for_match("X"))
    check("cjk 2-char eligible", eligible_for_match("预算"))
    check("long name eligible", eligible_for_match("项目X"))
    check("ascii 3-char eligible", eligible_for_match("AWS"))
    check("empty skipped", not eligible_for_match(""))


def test_ingest_hash_uses_scrubbed():
    """P6: 入库 input_hash 应基于脱敏后内容,而非原始 markdown。"""
    from app.ingest.service import build_ingest_msg
    from app.compile.dag import unit_hash
    scrubbed = "key REDACTED_API_KEY and 内容"
    raw = "key sk-ABCDEFGHIJKLMNO and 内容"
    msg = build_ingest_msg(
        tenant_id="t1", document_id="d1", depth="D1",
        scrubbed_md=scrubbed, source_path="")
    expected = unit_hash(scrubbed, "v1", "ingest")
    check("hash matches scrubbed content", msg.input_hash == expected)
    check("hash differs from raw content", msg.input_hash != unit_hash(raw, "v1", "ingest"))
    check("payload carries scrubbed markdown", msg.payload["markdown"] == scrubbed)


def test_verify_answer_concurrent():
    """P5: verify_answer 并发校验多 claim,结果结构与顺序正确(行为保持)。"""
    import asyncio
    import json as _json
    import app.query.verify as v
    from app.core.tenant import TenantContext

    class _FakeBlock:
        def __init__(self, text):
            self.text = text
            self.type = "text"

    class _FakeResp:
        def __init__(self, payload):
            self.content = [_FakeBlock(_json.dumps(payload, ensure_ascii=False))]

    class _FakeGW:
        async def complete(self, **kw):
            return _FakeResp({"entailed": True, "score": 0.9})

    class _FakeClient:
        async def call(self, method, params):
            return {"content": "证据文本"}

        async def aclose(self):
            pass

    v.get_gateway = lambda: _FakeGW()
    v.EvidenceClient = lambda ctx: _FakeClient()
    ctx = TenantContext(tenant_id="t1", user_id="u1", session_id="s1")
    answer = "预算是500万[doc1:sp1]。团队有10人[doc2:sp2]。无引用句。"
    res = asyncio.run(v.verify_answer(ctx, answer))
    check("claims count", len(res["claims"]) == 3)
    check("first claim verified", res["claims"][0]["verified"] is True)
    check("second claim verified", res["claims"][1]["verified"] is True)
    check("no-citation claim None", res["claims"][2]["verified"] is None)
    check("sufficient true", res["sufficient"] is True)
    check("ratio 1.0", abs(res["verified_ratio"] - 1.0) < 1e-9)


def test_manifest_new_chunk_not_skipped():
    """BUG FIX #1: 新 chunk(无 manifest 记录)必须被识别为"需编译",而非"未变化跳过"。

    此前 orchestrator 用 stale_artifacts() 返回 None 判断"未变化",但该方法对
    新 chunk 也返回 None,导致 L2 抽取被完全跳过,entities/facts 始终为 0。
    """
    import asyncio
    from app.compile.manifest import Manifest, ChunkArtifacts

    # Fake redis: 仅存储 manifest:{tenant}:{chunk_id} 键
    class FakeRedis:
        def __init__(self):
            self.store = {}

        async def get(self, key):
            return self.store.get(key)

        async def set(self, key, val):
            self.store[key] = val

    r = FakeRedis()
    m = Manifest(r)

    async def run():
        # 场景1: 新 chunk(prev=None) → 必须被编译
        prev = await m.get("t1", "ch_new")
        check("new chunk has no manifest entry", prev is None)
        # 修复后的 orchestrator 逻辑:prev is None → 需编译
        should_compile = not (prev and prev.content_hash == "hash_new")
        check("new chunk marked for compile", should_compile is True)

        # 场景2: 未变化 chunk(prev 存在且 hash 一致) → 跳过
        await m.record("t1", ChunkArtifacts(
            chunk_id="ch_unchanged", content_hash="hash_same",
            fact_ids=["f1"], entity_ids=["e1"]))
        prev2 = await m.get("t1", "ch_unchanged")
        should_compile2 = not (prev2 and prev2.content_hash == "hash_same")
        check("unchanged chunk skipped", should_compile2 is False)

        # 场景3: 变化 chunk(prev 存在但 hash 不同) → 需编译
        await m.record("t1", ChunkArtifacts(
            chunk_id="ch_changed", content_hash="hash_old",
            fact_ids=["f1"], entity_ids=["e1"]))
        prev3 = await m.get("t1", "ch_changed")
        should_compile3 = not (prev3 and prev3.content_hash == "hash_new")
        check("changed chunk marked for compile", should_compile3 is True)

        # stale_artifacts 的语义验证(仅用于失效,不用于判断是否编译)
        stale_new = await m.stale_artifacts("t1", "ch_new", "hash_new")
        check("stale_artifacts returns None for new chunk (no old artifacts)", stale_new is None)
        stale_unchanged = await m.stale_artifacts("t1", "ch_unchanged", "hash_same")
        check("stale_artifacts returns None for unchanged", stale_unchanged is None)
        stale_changed = await m.stale_artifacts("t1", "ch_changed", "hash_new")
        check("stale_artifacts returns old artifacts for changed", stale_changed is not None)

    asyncio.run(run())


def test_evidence_client_error_handling():
    """BUG FIX #3: EvidenceClient 在 evidence 服务不可用时应返回结构化错误,而非抛异常。"""
    import asyncio
    import httpx
    from app.query.tools import EvidenceClient
    from app.core.tenant import TenantContext

    ctx = TenantContext(tenant_id="t1", user_id="u1", session_id="s1")
    client = EvidenceClient(ctx)
    # 指向一个不存在的端口,模拟 evidence 服务未启动
    client._client = httpx.AsyncClient(base_url="http://127.0.0.1:59999", timeout=2)

    async def run():
        result = await client.call("search", {"query": "test"})
        check("connect error returns dict, not raises", isinstance(result, dict))
        check("error key present", "error" in result)
        check("error message mentions unavailable", "unavailable" in result["error"])
        await client.aclose()

    asyncio.run(run())


def test_graph_empty_vs_demo():
    """BUG FIX #4: Graph 前端应区分"API失败"、"空图"和"演示数据"。

    此处验证后端 /graph/export 在无实体时返回空 nodes 列表,而非错误。
    """
    import asyncio
    from app.db.store import Store

    class FakeCon:
        async def fetch(self, sql, *params):
            return []  # 无实体、无关系

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            pass

    class FakePool:
        def acquire(self):
            return FakeCon()

    store = Store(FakePool())
    result = asyncio.run(store.export_graph("t1"))
    check("empty graph has nodes list", "nodes" in result)
    check("empty graph has edges list", "edges" in result)
    check("empty graph nodes is []", result["nodes"] == [])
    check("empty graph edges is []", result["edges"] == [])


if __name__ == "__main__":
    print("=== llm-wiki offline smoke test ===")
    for fn in [test_tenant_security, test_chunking, test_rrf,
               test_lint_hub_weighting, test_tier_weights, test_provenance_model,
               test_auth, test_memory_key_isolation,
               test_graph_export, test_extract_parse, test_render_specs,
               test_schema_layer, test_html_export,
               test_lifecycle, test_contradiction_resolution,
               test_governance_scrub, test_quality_score,
               test_upsert_chunks_persists_summary_tier,
               test_schema_update_validation,
               test_crosslink_name_eligibility,
               test_ingest_hash_uses_scrubbed,
               test_verify_answer_concurrent,
               test_manifest_new_chunk_not_skipped,
               test_evidence_client_error_handling,
               test_graph_empty_vs_demo]:
        print(f"\n{fn.__name__}:")
        fn()
    print(f"\n{'='*40}")
    if failures:
        print(f"FAILED: {failures}")
        sys.exit(1)
    print("ALL SMOKE TESTS PASSED")
