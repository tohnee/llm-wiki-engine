# LLM-Wiki 企业级知识引擎 —— 完整设计与工程落地方案

Knowledge Compiler + 证据落地的多租户知识库问答系统。本仓库是可运行骨架,代码与设计一一对应。

---

## 0. 系统总览

```
                          ┌──────────────────────────────┐
   PDF ─► MinerU ─► MD ─► │ Ingest(鉴权后投递 compile)    │
                          └──────────────┬───────────────┘
                                         │ Redis Streams
        ┌────────────────────────────────▼─────────────────────────────────┐
        │  Compile DAG (无状态 worker, hash 寻址增量, 模型分层 + Batch)        │
        │  L0 parse → L1 chunk/span+embed → L2 fact/entity → L3 resolve/rel  │
        │  → L4 wiki(D2)                                                     │
        └───────────────┬───────────────────────────────┬───────────────────┘
                        │ 写导航层(entity/relation/wiki) │ 写证据层(chunk/span)
                        ▼                                ▼
        ┌──────────────────────────────────────────────────────────────────┐
        │  Storage: Postgres + pgvector(span 向量/BM25) │ Redis │ S3         │
        └───────────────────────────────┬──────────────────────────────────┘
                                         ▲ 只读
        ┌────────────────────────────────┴─────────────────────────────────┐
        │  Evidence Service(6 个只读工具, 服务端强制 tenant 注入)            │
        │  navigate / search / read_span / expand / lookup_entity / get_toc │
        └───────────────────────────────▲──────────────────────────────────┘
                                         │ 工具调用(带内部签名 header)
        ┌────────────────────────────────┴─────────────────────────────────┐
        │  Query Gateway → Router(Haiku) → Fast QA / Agentic QA → Verify    │
        └────────────────────────────────────────────────────────────────────┘
```

**两层不变量(贯穿全系统):**
1. **导航层(Fact/Entity/Relation/Wiki)可有损,证据层(Span)必须无损。** 一切 citation 落到 `(doc_id, span_id)` 原文。KG 解决"答案在哪/如何串多文档",span 取证解决"细节是什么/凭什么可信"——KG 指挥检索,而非取代检索。
2. **tenant_id 由网关从 JWT 解出,经 HMAC 内部 header 传递,服务端强制注入。** agent、文档内容、请求 body 里任何 tenant 字段一律忽略。

---

## 1. 代码地图(源码级对应)

