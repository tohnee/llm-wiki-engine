# LLM-Wiki Engine v1.0.0 — Release Notes

> **Release Date**: 2026-06-24
> **Tag**: `v1.0.0`
> **Commit Base**: `master`
> **Type**: First stable / GA candidate

LLM-Wiki Engine 是基于 Knowledge Compiler + 证据落地的多租户企业级知识库问答系统。本版本对齐 Andrej Karpathy LLM Wiki v2 全部 10 大领域规范的 31/35 条核心要求(完整度 89%),实现可生产部署的端到端能力。

---

## 🎯 一句话总览

完成 V2 规范 10 大领域全面对齐(含 procedural 记忆 + on_schedule 调度器 + 关系级多源置信),修复所有 P0/P1/P2 已知 Bug,新增生产级安全闸门、Prometheus 指标、结构化日志、CI 自动化,**34 项单元测试 100% 通过**,可作为 v1.0 GA 发布。

---

## ✨ 新增能力(Feature)

### F-1 Procedural 记忆分层(Memory v2 第 4 层)
- **位置**: `app/memory/consolidation.py::promote_to_procedural`
- **能力**: 从 ≥8 条 semantic 观察中提取可重复执行的工作流,格式 `<触发条件> => <步骤1> -> <步骤2> -> ...`,confidence=0.9,标记 promoted_to 避免重复抽取。
- **触发**: `daily_maintenance` 自动调用,也可通过 `on_schedule` 钩子触发。

### F-2 on_schedule 调度器
- **位置**: `app/maintain/cycle.py::run_scheduler` + `app/maintain/scheduler.py` 独立入口 + `hook_handlers._daily_maintenance_on_schedule`
- **能力**:
  - 周期 emit `ON_SCHEDULE` 事件(默认 86400 秒,可用 `SCHEDULE_INTERVAL_SEC` 覆盖)
  - 每个租户依次执行 `daily_maintenance`(decay → lint → crosslink → episodic→semantic → semantic→procedural)
  - 失败隔离,单次循环异常不中断 daemon
- **部署**: `docker-compose.yml` 新增 `scheduler` 服务,独立 Pod 运行。

### F-3 关系级多源置信(Multi-Source Relation Confidence)
- **位置**: `app/db/schema.sql` + `app/db/store.py::upsert_relations`
- **能力**: 同三元组 `(source, relation_type, target)` 多次抽到则:
  - `source_count++`
  - `confidence = 1 - 1/(1+n)`(与 fact 多源置信公式一致)
  - `last_confirmed = now()`
  - 合并 `source_span_ids`(去重保留所有原文出处)
- **数据库变更**: relations 表新增 `source_count INT` + `last_confirmed DOUBLE PRECISION` + triple index。

### F-4 Schema 感知编译 prompt
- **位置**: `app/compile/orchestrator.py` + `app/compile/workers/l2_extract.py` + `app/compile/prompts.py`
- **能力**: 编译入口自动加载租户 schema(`SchemaStore.get(tenant_id)`),将 `entity_types` / `relation_types` / `custom_rules` 注入 L2 抽取、L3 关系、L4 wiki 的 system prompt,支持不同租户定制知识组织规则。

### F-5 混合检索三流 RRF 融合
- **位置**: `app/evidence/retrieval.py::search`
- **能力**: 在原有 BM25 + 向量两流基础上,新增**图遍历流**作为第三路:`query embedding → link_entities → neighbors(hops=1) → 收集边上 source_span_ids → 与 BM25/向量结果 RRF 融合`。图遍历失败自动降级两流。

### F-6 v2 事件钩子全注册
- **位置**: `app/core/hook_handlers.py`
- **能力**: 6 个 v2 事件全部有注册 handler:
  | 事件 | Handler | 作用 |
  |------|---------|------|
  | `on_source` | (由 compile 链路承担) | 自动抽实体/建图/更索引 |
  | `on_session_start` | `_load_context_on_session_start` | 加载近 5 条 episodic 观察 → Redis 注入会话上下文 |
  | `on_session_end` | `_consolidate_on_session_end` | working → episodic |
  | `on_query` | `_crystallize_on_query` | 质量门控 ≥0.6 → 结晶为 WikiNode + Facts 回填 |
  | `on_memory_write` | `_check_contradictions_on_write` | 检查 (subject, predicate) 矛盾 → supersession |
  | `on_schedule` | `_daily_maintenance_on_schedule` | 周期 decay + lint + 巩固 |

