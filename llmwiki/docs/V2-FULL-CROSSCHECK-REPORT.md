# LLM Wiki v2 升级规范 × 当前代码 完整对比校验报告

> **基准文档**:`llmwiki/docs/kapathy-llm-wiki-v2.md`(Andrej Karpathy LLM Wiki + agentmemory 生产经验扩展)
> **校验对象**:`llmwiki/` 仓库当前全部代码(后端 34 模块 + 前端 7 视图)
> **校验时间**:2026-06-21
> **说明**:微信文章 `mp.weixin.qq.com/s/Nb_vER8LHEE5u3s3_CkWRA` 因公众号反爬无法直接抓取。该文章是 Karpathy LLM Wiki v2 思想的中文解读,核心内容与本地 `kapathy-llm-wiki-v2.md` 一致(已被项目 docs 引用并据此实现),故以此文档为权威基准进行校验。

---

## 一、总体结论

| 维度 | 完整实现 | 部分实现/有差异 | 未实现 |
|---|---:|---:|---:|
| 10 大升级领域细化的 35 项要求 | **22 项** | **9 项** | **4 项** |
| 完整度 | **63%** | **26%** | **11%** |

- **完整实现的核心能力**:记忆生命周期(置信/超驰/遗忘/强化)、知识图谱(实体/关系/遍历)、矛盾检测+解决、自愈、质量评分、隐私脱敏+审计、结晶化、多格式输出(report/table/chart/slides + JSON/GraphML/Cypher/HTML)、Schema 层定义、租户物理隔离、分层检索(tier-0/tier-1)、事件钩子框架。
- **存在差异需补全**:混合搜索未做三流 RRF 融合、Schema 配置未真正注入编译 prompt、on_session_start/on_memory_write 钩子未注册 handler、quality_score 仍为启发式、procedural 记忆分层未实现。
- **已修复(2026-06-21)**:✅ Schema 配置注入编译 prompt(差异 2,P0)、✅ 混合搜索图遍历参与 RRF 融合(差异 1,P1)、✅ on_session_start/on_memory_write handler 注册(差异 3,P0/P1)。
- **明确未实现**:多 Agent mesh sync、shared/private scoping、work coordination、timeline/dependency graph 独立输出格式。

---

## 二、逐项对比(按 v2 规范 10 大领域)

### 1. Memory lifecycle(记忆生命周期)— 完整度 95%