| 模块 | 文件 | 职责 |
|---|---|---|
| 配置 | `app/core/config.py` | 全部可调参数(chunk/span 大小、检索 k、编译深度、prompt 版本) |
| 租户安全 | `app/core/tenant.py` | HMAC 签名/校验,`TenantContext`(已通过伪造拦截测试) |
| 数据模型 | `app/models/schema.py` | Span/Chunk/Fact/Entity/Relation/WikiNode + hash |
| 存储 DDL | `app/db/schema.sql` | Postgres + pgvector,**按 tenant LIST 分区** |
| 存储访问 | `app/db/store.py` | 强制带 tenant 的读写;`ensure_tenant_partition` 自动建分区+索引 |
| LLM 网关 | `app/llm/gateway.py` | 模型分层 + prompt caching + 优先级队列 + token bucket + Batch |
| 向量/rerank | `app/llm/embed.py` | bge-m3 embedding + bge-reranker(可插拔) |
| 编译编排 | `app/compile/dag.py` | Redis Streams 拓扑、消息 schema、完成协调、hash 增量 |
| 编译编排 | `app/compile/orchestrator.py` | L0–L4 串联;inline 版(渐进编译)+ worker 版 |
| L1 | `app/compile/workers/l1_chunk_span.py` | 章节切分 + span 切分(表格行独立)+ embedding |
| L2 | `app/compile/workers/l2_extract.py` | Fact+Entity 抽取(Haiku,共享缓存前缀,带 span 回链) |
| L3 | `app/compile/workers/l3_resolve_relation.py` | Entity Resolution(blocking 4 级)+ Relation 抽取 |
| 编译 prompt | `app/compile/prompts.py` | 抽取/关系/wiki/resolve 提示词(改后 bump 版本触发重编) |
| 溯源+矛盾 | `app/compile/contradiction.py` | extracted/inferred/ambiguous 三态 + 跨源矛盾检测(借自 obsidian-wiki) |
| 依赖 manifest | `app/compile/manifest.py` | 源→派生产物(fact/entity/wiki)依赖,精确失效下游(强化增量) |
| 知识体检 | `app/maintain/lint.py` | 离线 KG 审计 + **hub 加权错误传播优先级**(借自 wiki-lint) |
| 维护循环 | `app/maintain/cycle.py` | archive/rebuild + 每日维护(借自 obsidian-wiki) |
| 分层检索 | `app/evidence/tiered.py` | **tier-0 摘要扫描**(index-only)+ 重要度 tier 加权(借自 wiki-query) |
| 混合检索 | `app/evidence/retrieval.py` | BM25 + 向量 → RRF → cross-encoder rerank,scope 收窄 |
| 证据服务 | `app/evidence/service.py` | 6 个只读工具,FastAPI,服务端 tenant 注入 |
| 工具客户端 | `app/query/tools.py` | Anthropic tool schema + HTTP 客户端(剥除注入的 tenant) |
| 查询管线 | `app/query/pipeline.py` | Router + Fast/Agentic tool loop + 升级兜底 |
| 校验 | `app/query/verify.py` | claim 切分 + 引用存在性 + NLI 蕴含校验 |
| 查询网关 | `app/query/gateway.py` | JWT 鉴权对外入口 |
| 评测 | `app/eval/harness.py` | 分层指标:retrieval recall@k + answer faithfulness,分桶 |
| 部署 | `deploy/docker-compose.yml` `deploy/k8s/*` | 本地一键起 + 编译 worker 的 gVisor 隔离 + KEDA 扩缩 |

---

## 2. 四个核心问题的解法(对应代码)

### 2.1 编译慢 → DAG 并行 + hash 增量 + 模型分层 + Batch + 渐进编译

- **并行 DAG**:`dag.py` 用 Redis Streams,每层 worker 无状态全并行,层间靠 hash 计数器协调(子单元全完成→投递父单元)。300 页文档切 N 个 section 单元,墙钟近似除以并发度。
- **增量**:单元 hash = `sha256(content + prompt_version + model_id)`(`dag.unit_hash`)。`store.existing_chunk_hashes` 跳过未变化 chunk;改 prompt 时 bump `config.prompt_version_*` 触发选择性重编——增量与升级共用一套失效机制。
- **模型分层**:L1/L2 抽取走 Haiku + **Batch API**(`gateway.submit_batch`,成本减半且不占交互配额);L3 关系/L4 wiki 走 Sonnet。
- **prompt caching**:`gateway.complete(cached_prefix=chunk_text)` 把原文标 `cache_control`,同 chunk 的 fact/entity 抽取复用前缀。`gateway.cache_hit_rate` 作为运维指标,目标 ≥70%。
- **分级编译深度**:`CompileDepth.D0/D1/D2`。D0(parse+span+embedding)分钟级让文档 `queryable_coarse`,KG 后台补全;D2 图编译只对高价值文档集开启。

### 2.2 精度低/细节丢失 → 证据层 + navigation-first + agentic 取证 + verify

- **证据层 span(citation 落点)**:`l1_chunk_span.py` 把 chunk(~1200 token)切成 span(~200 token);**表格每行独立成 span 并附表头**(测试已验证),数值/条款细节可精确引用到行。
- **child→parent 扩展**:命中 span 后 `/expand` 取所属 chunk 补上下文,解决"chunk 太大稀释信号 / 太小丢上下文"。
- **navigation-first**:`/navigate` 用 KG 先圈定 `scope_document_ids`,`/search` 在 scope 内做混合检索——不是全库朴素 topK。多跳问题先 `lookup_entity` 拿跨文档 mention。
- **混合检索**:`retrieval.py` BM25(tsvector)+ 向量(pgvector)→ RRF 融合 → cross-encoder rerank(top-50→top-8)。
- **agentic 取证**:`pipeline._tool_loop` 让模型多轮 navigate/search/read_span 直到证据充分(上限 8 轮),多跳/跨文档天然需要 2–4 轮。
- **verify 拦截幻觉**:`verify.py` 逐 claim 校验引用 span 存在性 + NLI 蕴含;不达标的 simple 路径自动升级 Agentic 重答。
- **评测闭环**:`eval/harness.py` 分桶(detail/table/multi_doc/long_doc/summary)分层测 recall@k 与 faithfulness,定位损失发生在检索层还是生成层。