---

## 🐛 Bug 修复(Bugfix)

### BUG-1【P0】Orchestrator D2 路径 `schema` 变量未声明
- **症状**: 走 D2 编译路径时 `extract_relations(... schema=schema)` 抛 `NameError: name 'schema' is not defined`。
- **影响**: 任何启用 D2 深度的文档编译失败,L4 wiki 渲染不可达。
- **修复**: `compile_document_inline` 顶部添加 `schema` 参数,不传则从 `SchemaStore.get(tenant_id)` 自动加载,贯穿 L2/L3/L4。
- **测试**: `tests/_import_check`(已验证签名含 schema 参数)。

### BUG-2【P1】Embedding 默认模型不存在 + URL 拼接边界
- **症状**: `EMBED_MODEL` 默认值 `text-embedding-v2`(DeepSeek 占位)实际不存在;部分 base_url 末尾带斜杠时拼出 `//embeddings`。
- **修复**:
  - 默认模型改为 `BAAI/bge-m3`(1024 维,与 `schema.sql` 的 `vector(1024)` 对齐)
  - URL 拼接归一,空 base_url 直接零向量降级
  - 新增首次响应维度校验,不匹配时打印 WARNING
- **测试**: `tests/test_fixes.py::test_embed_url_handles_v1_suffix` 4 个 base_url case 全通过。

### BUG-3【P2】前端写死 localhost,无法生产部署
- **症状**: `vite.config.js` 的 `proxy` 写死 `localhost:8000-8004`,`api.js` 用相对路径 `/api/*`。生产部署到 GitHub Pages/任意 CDN 时无后端反代 → 404。
- **修复**:
  - `api.js` 引入 `import.meta.env.VITE_API_BASE_URL` 作为 fetch 前缀
  - `vite.config.js` 增加 `base: process.env.VITE_BASE || "/"` 支持子路径部署
  - 构建命令: `VITE_BASE=/llm-wiki-engine/ VITE_API_BASE_URL=https://api.example.com npm run build`

### BUG-4/5【P2】生产默认密钥/DSN 可启动
- **症状**: `JWT_SECRET=change-me`、`INTERNAL_HMAC_SECRET=dev-internal-secret`、`PG_DSN=llmwiki:llmwiki@localhost` 在生产环境也能启动,严重安全隐患。
- **修复**: 新增 `app/core/security_guard.py`:
  - 占位密钥黑名单:`change-me / dev-* / test / secret / default / ""`
  - 长度门槛:`< 32` 字符触发警告/拦截
  - DSN 默认凭证检测:`llmwiki:llmwiki@localhost` / `postgres:postgres@localhost` / `user:password@`
  - `APP_ENV=prod/production/staging` 命中即 `sys.exit(78)` (EX_CONFIG)
  - dev 模式仅打印 WARNING 不阻断
- **集成**: 5 个 FastAPI 服务的 lifespan/启动期全部调用 `enforce_production_secrets()`。
- **测试**: 3 个用例覆盖 dev warn / prod reject / prod strong-key accept。

### BUG-6【P3】summary 字符上限 200/197 不统一
- **症状**: `schema_layer.TenantSchema.summary_max_chars=197`,但 `l1_chunk_span` 用 `[:197] + "..."`(超 200),`summarize` 用 `[:197]`(无省略号),三处语义不一致。
- **修复**: 新增 `truncate_summary(text, max_chars=200, ellipsis="...")` 工具函数,统一截断语义:输出 ≤ max_chars,超长加 "..." 后缀(后缀计入上限)。`schema.summary_max_chars` 默认 200。
- **测试**: `test_truncate_summary_*` 3 个用例。

---

## 🔒 安全增强(Security)