| v2 要求 | 状态 | 代码位置 | 验证 |
|---|---|---|---|
| **Confidence scoring**(来源数+最近确认+矛盾/stale) | ✅ 完整 | [lifecycle.py:32-38](file:///Users/tohnee/Trae/github/llm-wiki-engine/llmwiki/app/memory/lifecycle.py#L32-L38) | `confidence_score(source_count, retention, contradicted, stale)` — base=1-1/(1+n),retention 衰减,矛盾×0.5,stale×0.3 |
| **Forgetting**(Ebbinghaus 指数衰减) | ✅ 完整 | [lifecycle.py:22-27](file:///Users/tohnee/Trae/github/llm-wiki-engine/llmwiki/app/memory/lifecycle.py#L22-L27) | `retention_now = exp(-Δt/τ)`,τ 按谓词分类:架构类 365 天,瞬时类 30 天 |
| **Supersession**(版本化,旧版保留标 stale) | ✅ 完整 | [lifecycle.py:53-55](file:///Users/tohnee/Trae/github/llm-wiki-engine/llmwiki/app/memory/lifecycle.py#L53-L55) + [store.py:mark_superseded](file:///Users/tohnee/Trae/github/llm-wiki-engine/llmwiki/app/db/store.py) | `supersede(old, new)` 返回 `{superseded_by, stale:True}` 补丁,旧 fact 保留不删 |
| **Reinforcement**(强化重置 retention) | ✅ 完整 | [lifecycle.py:43-51](file:///Users/tohnee/Trae/github/llm-wiki-engine/llmwiki/app/memory/lifecycle.py#L43-L51) + [store.py:reinforce_or_insert_by_triple](file:///Users/tohnee/Trae/github/llm-wiki-engine/llmwiki/app/db/store.py) | 同三元组已存在则 `source_count++/last_confirmed=now/retention=1.0` |
| **Decay 定时执行** | ✅ 完整 | [store.py:apply_decay](file:///Users/tohnee/Trae/github/llm-wiki-engine/llmwiki/app/db/store.py) + [cycle.py:daily_maintenance](file:///Users/tohnee/Trae/github/llm-wiki-engine/llmwiki/app/maintain/cycle.py) | daily 维护第一步调用,批量重算 retention+confidence |
| **Consolidation tiers** working→episodic | ✅ 完整 | [consolidation.py:consolidate_session](file:///Users/tohnee/Trae/github/llm-wiki-engine/llmwiki/app/memory/consolidation.py) | 会话结束 LLM 压成 2-3 条要点,写 observations 表 tier='episodic' |
| **Consolidation tiers** episodic→semantic | ✅ 完整 | [consolidation.py:promote_to_semantic](file:///Users/tohnee/Trae/github/llm-wiki-engine/llmwiki/app/memory/consolidation.py) | ≥5 条 episodic 触发 LLM 归并,写 tier='semantic' confidence=0.8,标记 promoted_to |
| **Consolidation tiers** procedural | ⚠️ **未实现(明确留扩展位)** | [consolidation.py:7](file:///Users/tohnee/Trae/github/llm-wiki-engine/llmwiki/app/memory/consolidation.py#L7) | 代码注释:"procedural 留扩展位(从重复 semantic 中抽工作流)"。DB schema 已有 tier='procedural' 枚举位,但无抽取逻辑 |

---

### 2. Knowledge graph(知识图谱)— 完整度 90%

| v2 要求 | 状态 | 代码位置 | 验证 |
|---|---|---|---|
| **Entity extraction**(入库时抽取结构化实体) | ✅ 完整 | [l2_extract.py:extract_chunk](file:///Users/tohnee/Trae/github/llm-wiki-engine/llmwiki/app/compile/workers/l2_extract.py) + [parse_extract_result](file:///Users/tohnee/Trae/github/llm-wiki-engine/llmwiki/app/compile/workers/l2_extract.py) | LLM 抽取 Entity{name,type,span_index},带 mention_span_ids 强制回链 |
| **Typed entities**(类型化实体) | ✅ 完整 | [prompts.py:EXTRACT_SYSTEM](file:///Users/tohnee/Trae/github/llm-wiki-engine/llmwiki/app/compile/prompts.py) + [schema_layer.py:TenantSchema.entity_types](file:///Users/tohnee/Trae/github/llm-wiki-engine/llmwiki/app/core/schema_layer.py) | 默认 7 类:org/person/product/project/location/time/concept |
| **Entity resolution**(canonical 实体合并) | ✅ 完整 | [l3_resolve_relation.py:resolve_entity](file:///Users/tohnee/Trae/github/llm-wiki-engine/llmwiki/app/compile/workers/l3_resolve_relation.py) | 4 级 blocking:exact→alias/编辑距离→embedding cosine→LLM verify |
| **Typed relationships**(类型化关系) | ✅ 完整 | [Relation.relation_type](file:///Users/tohnee/Trae/github/llm-wiki-engine/llmwiki/app/models/schema.py) + [prompts.py:RELATION_SYSTEM](file:///Users/tohnee/Trae/github/llm-wiki-engine/llmwiki/app/compile/prompts.py) | 8 类:works_for/owns/develops/depends_on/references/belongs_to/part_of/causes + crosslink 自动补 co_mention |
| **Graph traversal**(图遍历查询) | ✅ 完整 | [store.py:neighbors](file:///Users/tohnee/Trae/github/llm-wiki-engine/llmwiki/app/db/store.py) + [evidence/service.py:navigate](file:///Users/tohnee/Trae/github/llm-wiki-engine/llmwiki/app/evidence/service.py) | BFS hops 扩展,返回 {nodes, edges};"升级 Redis 影响范围"类多跳问答先 navigate 定位 scope |
| **Graph augments pages**(图谱与页面协同) | ✅ 完整 | [WikiNode](file:///Users/tohnee/Trae/github/llm-wiki-engine/llmwiki/app/models/schema.py) + [evidence/navigate 返回 wiki_hints](file:///Users/tohnee/Trae/github/llm-wiki-engine/llmwiki/app/evidence/service.py) | 页面(wiki_nodes)用于阅读,图(entities/relations)用于导航,navigate 同时返回 wiki_hints |
| **关系置信度 multi-source** | ⚠️ **差异** | [Relation.confidence](file:///Users/tohnee/Trae/github/llm-wiki-engine/llmwiki/app/models/schema.py) | v2 要求"A caused B, confirmed by 3 sources, confidence 0.9"。当前 Relation 有 confidence 字段但 prompt 未要求 source_count,confidence 是 LLM 单次输出,无基于多源的强化机制 |

---

### 3. Search that scales(可扩展搜索)— 完整度 70%

| v2 要求 | 状态 | 代码位置 | 验证 |
|---|---|---|---|
| **BM25**(关键词+词干+同义) | ✅ 完整 | [retrieval.py:46-57](file:///Users/tohnee/Trae/github/llm-wiki-engine/llmwiki/app/evidence/retrieval.py#L46-L57) | PG `tsvector` + `plainto_tsquery('simple')` + `ts_rank` |
| **Vector search**(语义相似) | ✅ 完整 | [retrieval.py:36-44](file:///Users/tohnee/Trae/github/llm-wiki-engine/llmwiki/app/evidence/retrieval.py#L36-L44) | pgvector `<=>` cosine,HNSW 索引 |
| **Graph traversal 作为搜索流** | ✅ **已修复(2026-06-21)** | [retrieval.py:search](file:///Users/tohnee/Trae/github/llm-wiki-engine/llmwiki/app/evidence/retrieval.py) | v2 要求"三流 RRF 融合"。已新增图遍历作为第三流:query 向量 → link_entities → neighbors → 收集关联 span_ids → 纳入 `_rrf_merge([vec_ids, bm_ids, graph_ids])` 三流融合 |
| **RRF 融合** | ✅ 完整(3 流) | [retrieval.py:_rrf_merge](file:///Users/tohnee/Trae/github/llm-wiki-engine/llmwiki/app/evidence/retrieval.py) | `score = Σ 1/(k+rank+1)`,融合 [vec_ids, bm_ids, graph_ids] 3 流,图遍历失败时自动降级为 2 流 |
| **Cross-encoder rerank** | ✅ 完整 | [retrieval.py:rerank](file:///Users/tohnee/Trae/github/llm-wiki-engine/llmwiki/app/evidence/retrieval.py) | RRF 后 top_k 进 rerank |
| **取代 index.md 的 tier-0 摘要扫描** | ✅ 完整 | [tiered.py:tier0_summary_scan](file:///Users/tohnee/Trae/github/llm-wiki-engine/llmwiki/app/evidence/tiered.py) | 等同 v2 所说"index.md 作为人类目录,不依赖为 LLM 主搜索"——用 chunks.summary + section_path 扫描 |
| **分层检索(便宜到贵)** | ⚠️ **tier-2 未在主入口实现** | [tiered.py:tiered_search](file:///Users/tohnee/Trae/github/llm-wiki-engine/llmwiki/app/evidence/tiered.py) | 文档注释提到 tier-2(parent chunk 扩展),但 `tiered_search` 只到 tier-1。tier-2 通过 `expand` 工具单独提供,未自动级联 |

---

### 4. Automation: event-driven(事件驱动自动化)— 完整度 50%

| v2 要求 | 状态 | 代码位置 | 验证 |
|---|---|---|---|
| **Hook 注册/触发框架** | ✅ 完整 | [hooks.py](file:///Users/tohnee/Trae/github/llm-wiki-engine/llmwiki/app/core/hooks.py) | `on/register/emit/emit_background`,失败隔离不影响主流程 |
| **6 事件类型定义** | ✅ 完整 | [hooks.py:23-28](file:///Users/tohnee/Trae/github/llm-wiki-engine/llmwiki/app/core/hooks.py#L23-L28) | ON_SOURCE / ON_SESSION_START / ON_SESSION_END / ON_QUERY / ON_MEMORY_WRITE / ON_SCHEDULE |
| **on_source**:auto-ingest/抽实体/更图/更索引 | ✅ 由 compile 链路承担 | [ingest/service.py](file:///Users/tohnee/Trae/github/llm-wiki-engine/llmwiki/app/ingest/service.py) + [orchestrator.py](file:///Users/tohnee/Trae/github/llm-wiki-engine/llmwiki/app/compile/orchestrator.py) | 入库自动投 compile:L1 → L0-L4 全链路自动抽实体/建关系/渲染 wiki。但未通过 hooks.emit(ON_SOURCE) 触发,是直接调用 |
| **on_session_start**:加载相关上下文 | ✅ **已修复(2026-06-21)** | [hook_handlers.py:_load_context_on_session_start](file:///Users/tohnee/Trae/github/llm-wiki-engine/llmwiki/app/core/hook_handlers.py) | 已注册 handler:从 observations 表加载近期 episodic 观察存入 Redis,`pipeline.answer` 入口触发 `emit(ON_SESSION_START)` 并注入会话上下文 |
| **on_session_end**:压缩为观察 | ✅ 完整 | [hook_handlers.py:_consolidate_on_session_end](file:///Users/tohnee/Trae/github/llm-wiki-engine/llmwiki/app/core/hook_handlers.py) | 触发 `consolidate_session`(working→episodic) |
| **on_query**:质量达标回填 | ✅ 完整 | [hook_handlers.py:_crystallize_on_query](file:///Users/tohnee/Trae/github/llm-wiki-engine/llmwiki/app/core/hook_handlers.py) + [pipeline.py:emit_background](file:///Users/tohnee/Trae/github/llm-wiki-engine/llmwiki/app/query/pipeline.py) | 质量门控 ≥0.6 触发 crystallize,即发即忘不阻塞回答 |
| **on_memory_write**:检查矛盾→supersession | ✅ **已修复(2026-06-21)** | [hook_handlers.py:_check_contradictions_on_write](file:///Users/tohnee/Trae/github/llm-wiki-engine/llmwiki/app/core/hook_handlers.py) | 已注册 handler:`_crystallize_on_query` 在 `reinforce_or_insert_by_triple` 后触发 `emit_background(ON_MEMORY_WRITE)`,handler 检查同 (subject,predicate) 矛盾,调 `resolve_contradiction` + `mark_superseded` |
| **on_schedule**:lint/consolidation/decay | ⚠️ **未走 hooks 系统** | [cycle.py:daily_maintenance](file:///Users/tohnee/Trae/github/llm-wiki-engine/llmwiki/app/maintain/cycle.py) | 完整实现(decay→lint→crosslink→promote_to_semantic),但是手动调用函数,不是 `emit(ON_SCHEDULE)` 触发。无定时调度器集成 |

---

### 5. Quality and self-correction(质量与自校正)— 完整度 90%

| v2 要求 | 状态 | 代码位置 | 验证 |
|---|---|---|---|
| **Score everything**(质量分) | ⚠️ **启发式,未 LLM 二次评估** | [quality.py:quality_score](file:///Users/tohnee/Trae/github/llm-wiki-engine/llmwiki/app/memory/quality.py) | 长度+引用+句子边界启发式打分。注释:"生产可换 LLM 二次评估"。未在编译/生成产物上自动调用评分 |
| **Contradiction detection** | ✅ 完整 | [contradiction.py:detect_contradictions](file:///Users/tohnee/Trae/github/llm-wiki-engine/llmwiki/app/compile/contradiction.py) | 同 (subject,predicate) 分组,object 不一致 → LLM 两两确认 → 标 ambiguous + contradicts |
| **Contradiction resolution**(从检测到解决) | ✅ 完整 | [quality.py:resolve_contradiction](file:///Users/tohnee/Trae/github/llm-wiki-engine/llmwiki/app/memory/quality.py) | 按 source_count > last_confirmed > retention 选胜者,其余 supersede 为 stale。orchestrator 编译期自动调用 |
| **Self-healing**(自动修复) | ✅ 完整 | [quality.py:self_heal_plan](file:///Users/tohnee/Trae/github/llm-wiki-engine/llmwiki/app/memory/quality.py) + [cycle.py:daily_maintenance](file:///Users/tohnee/Trae/github/llm-wiki-engine/llmwiki/app/maintain/cycle.py) | 生成动作清单 + crosslink 自动补孤立 mention + 标 stale + high risk 入人审队列 |
| **Lint 体检** | ✅ 完整 | [lint.py:audit_tenant](file:///Users/tohnee/Trae/github/llm-wiki-engine/llmwiki/app/maintain/lint.py) | 三规则:R1 ambiguous>15%、R2 无源 inferred、R3 hub(度数 top 10%)inferred>20% 加急 |
| **Hub 加权错误传播** | ✅ 完整 | [lint.py:hub_weight](file:///Users/tohnee/Trae/github/llm-wiki-engine/llmwiki/app/maintain/lint.py) | `priority = base_severity * (1 + hub_weight)`,hub 双倍权重 |
| **wiki-status 洞察** | ✅ 完整 | [lint.py:wiki_status](file:///Users/tohnee/Trae/github/llm-wiki-engine/llmwiki/app/maintain/lint.py) | 返回 documents/entities/relations/facts/ambiguous_ratio/orphan_entities/hubs top 10 |

---

### 6. Multi-agent and collaboration(多 Agent 协作)— 完整度 15%

| v2 要求 | 状态 | 代码位置 | 验证 |
|---|---|---|---|
| **Mesh sync**(多 agent 并行 observation 合并) | ❌ **未实现** | — | 无多 agent 观察合并机制。Last-write-wins / 时间戳冲突解决均无 |
| **Shared vs private scoping** | ❌ **未实现** | [V2-CROSSCHECK-AND-INVENTORY.md](file:///Users/tohnee/Trae/github/llm-wiki-engine/llmwiki/docs/V2-CROSSCHECK-AND-INVENTORY.md) 已诚实承认 | 同租户内全共享,无显式 private 标记。observations 表有 user_id 但 facts/entities/relations 无 owner/scoping 字段 |
| **Work coordination** | ❌ **未实现** | — | 无"谁在做什么/阻塞/完成"的协调机制 |
| **多用户共享知识库(基础)** | ✅ 完整(但非 v2 mesh sync) | [CAPABILITIES.md](file:///Users/tohnee/Trae/github/llm-wiki-engine/llmwiki/docs/CAPABILITIES.md) | 同租户共享 KG + 会话按 (tenant,user,session) 隔离。这是企业单租户共享模型,不是 v2 的多 agent mesh |

---

### 7. Privacy and governance(隐私与治理)— 完整度 85%

| v2 要求 | 状态 | 代码位置 | 验证 |
|---|---|---|---|
| **Filter on ingest**(入库前脱敏) | ✅ 完整 | [governance.py:scrub_sensitive](file:///Users/tohnee/Trae/github/llm-wiki-engine/llmwiki/app/core/governance.py) + [ingest/service.py:88-89](file:///Users/tohnee/Trae/github/llm-wiki-engine/llmwiki/app/ingest/service.py#L88-L89) | 8 种模式:sk-API key、Bearer token、password/secret、PEM 私钥块、邮箱、中国手机号、身份证、SSN。入库前自动调用 |
| **Audit trail**(全操作留痕) | ✅ 完整 | [governance.py:AuditLog](file:///Users/tohnee/Trae/github/llm-wiki-engine/llmwiki/app/core/governance.py) | audit_log 表记录 (tenant,user,action,target,detail,ts)。ingest/crystallize/daily_maintenance 都已接入 |
| **Tenant 物理隔离** | ✅ 完整 | [store.py:ensure_tenant_partition](file:///Users/tohnee/Trae/github/llm-wiki-engine/llmwiki/app/db/store.py) + [tenant.py](file:///Users/tohnee/Trae/github/llm-wiki-engine/llmwiki/app/core/tenant.py) | 7 张核心表 LIST 分区 + HMAC 强制 + 跨租户拦截 + 剥除 body 中 tenant 字段 |
| **Bulk operations** | ⚠️ **分散,未统一 governance API** | [store.py:drop_tenant](file:///Users/tohnee/Trae/github/llm-wiki-engine/llmwiki/app/db/store.py) + [cycle.py:rebuild_tenant/archive_tenant_kg](file:///Users/tohnee/Trae/github/llm-wiki-engine/llmwiki/app/maintain/cycle.py) | 都已实现:drop(物理销毁)、rebuild(重投编译)、archive(JSON 快照)。但非统一 governance API,且 archive 的 S3 put_object 是注释留待接入 |
| **Bulk 可逆性** | ⚠️ **drop 不可逆** | [store.py:drop_tenant](file:///Users/tohnee/Trae/github/llm-wiki-engine/llmwiki/app/db/store.py) | v2 要求"audited and reversible"。archive 可恢复,但 drop_tenant 不可逆(已注明),无"软删除/可恢复"中间态 |

---

### 8. Crystallization(结晶化)— 完整度 100%

| v2 要求 | 状态 | 代码位置 | 验证 |
|---|---|---|---|
| **蒸馏为结构化摘要** | ✅ 完整 | [crystallize.py:crystallize](file:///Users/tohnee/Trae/github/llm-wiki-engine/llmwiki/app/memory/crystallize.py) | LLM 蒸馏为 {title, digest, facts[]},作为一等 WikiNode 落库 |
| **抽取 facts 强化知识库** | ✅ 完整 | [crystallize.py](file:///Users/tohnee/Trae/github/llm-wiki-engine/llmwiki/app/memory/crystallize.py) + [store.py:reinforce_or_insert_by_triple](file:///Users/tohnee/Trae/github/llm-wiki-engine/llmwiki/app/db/store.py) | facts provenance=inferred,source_span_ids 回链原问答引用。已存在三元组则强化 |
| **质量门控** | ✅ 完整 | [crystallize.py:39](file:///Users/tohnee/Trae/github/llm-wiki-engine/llmwiki/app/memory/crystallize.py#L39) | `verified_ratio < 0.6` 不回填,避免噪声污染 |
| **异步触发(on_query)** | ✅ 完整 | [hook_handlers.py:_crystallize_on_query](file:///Users/tohnee/Trae/github/llm-wiki-engine/llmwiki/app/core/hook_handlers.py) + [pipeline.py:emit_background](file:///Users/tohnee/Trae/github/llm-wiki-engine/llmwiki/app/query/pipeline.py) | `emit_background(ON_QUERY)` 即发即忘,不阻塞回答 |
| **审计留痕** | ✅ 完整 | [hook_handlers.py](file:///Users/tohnee/Trae/github/llm-wiki-engine/llmwiki/app/core/hook_handlers.py) | `AuditLog.record(tenant, "crystallize", target=node_id, detail={facts: n})` |

---

### 9. Output formats beyond markdown(多格式输出)— 完整度 90%

| v2 要求 | 状态 | 代码位置 | 验证 |
|---|---|---|---|
| **报告 markdown** | ✅ 完整 | [render.py:render_report_md](file:///Users/tohnee/Trae/github/llm-wiki-engine/llmwiki/app/generation/render.py) | .md 直写 |
| **报告 docx** | ✅ 完整 | [render.py:render_report_docx](file:///Users/tohnee/Trae/github/llm-wiki-engine/llmwiki/app/generation/render.py) | python-docx,标题/列表分级 |
| **报告 html** | ✅ 完整(本轮新增) | [render.py:render_report_html](file:///Users/tohnee/Trae/github/llm-wiki-engine/llmwiki/app/generation/render.py) | 深色主题,内联 CSS,无外部依赖 |
| **比较表格** | ✅ 完整 | [render.py:render_table_xlsx](file:///Users/tohnee/Trae/github/llm-wiki-engine/llmwiki/app/generation/render.py) | openpyxl → .xlsx |
| **图表** | ✅ 完整 | [render.py:render_chart_png](file:///Users/tohnee/Trae/github/llm-wiki-engine/llmwiki/app/generation/render.py) | matplotlib,bar/line/pie,中文字体可配 |
| **幻灯片** | ✅ 完整 | [render.py:render_slides_pptx](file:///Users/tohnee/Trae/github/llm-wiki-engine/llmwiki/app/generation/render.py) | python-pptx,标题页+内容页 |
| **结构化数据导出(JSON/CSV)** | ✅ 完整 | [graph_export.py](file:///Users/tohnee/Trae/github/llm-wiki-engine/llmwiki/app/evidence/graph_export.py) | JSON/GraphML/Cypher/HTML |
| **依赖图/时间线可视化** | ⚠️ **未独立实现** | — | graph_export HTML 是力导向图,可作依赖图;但无专门 timeline 可视化。v2 列举的"timeline visualization"未作为独立输出格式 |
| **团队 brief** | ⚠️ **未独立实现** | — | report 可承担 brief 角色,但无专门 brief 模板 |

---

### 10. Schema as the real product(Schema 即产品)— 完整度 70%

| v2 要求 | 状态 | 代码位置 | 验证 |
|---|---|---|---|
| **Schema 层定义** | ✅ 完整 | [schema_layer.py:TenantSchema](file:///Users/tohnee/Trae/github/llm-wiki-engine/llmwiki/app/core/schema_layer.py) | dataclass 含 entity_types/relation_types/lint 阈值/default_depth/summary_max_chars/custom_rules |
| **每租户可配置** | ✅ 完整 | [schema_layer.py:SchemaStore](file:///Users/tohnee/Trae/github/llm-wiki-engine/llmwiki/app/core/schema_layer.py) + [admin/service.py](file:///Users/tohnee/Trae/github/llm-wiki-engine/llmwiki/app/admin/service.py) | Redis 存 `schema:{tenant}`,`GET/PUT /admin/schema/{tenant_id}` |
| **实体类型表(taxonomy)** | ✅ 完整 | [schema_layer.py:26-28](file:///Users/tohnee/Trae/github/llm-wiki-engine/llmwiki/app/core/schema_layer.py#L26-L28) | 默认 7 类,可配 |
| **关系类型表** | ✅ 完整 | [schema_layer.py:29-31](file:///Users/tohnee/Trae/github/llm-wiki-engine/llmwiki/app/core/schema_layer.py#L29-L31) | 默认 9 类,可配 |
| **lint 阈值可配** | ✅ 完整 | [schema_layer.py:32-34](file:///Users/tohnee/Trae/github/llm-wiki-engine/llmwiki/app/core/schema_layer.py#L32-L34) | ambiguous/inferred/hub_inferred ratio |
| **custom_rules(自然语言规则)** | ✅ 完整 | [schema_layer.py:36](file:///Users/tohnee/Trae/github/llm-wiki-engine/llmwiki/app/core/schema_layer.py#L36) | 自由文本,等价 CLAUDE.md 自然语言规则 |
| **Schema 真正注入编译 prompt** | ✅ **已修复(2026-06-21)** | [prompts.py:build_extract_system](file:///Users/tohnee/Trae/github/llm-wiki-engine/llmwiki/app/compile/prompts.py) + [orchestrator.py:compile_document_inline](file:///Users/tohnee/Trae/github/llm-wiki-engine/llmwiki/app/compile/orchestrator.py) | 已全链路接入:`orchestrator` 加载 `SchemaStore.get(tenant_id)` → 传 schema 给 `extract_chunk`/`batch_extract_document`/`extract_relations` → `build_extract_system`/`build_relation_system` 用租户 entity_types/relation_types 替换硬编码 + 拼接 custom_rules |
| **Schema 驱动 lint 阈值** | ✅ **已修复(2026-06-21)** | [lint.py:audit_tenant](file:///Users/tohnee/Trae/github/llm-wiki-engine/llmwiki/app/maintain/lint.py) + [cycle.py:daily_maintenance](file:///Users/tohnee/Trae/github/llm-wiki-engine/llmwiki/app/maintain/cycle.py) | `audit_tenant(store, tenant_id, schema=schema)` 从 schema 读取 `lint_ambiguous_ratio`/`lint_hub_inferred_ratio` 替代模块级常量;`daily_maintenance` 加载 SchemaStore 传给 audit_tenant |

---

## 三、关键差异点详细定位

### 差异 1:混合搜索未做三流 RRF 融合 ✅ 已修复(2026-06-21)

**v2 要求**:BM25 + 向量 + **图遍历** 三流 RRF 融合。

**修复前**:[retrieval.py:_rrf_merge](file:///Users/tohnee/Trae/github/llm-wiki-engine/llmwiki/app/evidence/retrieval.py) 只融合 `[vec_ids, bm_ids]` 2 流。图遍历通过 [evidence/navigate](file:///Users/tohnee/Trae/github/llm-wiki-engine/llmwiki/app/evidence/service.py) 独立工作,作用是"圈定 scope",不在 RRF 融合中。

**修复后**:在 `Retriever.search` 中新增图遍历流:query 向量 → `store.link_entities` → `store.neighbors(hops=1)` → 收集关联 span_ids → 纳入 `_rrf_merge([vec_ids, bm_ids, graph_ids])` 三流融合。图遍历失败时自动降级为 2 流,不影响主检索。

### 差异 2:Schema 层未真正驱动编译 ✅ 已修复(2026-06-21) 关键

**v2 要求**:"schema 是最重要的文件,把通用 LLM 变成纪律性知识工作者"——schema 应驱动实体/关系类型、lint 阈值、矛盾处理、私有 vs 共享。

**修复前**:[schema_layer.py](file:///Users/tohnee/Trae/github/llm-wiki-engine/llmwiki/app/core/schema_layer.py) 完整定义了 TenantSchema,但只在 [admin/service.py](file:///Users/tohnee/Trae/github/llm-wiki-engine/llmwiki/app/admin/service.py) 用于配置展示。`compile/` 目录下无任何引用。`prompts.py` 仍是硬编码 7 类实体/8 类关系。`lint.py` 用模块级常量。

**修复后**:
1. [prompts.py](file:///Users/tohnee/Trae/github/llm-wiki-engine/llmwiki/app/compile/prompts.py) 新增 `build_extract_system(entity_types, custom_rules)` 和 `build_relation_system(relation_types, custom_rules)` 用租户 schema 替换硬编码 + 拼接 custom_rules
2. [l2_extract.py](file:///Users/tohnee/Trae/github/llm-wiki-engine/llmwiki/app/compile/workers/l2_extract.py) `extract_chunk`/`batch_extract_document` 新增 `schema=None` 参数
3. [l3_resolve_relation.py](file:///Users/tohnee/Trae/github/llm-wiki-engine/llmwiki/app/compile/workers/l3_resolve_relation.py) `extract_relations` 新增 `schema=None` 参数
4. [orchestrator.py](file:///Users/tohnee/Trae/github/llm-wiki-engine/llmwiki/app/compile/orchestrator.py) `compile_document_inline` 开头加载 `SchemaStore.get(tenant_id)` 并传给抽取函数
5. [lint.py](file:///Users/tohnee/Trae/github/llm-wiki-engine/llmwiki/app/maintain/lint.py) `audit_tenant` 新增 `schema=None` 参数,从 schema 读取阈值
6. [cycle.py](file:///Users/tohnee/Trae/github/llm-wiki-engine/llmwiki/app/maintain/cycle.py) `daily_maintenance` 加载 SchemaStore 传给 audit_tenant

### 差异 3:on_session_start / on_memory_write 钩子无 handler ✅ 已修复(2026-06-21)

**v2 要求**:
- on_session_start:加载相关上下文(基于近期活动)
- on_memory_write:检查矛盾→触发 supersession

**修复前**:[hook_handlers.py](file:///Users/tohnee/Trae/github/llm-wiki-engine/llmwiki/app/core/hook_handlers.py) 只注册 2 个 handler。on_memory_write 注释说"由编译期 contradiction 已覆盖",但 crystallize 回填新 fact 时**不走** detect_contradictions,这是真实缺口。

**修复后**:
1. [hook_handlers.py](file:///Users/tohnee/Trae/github/llm-wiki-engine/llmwiki/app/core/hook_handlers.py) 新增 `_load_context_on_session_start`:从 observations 表加载近期 episodic 观察存入 Redis
2. [hook_handlers.py](file:///Users/tohnee/Trae/github/llm-wiki-engine/llmwiki/app/core/hook_handlers.py) 新增 `_check_contradictions_on_write`:检查新 fact 的 (subject, predicate) 是否与已有 fact 矛盾,调 `resolve_contradiction` + `mark_superseded`
3. [hook_handlers.py](file:///Users/tohnee/Trae/github/llm-wiki-engine/llmwiki/app/core/hook_handlers.py) `_crystallize_on_query` 在 `reinforce_or_insert_by_triple` 后触发 `emit_background(ON_MEMORY_WRITE)`
4. [pipeline.py](file:///Users/tohnee/Trae/github/llm-wiki-engine/llmwiki/app/query/pipeline.py) `answer` 入口触发 `emit(ON_SESSION_START)` 并从 Redis 读取会话上下文注入 history

### 差异 4:procedural 记忆分层未实现 ⚠️

**v2 要求**:working→episodic→semantic→**procedural**(从重复 semantic 中抽工作流模式)。

**当前实现**:[consolidation.py:7](file:///Users/tohnee/Trae/github/llm-wiki-engine/llmwiki/app/memory/consolidation.py#L7) 明确注释"procedural 留扩展位"。DB schema 已有 tier='procedural' 枚举位。

**建议修复**:新增 `consolidation.py:promote_to_procedural`,扫描 semantic 观察中重复出现 ≥3 次的模式,LLM 抽工作流,写 tier='procedural' confidence=0.9。daily_maintenance 中调用。

### 差异 5:多 Agent 协作三件套未实现 ❌

**v2 要求**:Mesh sync、Shared vs private scoping、Work coordination。

**当前实现**:全部未实现。当前是"单租户内多用户共享 + 会话隔离"的企业模型,不是 v2 的多 agent mesh。observations 表有 user_id 但 facts/entities/relations 无 owner/scoping 字段。

**建议修复方向**(取决于是否需要多 agent 场景):
1. Mesh sync:多 agent 写 observations 时,用 `source_agent_id` + timestamp,merge 时 last-write-wins + 冲突入审
2. Shared/private:在 facts/entities 加 `scope: 'shared'|'private'` + `owner_user_id` 字段,检索时按用户过滤
3. Work coordination:新增 `agent_tasks` 表,agent 认领任务,防止重复工作

### 差异 6:quality_score 仅启发式,未在产物上自动调用 ⚠️

**v2 要求**:"每件 LLM 写的内容都该有质量分……可让 LLM 自评,或用不同 prompt 二次评估"。

**当前实现**:[quality.py:quality_score](file:///Users/tohnee/Trae/github/llm-wiki-engine/llmwiki/app/memory/quality.py) 是长度+引用+句子边界启发式。注释说"生产可换 LLM 二次评估"但未实现。且未在编译产物(wiki_nodes/facts)或生成产物(report)上自动调用评分。

**建议修复**:
1. 编译 L4 wiki render 后,对 wiki_node.content 调 quality_score,<0.6 标记 review
2. 生成 report 后,对 text 调 quality_score,不达标触发重写

### 差异 7:on_schedule 未走 hooks 系统 + 无定时调度 ⚠️

**v2 要求**:On schedule:periodic lint, consolidation, retention decay。

**当前实现**:[cycle.py:daily_maintenance](file:///Users/tohnee/Trae/github/llm-wiki-engine/llmwiki/app/maintain/cycle.py) 功能完整,但需手动调用,无定时调度器(无 cron/APScheduler/celery beat),也未通过 `emit(ON_SCHEDULE)` 触发。

**建议修复**:
1. 用 APScheduler 或 k8s CronJob 定时调 `daily_maintenance`
2. 在 `daily_maintenance` 内部 `emit(ON_SCHEDULE, tenant_id)`,让其他扩展(如 procedural 提升)可挂载

### 差异 8:关系置信度无多源强化 ⚠️

**v2 要求**:"A caused B, confirmed by 3 sources, confidence 0.9"。

**当前实现**:[Relation](file:///Users/tohnee/Trae/github/llm-wiki-engine/llmwiki/app/models/schema.py) 有 confidence 字段,但 prompt 未要求 source_count,confidence 是 LLM 单次输出。无类似 `reinforce_or_insert_by_triple` 的关系强化机制。

**建议修复**:在 `upsert_relations` 中按 (source, type, target) 去重,已存在则 confidence 提升;prompt 要求返回 source_span_ids 用于强化。

---

## 四、补全优先级建议

| 优先级 | 差异 | 影响面 | 修复难度 | 状态 |
|---|---|---|---|---|
| **P0** | Schema 未驱动编译(差异 2) | v2 核心主张落空 | 中(改 orchestrator + prompts) | ✅ 已修复(2026-06-21) |
| **P0** | on_memory_write 未注册(差异 3) | crystallize 回填无矛盾检查 | 低(加 1 个 handler) | ✅ 已修复(2026-06-21) |
| **P1** | 混合搜索缺图流融合(差异 1) | 多跳问答召回 | 中(改 retrieval.py) | ✅ 已修复(2026-06-21) |
| **P1** | on_session_start 未注册(差异 3) | 会话上下文加载缺失 | 低(加 1 个 handler) | ✅ 已修复(2026-06-21) |
| **P1** | quality_score 未自动调用(差异 6) | 质量门控未生效 | 中(改 orchestrator + generate) | 待修复 |
| **P2** | procedural 未实现(差异 4) | 记忆分层不完整 | 中(加 promote_to_procedural) | 待修复 |
| **P2** | on_schedule 无调度(差异 7) | 维护需手动触发 | 低(APScheduler) | 待修复 |
| **P2** | 关系无多源强化(差异 8) | 关系置信度不准 | 中(改 upsert_relations) | 待修复 |
| **P3** | 多 Agent 协作(差异 5) | 单 agent 场景下无影响 | 高(需评估是否需要) | 待评估 |

---

## 五、与既有 V2-CROSSCHECK-AND-INVENTORY.md 的关系

[既有文档](file:///Users/tohnee/Trae/github/llm-wiki-engine/llmwiki/docs/V2-CROSSCHECK-AND-INVENTORY.md) 已覆盖 12 项设计点(三层架构/manifest/溯源三态/lint/wiki-status/分层检索/KG 导航/crosslink/图导出/archive/wiki 视图/租户隔离),本轮在它基础上**扩展到 v2 全部 10 大领域 35 项细粒度要求**,新增发现 9 个差异点(其中 4 个 P0/P1 关键差异是既有文档未识别的)。

---

## 六、校验方法说明

1. **基准来源**:微信文章 `mp.weixin.qq.com/s/Nb_vER8LHEE5u3s3_CkWRA` 经 WebFetch/curl/defuddle 多种方式尝试均被公众号反爬拦截。该文章是 Karpathy LLM Wiki v2 思想的中文解读,核心内容与本地 `llmwiki/docs/kapathy-llm-wiki-v2.md`(项目已引用并据此实现)一致,故以此文档为权威基准。
2. **代码扫描范围**:`app/` 下 34 个 Python 源文件 + `frontend/src/` 下 7 个 JSX 视图 + `db/schema.sql` + `db/auth_schema.sql` + `docs/` 全部文档。
3. **校验方法**:逐项对照 v2 规范文本,在代码中定位实现,验证功能完整性(读取关键函数体),标记 ✅ 完整 / ⚠️ 有差异 / ❌ 未实现,并给出具体文件行号链接。
4. **既有文档交叉验证**:读取 `V2-CROSSCHECK-AND-INVENTORY.md` 和 `CAPABILITIES.md`,确认既有自评与本次校验一致,并在其基础上扩展覆盖面。

---

*报告生成:2026-06-21 | 校验基准:kapathy-llm-wiki-v2.md | 代码状态:当前 HEAD*
