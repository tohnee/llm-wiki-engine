# V2 设计交叉核对 + 模块能力清单(回答第 1、2 题)

> 说明:用户给的微信文章与 gist 两个链接未能抓取(公众号文章通常不被搜索引擎索引,
> web_fetch 仅允许抓取搜索结果内的 URL)。本核对基于**上一轮已成功抓取并验证的 obsidian-wiki
> 真实仓库**(Karpathy llm-wiki 模式的权威来源)+ 我们自己的 V2.0 架构文档。
> 若两链接有额外主张,请粘贴关键内容,我再补差。

---

## 一、V2 设计逐项交叉核对(已据此补全代码)

| V2 / obsidian-wiki 设计点(已验证) | 现状 | 本轮动作 |
|---|---|---|
| 三层架构:raw / wiki / **schema(规则层)** | raw=span、wiki=wiki_nodes 有;schema 此前硬编码在 prompts+config | ✅ **新增 `core/schema_layer.py`**:每租户可配 taxonomy/关系类型/lint 阈值/自定义规则 + admin 端 get/set |
| 增量编译 manifest(源→派生产物) | `manifest.py` + content_hash | ✅ 已具备 |
| 溯源三态 extracted/inferred/ambiguous + 比例块 | `Provenance` + `Fact.provenance` + `WikiNode.provenance_mix` + `contradiction.py` | ✅ 已具备 |
| wiki-lint:ambiguous>15% / 无源 inferred / hub 加权错误传播 | `maintain/lint.py` | ✅ 已具备 |
| **wiki-status 洞察(hubs/orphans/规模)** | 此前只有 lint hub 度数 | ✅ **新增 `lint.wiki_status` + evidence `/status`** |
| 分层检索 summary→span→full + index-only + tier | `evidence/tiered.py` | ✅ 已具备 |
| tier core/supporting/peripheral | `Tier` enum,tiered + wiki render 用 | ✅ 已具备 |
| KG 导航 + 多跳 | `store.link_entities/neighbors` + `/navigate`(返回 edges)+ `/neighbors` | ✅ 已具备(上一轮) |
| cross-linker(未链接提及织入) | `maintain/crosslink.py` | ✅ 已具备 |
| 图导出 json/graphml/cypher/**html** | 此前缺 html | ✅ **新增 `to_html`(自包含力导向图)+ `/graph/export?fmt=html`** |
| archive + rebuild + daily 维护 | `maintain/cycle.py` | ✅ 已具备 |
| wiki 仅视图、引用落原文 span | 核心不变量 | ✅ 已具备 |

**本轮补全的 3 个 V2 缺口**:① 租户级 schema 规则层(此前唯一缺的"第三层");② wiki-status 洞察;③ HTML 图导出。其余 V2 设计点在前几轮已落地。

---

## 二、模块能力清单(逐条回答)

### 租户管理 — ✅ 具备
`admin/service.py`:`POST /admin/tenants` 建租户(自动建物理分区)、`POST /admin/users` 建用户、`GET/PUT /admin/schema/{tenant}` 管理 schema 层。租户停用 + 物理销毁:`AuthStore.purge_tenant` + `Store.drop_tenant`。

### 租户隔离 — ✅ 三层强制
1. 存储物理隔离:7 张核心表按 `tenant_id` LIST 分区;
2. 查询服务端强制注入 `tenant_id`(HMAC 签名内部 header,忽略 body/agent 传入);
3. 跨租户探测拦截(`read_span` 校验归属;HMAC 篡改拒绝,smoke 已验证)。

### 用户隔离 — ✅(会话/记忆层面)
同租户内用户**共享知识库**(见下),但**会话与记忆按用户隔离**:记忆键 `mem:{tenant}:{user}:{session}`,Redis + PG `conversations` 表主键即三元组。smoke 验证不同 user/不同 session key 不交叉。
> 注:同租户内的**文档级 ACL**(用户 A 不能看用户 B 的文档)目前**未做**——当前模型是"租户内共享"。若需要用户级文档权限,是一个明确的扩展点(在 spans/documents 加 owner/acl 字段 + 检索注入)。

### 会话隔离 — ✅
`query/memory.py`,键含 session_id;每会话独立历史,worker 无状态按键恢复,不串号。

### 多用户共享知识库 — ✅(租户内共享是默认且正确的企业模型)
同一租户下所有用户查询的是同一套已编译知识库(documents/spans/entities/relations/wiki)。这正是企业知识库的预期:**知识共享、对话隔离**。跨租户则完全隔离,不共享。

### 多用户/多租户是用 Claude API 还是 Agent SDK 实现?
**多租户与隔离跟用哪个 SDK 无关**——隔离是**存储分区 + 鉴权 + 服务端 ACL** 的架构问题,在 LLM 调用之外完成。具体到模型调用:**全程用 Claude Messages API**(`anthropic` / `@anthropic-ai/sdk`,见 `llm/gateway.py` 的 `AsyncAnthropic`),**不是 Agent SDK**(`@anthropic-ai/claude-agent-sdk`)。问答取证循环 `_tool_loop`、抽取、生成,都走 Messages API。每次调用都带 `tenant_id` 进 token bucket 限流,但 LLM 本身不感知租户——租户隔离发生在它前面的存储与鉴权层。

---

## 三、模块全景(当前 53 个后端源文件)

| 域 | 模块 | 能力 |
|---|---|---|
| 鉴权/管理 | `core/auth` `admin/service` `db/auth_store` `core/schema_layer` | 租户/用户/角色/schema 层 |
| 隔离 | `core/tenant` `db/store`(分区) | HMAC 注入 + 物理分区 + drop |
| 编译 | `compile/{dag,orchestrator,manifest,contradiction}` `compile/workers/{l0..l4,summarize}` | DAG 并行 / 增量 / Batch / 溯源 / 摘要 |
| 检索取证 | `evidence/{service,retrieval,tiered,graph_export}` | 分层检索 / KG 导航 / neighbors / 图导出 / status |
| 查询 | `query/{gateway,pipeline,tools,verify,memory}` | 路由 / Fast+Agentic / verify / 记忆 / graph+status 透传 |
| 生成 | `generation/{generate,render,service}` | 报告/图表/表格/PPT(Messages API + 确定性渲染) |
| 维护 | `maintain/{lint,crosslink,cycle}` | 体检 / cross-link / archive+daily |
| 入库 | `ingest/service` | HTTP 入库 + 编译生产端 |
| LLM | `llm/{gateway,embed}` | Messages API 网关 / 向量 |

模型调用一律 **Messages API**;隔离一律在其外的存储+鉴权层。