### 2.3 高并发规模化 → 分流 + 无状态 + 网关管控

- **复杂度分流**:`pipeline.route`(Haiku)把 70–85% 流量分到 Fast 路径(Haiku,≤3 轮),复杂问题才走 Sonnet 多轮。
- **Agent SDK 能支撑推广,但工具面收口在自有 Evidence API 之后**:`_tool_loop` 用 Messages API 的 tool loop 直接编排,不强依赖 SDK,可随时替换或退化为自写 loop。SDK 仅承担循环编排时同理替换。
- **无状态 worker**:session 状态外置(messages 可序列化进 Redis/PG),K8s + KEDA 按 stream 深度扩缩(见 `deploy/k8s`)。
- **LLM Gateway**:`gateway.py` 优先级队列 `INTERACTIVE > VERIFY > COMPILE_REALTIME > COMPILE_BATCH` 保证交互永远优先于后台编译;按租户 token bucket;大规模上量加多供应商路由(Anthropic 直连 + Bedrock/Vertex),企业配额与 Anthropic 商务确认后填入容量模型。

### 2.4 多用户隔离 → 数据隔离靠架构,执行隔离看工具面

- **数据隔离(不能等的安全项)**:`tenant.py` HMAC 内部 header,服务端解出 tenant 强制注入;`store.py` 所有查询带 tenant;`schema.sql` 按 tenant **物理 LIST 分区**;`tools.py` 客户端剥除 LLM 注入的 tenant 字段。已通过跨租户伪造拦截测试。
- **执行隔离分级**:
  - **问答 agent 工具面只读(6 个 API)→ 无需 sandbox**,逻辑隔离 + 服务端 ACL 足够。这是仅用 Agent SDK 就能安全跑的部分。
  - **编译/执行类 agent(bash/文件系统)→ 每 job 一个隔离单元**:`deploy/k8s/compile-worker.yaml` 用 `runtimeClassName: gvisor` + readOnlyRootFS + drop ALL caps + 出口白名单 NetworkPolicy + 只挂租户工作目录。内部产品 Docker 够,对外推广建议 gVisor/Firecracker。
- **Prompt injection**:问答路径工具只读 → 注入最坏只是答错,无法越权;编译路径文档内容只进受控 prompt 槽位,不拼进工具参数模板,产物落库前过 schema 校验。

---

## 3. 快速启动

```bash
# 1. 起基础设施 + 服务
export ANTHROPIC_API_KEY=sk-...
docker compose -f deploy/docker-compose.yml up -d

# 2. 编译一篇文档(本地 inline,渐进 D0→D1)
python -m scripts.ingest_demo --tenant t1 --doc doc1 --md ./sample.md --depth D1

# 3. 提问(需先签发 JWT,见 scripts/issue_jwt.py)
curl -X POST localhost:8000/ask \
  -H "Authorization: Bearer $JWT" \
  -H "Content-Type: application/json" \
  -d '{"question":"项目为什么超预算?","session_id":"s1"}'

# 4. 跑评测
python -m app.eval.harness ./golden_qa.jsonl t1
```

golden QA 格式(JSONL):
```json
{"id":"q1","bucket":"multi_doc","question":"项目为什么超预算?","answer":"...","golden_span_ids":["sp_xxx","sp_yyy"]}
```

---

## 4. 12 周落地路线