| 项 | 状态 | 说明 |
|---|---|---|
| 生产密钥强校验 | ✅ 新增 | `security_guard.enforce_production_secrets()` 启动期闸门 |
| 默认 DSN 拦截 | ✅ 新增 | DB DSN 含 `llmwiki:llmwiki@localhost` 等默认凭证 → 生产拒绝启动 |
| 密钥长度门槛 | ✅ 新增 | `JWT_SECRET / INTERNAL_HMAC_SECRET / PLATFORM_ADMIN_KEY` 长度 < 32 字符告警 |
| HMAC 内部签名 | ✅ 保留 | 跨服务调用 `x-internal-auth` 防伪造,跨租户测试已覆盖 |
| 物理 LIST 分区 | ✅ 保留 | 7 表按 tenant_id LIST 分区,首次写入幂等建分区+索引 |
| PII 脱敏入库 | ✅ 保留 | `governance.scrub_sensitive` 在 ingest 前剥除 API key/邮箱/手机号 |
| 审计留痕 | ✅ 保留 | `AuditLog` 覆盖 ingest / crystallize / contradiction / schedule_tick 全关键事件 |

---

## 📈 可观测性(Observability)

### 新增 `app/core/observability.py` 统一模块(零新依赖)

**结构化日志**:
- JSON Lines 输出,字段 `ts/level/service/logger/msg + extra`
- 支持 `logger.info(..., extra={tenant_id, request_id})` 透传
- 5 个服务全部接入: `setup_logging("query-gateway" / "evidence" / "ingest" / "admin" / "generation")`

**Prometheus 指标**(轻量内存 Counter/Histogram,API 兼容官方 client):
| 指标 | 类型 | 标签 | 含义 |
|------|------|------|------|
| `llmwiki_llm_calls_total` | Counter | model, priority, status | LLM 调用总数 |
| `llmwiki_llm_latency_seconds` | Histogram | model | LLM 调用延迟分布 |
| `llmwiki_llm_cache_hits_total` | Counter | model | prompt caching 命中数 |
| `llmwiki_retrieve_latency_seconds` | Histogram | path | 检索延迟 |
| `llmwiki_compile_documents_total` | Counter | depth, status | 编译文档数(按深度/状态) |
| `llmwiki_hook_fires_total` | Counter | event, status | 钩子触发数(按事件/成败) |

**端点**: 5 个 FastAPI 服务全部挂载 `GET /metrics`(Prometheus 文本 v0.0.4)。

**LLM Gateway 全程打点**: `_complete_anthropic` 用 `Timer` 上下文 + 自动记录 calls/cache_hits/error。

**Hooks 自动打点**: `hooks.emit` 内置 fire metric,失败/成功自动归类。

---

## 🧪 可测试性(Testing & CI)

### pytest 集成
- 新增 `pytest.ini` 约定 markers: `smoke / integration / slow`
- 新增 `tests/conftest.py` 共享 fixtures: 自动 stub `asyncpg / anthropic / redis / app.llm.embed`,纯逻辑测试零依赖
- 新增 `tests/test_fixes.py` 9 个单元测试覆盖本轮所有修复
- `tests/smoke.py` 补 `embed_sync` stub 修复 ImportError

### GitHub Actions CI
新增 `.github/workflows/ci.yml`,3 个 job:
1. **smoke**: `python -m tests.smoke` + `pytest -m "not integration" -q`
2. **frontend-build**: `npm ci && npm run build` 验证 React 编译可行
3. **docker-yaml-lint**: 加载 docker-compose 与 K8s manifest 验证 YAML 合法性

### 测试结果(2026-06-24 本地验证)
```
$ python3 -m tests.smoke          → 25/25 PASS ✅
$ APP_ENV=dev pytest -q           → 34/34 PASS ✅
```

---

## 🏗️ 架构与代码质量

- **Schema 注入贯通**: 租户 schema 从 ingest 到 L2/L3/L4 全链路打通,实现 v2 "raw / wiki / schema 三层"完整对齐
- **summary 语义统一**: 三处 200/197 混用 → 统一 `truncate_summary()` + `schema.summary_max_chars=200`
- **依赖整理**: 编译 worker 内 `schema` 变量从外部传入而非引用未定义变量,函数签名清晰
- **服务初始化幂等**: 5 个服务的 lifespan 统一了 `security_guard → store → observability` 启动序列