```
周        1  2  3  4  5  6  7  8  9  10 11 12
P0 评测+安全  ██ ██
P1 编译DAG       ██ ██ ██ ██
P2 取证+精度           ██ ██ ██ ██ ██
P3 规模化                    ██ ██ ██ ██
P4 隔离生产化                      ██ ██ ██ ██
```

- **P0(1–2 周)**:golden QA 集 + `eval/harness.py` 出基线;`Evidence Service` 服务端 tenant filter + 跨租户探测用例进 CI。**唯一不能等的是 tenant filter。**
- **P1(2–5 周)**:落地 `models/schema.py` + `db/*`;`compile/*` DAG + hash 增量 + 模型分层 + Batch + caching;D0 渐进编译。验收:300 页 PDF coarse ≤5 min、缓存命中 ≥70%、小改动只重编受影响单元。
- **P2(4–8 周,与 P1 后半并行)**:五类索引接入 RRF;`/navigate`+`/search` 双层;`_tool_loop` agentic 取证 + `verify.py`;评测驱动迭代。验收:detail recall@8 ≥0.9、multi_doc correctness +20pt、faithfulness ≥0.95、citation 100% 可解引用。
- **P3(7–10 周)**:`pipeline.route` 分流;session 外置;`gateway.py` 优先级队列。验收:Fast P99 <10s、Agentic P99 <60s(2000 并发压测)。
- **P4(9–12 周)**:`deploy/k8s` 编译隔离;注入红队用例;OpenTelemetry trace;租户数据生命周期(分区 drop + S3 清理)。

### 本周三件事
1. golden QA 标注启动(P0)。
2. `tenant.py` + `Evidence Service` tenant 注入 + 跨租户探测用例进 CI(安全急项)。
3. `models/schema.py` 的 Span/Fact(带 source_span_ids)schema 评审(P1 前置)。

---

## 4.5 从 obsidian-wiki 吸收的能力(已核对源码)

obsidian-wiki(Karpathy LLM-Wiki 模式)是单用户本地框架,但有三样企业 KB 同样需要、而我们原先缺失的机制,已嫁接进来(详见 `docs/obsidian-wiki-reflection.md`):

1. **认识论三态溯源 + 矛盾检测**(`compile/contradiction.py`):每条 Fact 标 `extracted`(源文明说)/`inferred`(AI 推断)/`ambiguous`(多源矛盾)。多文档口径冲突时不悄悄选一个,而是显式暴露——这是合同/邮件/纪要交叉问答的关键。
2. **离线知识体检 + hub 加权错误传播**(`maintain/lint.py`):定时扫 KG,ambiguous 比例、无源 inferred、**高度数实体(hub)的 inferred 加急修复**(已测:hub 节点优先级正确高于 peripheral)。错误先修影响面最大的节点。
3. **分层检索 tier-0**(`evidence/tiered.py`):先读 ≤200 字 summary 尝试回答(index-only 模式可强制,并标注"未读正文"),答不了才落 span 检索,并按重要度 tier(core/supporting/peripheral)加权。让查询成本随库规模平坦。

**不照搬的**:它"无需向量库"(百万文档不成立,保留 pgvector,只借便宜层优先思想);它"人确认默认"(改为高风险人审 + 低风险 gated auto-fix);它"wiki 页即答案"(企业细节必须无损,坚持 span 强制引用)。

---

## 5. 这套设计的核心壁垒

1. **Knowledge Compiler** —— 分级编译深度 + Batch/caching 使其成本可控。
2. **证据层 + Verify Engine** —— span 级 ground truth + citation 校验,这是"细节不丢/结论可信"的真正壁垒。
3. **navigation-first 检索** —— KG 指挥检索而非取代,兼得多跳能力与细节精度。
4. **服务端强制隔离 + 执行隔离分级** —— 数据靠架构、执行看工具面,既安全又不给交互流量背沙箱开销。
5. **分层评测闭环** —— 所有精度优化可持续、可定位的前提。

> 一句话:**用编译期构建的知识图谱缩小搜索空间、串起多跳;用查询期的 span 级取证 + 校验保证细节不丢、结论可信。**