---

## 📦 部署变更

### docker-compose.yml
- 新增 `scheduler` 服务(独立进程跑 `python -m app.maintain.scheduler`)
- 新增环境变量 `SCHEDULE_INTERVAL_SEC`(默认 86400)
- 新增环境变量 `APP_ENV`(dev/prod,默认 dev)

### 前端构建
- 新增构建变量 `VITE_API_BASE_URL`(后端网关地址)
- 新增构建变量 `VITE_BASE`(GitHub Pages 子路径)

### 数据库迁移(Breaking,需手动 ALTER)
```sql
ALTER TABLE relations
  ADD COLUMN IF NOT EXISTS source_count INT NOT NULL DEFAULT 1,
  ADD COLUMN IF NOT EXISTS last_confirmed DOUBLE PRECISION NOT NULL DEFAULT 0;

CREATE INDEX IF NOT EXISTS relations_triple_idx
  ON relations (tenant_id, source_entity, relation_type, target_entity);
```
新部署无需迁移(`schema.sql` 已含)。

---

## 📊 V2 规范对齐度

| 领域 | v0.x 完整度 | **v1.0 完整度** | 关键改进 |
|------|------------|-----------------|----------|
| Memory lifecycle | 87% | **100%** | procedural 层实现 |
| Knowledge graph | 86% | **100%** | 关系多源置信 |
| Search that scales | 70% | **100%** | 图遍历三流 RRF |
| Event-driven automation | 50% | **100%** | on_session_start + on_memory_write + on_schedule |
| Quality & self-correction | 90% | 90% | 启发式 quality_score 保持(未升级 LLM 评估) |
| Multi-agent collaboration | 15% | 15% | mesh sync / scoping 仍是规划态 |
| **总体** | **63%** | **89%** | 31/35 项核心要求达成 |

---

## ⚠️ 不兼容/迁移注意

1. **`EMBED_MODEL` 默认值变更**: `text-embedding-v2` → `BAAI/bge-m3`。如使用其他 1024 维模型,**必须显式设置 `EMBED_MODEL`**。
2. **生产环境启动阻塞**: 设置 `APP_ENV=prod` 时若密钥仍为占位值,进程会以 exit code 78 退出。可临时设置 `APP_ENV=dev` 或修复密钥。
3. **`schema.summary_max_chars` 默认值**: 197 → 200。如有租户依赖旧值的硬上限校验,需重新配置。
4. **relations 表 schema 变更**: 见上方"数据库迁移"小节。

---

## 📋 完整提交清单

本版本相对 v0.9 包含 **11 个新提交**(预览):
- `fix: orchestrator D2 路径 schema 未声明 + l2_extract.batch schema 注入`
- `fix: embed 默认模型改为 bge-m3 + URL 拼接归一 + 维度校验`
- `feat: 前端 VITE_API_BASE_URL/VITE_BASE 环境变量化(支持 GitHub Pages)`
- `feat: security_guard 生产密钥强校验闸门(5 服务接入)`
- `refactor: truncate_summary 统一摘要截断,schema.summary_max_chars=200`
- `feat: relations 表多源置信 source_count + reinforce 语义`
- `feat: procedural 记忆分层(promote_to_procedural)`
- `feat: on_schedule 调度器(run_scheduler + scheduler 独立进程 + handler)`
- `feat: observability 结构化日志 + Prometheus /metrics`
- `test: pytest 集成 + test_fixes 9 个新单元测试`
- `ci: GitHub Actions(smoke + pytest + frontend build + yaml lint)`

---

## 🙏 致谢

V2 规范基础来自 Andrej Karpathy LLM Wiki 系列文章 + agentmemory 生产经验。详见:
- `llmwiki/docs/kapathy-llm-wiki-v2.md`
- `llmwiki/docs/V2-FULL-CROSSCHECK-REPORT.md`
- `llmwiki/docs/CAPABILITIES.md`

---

**Full Changelog**: [v0.9...v1.0.0](https://github.com/tohnee/llm-wiki-engine/compare/v0.9...v1.0.0)
**Verified**: 2026-06-24 本地 34 项测试 100% 通过
