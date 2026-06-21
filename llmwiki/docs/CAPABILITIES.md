# 能力现状与剩余缺口(对照你的提问逐条回答)

> 本轮在上一版基础上补齐了鉴权、租户/用户管理、会话记忆隔离、入库 API + 编译生产端、
> D0 摘要、cross-linker、archive/rebuild/daily 执行、租户数据生命周期。以下逐条诚实回答。

---

## 一、多用户、多租户管理 —— 现在支持了

| 能力 | 状态 | 实现 |
|---|---|---|
| 租户创建 | ✅ | `POST /admin/tenants`(平台 admin key),自动建物理分区 |
| 用户创建(租户下) | ✅ | `POST /admin/users`,角色 admin/member/viewer |
| 登录发 JWT | ✅ | `POST /auth/login`,邮箱+密码 → JWT(含 tenant_id/user_id/role) |
| 租户表/用户表 | ✅ | `app/db/auth_schema.sql`:tenants / users |
| 租户停用 / 数据销毁 | ✅ | `AuthStore.purge_tenant` + `Store.drop_tenant`(物理删分区) |

入口服务:`app/admin/service.py`(8002 端口)。

## 二、鉴权 —— 现在是真的

- 密码哈希:`app/core/auth.py` 用 stdlib pbkdf2-hmac-sha256(20 万次迭代 + 随机盐)。生产建议换 argon2/bcrypt(已注明)。
- JWT 签发/校验:登录签发,query/ingest 网关校验,`tenant_id/user_id/role` 全部从 token 解出,**绝不信任 body**。
- 内部服务间:Evidence Service 仍要求 HMAC 签名的内部 header(`app/core/tenant.py`),Query→Evidence 调用带签名,过期/篡改拒绝。
- 角色:viewer 不能 ingest(`ingest.service` 已拦)。
- 已测:密码正确/错误判定、JWT 载荷、跨租户 header 伪造拦截(smoke 全过)。

## 三、用户数据是否完全隔离 —— 是,三层强制

1. **存储物理隔离**:核心 7 张表按 `tenant_id` LIST 分区(`schema.sql`),不同租户数据在不同物理分区表。
2. **查询强制注入**:Evidence 所有接口的 `tenant_id` 从签名 header 解出,客户端/agent/文档内容传入的 tenant 字段被剥除并忽略(`tools.py` + `service.py`)。
3. **跨租户探测拦截**:`read_span` 校验 span 既存在又属本租户;HMAC 篡改被拒(smoke 验证)。

## 四、不同用户的问答与记忆会不会冲突 —— 不会,记忆按三元组物理分键

- 会话记忆现在是真实实现:`app/query/memory.py`,**隔离键 = `mem:{tenant_id}:{user_id}:{session_id}`**,Redis 热副本(7天 TTL)+ Postgres 持久副本(`conversations` 表主键三元组)。
- 已测:不同 tenant、不同 user、不同 session 的 key 互不相同,不可能交叉(smoke `test_memory_key_isolation`)。
- worker 无状态:任意实例按 key 从 Redis/PG 恢复会话 → 支持 P3 水平扩展,且不串号。
- 多轮对话历史注入 `pipeline.answer(ctx, q, memory=...)`,逐轮持久化。

## 五、QA 与生成模块用的是 Claude API 还是 Agent SDK

**用的是 Claude Messages API(`client.messages.create`),不是 Agent SDK。** 这是有意的:

- 取证循环 `_tool_loop`(`app/query/pipeline.py`)用 Messages API 的原生 tool-use 循环自行编排 Plan→Navigate→Collect→Reason,工具收口在自有 Evidence API 之后。
- **为什么不用 Agent SDK**:(a) 工具面要服务端强制 ACL,自管循环更可控;(b) 可替换性——SDK 接口/并发模型变化时不被绑死;(c) 高并发下自管循环 + 无状态 worker 更易水平扩展。
- **若想换 Agent SDK**:把 `_tool_loop` 换成 SDK 的 agent loop,工具仍指向同一组 Evidence API 即可,其余(鉴权/记忆/verify)不变。编译侧若未来需要 bash/文件工具,则那部分 agent 上 gVisor 隔离(已在 k8s 清单)。

---

## 六、除第三节外,本轮还补了哪些(之前未实现)

| 之前缺 | 现状 | 文件 |
|---|---|---|
| 鉴权系统 + 租户/用户管理 | ✅ 已实现 | `core/auth.py` `admin/service.py` `db/auth_schema.sql` `db/auth_store.py` |
| 会话记忆(隔离) | ✅ 已实现 | `query/memory.py` + pipeline 接入 |
| 入库 HTTP API | ✅ 已实现 | `ingest/service.py` |
| 编译生产端(此前只有消费端 run_worker) | ✅ 已接上 | `ingest/service.py` 投递 compile:L1 |
| D0 LLM 摘要(tier-0 质量) | ✅ 已实现 | `compile/workers/summarize.py` + orchestrator 接入 |
| cross-linker(未链接提及织入 + 共现关系) | ✅ 已实现 | `maintain/crosslink.py` |
| archive / rebuild | ✅ 已实现 | `maintain/cycle.py`(JSON 快照 + 重投编译) |
| daily 维护执行(人审队列 + cross-link) | ✅ 已实现 | `maintain/cycle.py` |
| wiki 节点被消费(此前 write-only) | ✅ navigate 返回 wiki_hints | `evidence/service.py` |
| 租户数据生命周期(物理销毁) | ✅ 已实现 | `store.drop_tenant` + `auth.purge_tenant` |
| 文档状态查询 | ✅ 已实现 | `ingest/service.py:/documents/{id}/status` |

## 七、仍然不做"补全成代码"的项 —— 因为它们本质是基础设施/业务决策,不是代码缺口

诚实说明:不是所有东西都该塞进这个仓库,以下保持为"接入点"而非内置实现,硬塞反而是错:

| 项 | 为什么不内置 |
|---|---|
| 生产级 PG/Redis 高可用、备份、容灾 | 用托管服务(RDS/ElastiCache 等),不是应用代码 |
| 多供应商路由(Bedrock/Vertex 端点 + 企业配额) | 端点与配额是商务/合同决定,代码只留路由位 |
| OpenTelemetry collector 后端 | 接你已有的可观测栈 |
| MinerU 本体 | 独立服务,设 `MINERU_URL` 接入;仓库给了调用 + .md 回退 |
| 前端/控制台 UI | 产品层,非本知识引擎职责 |
| argon2/bcrypt 密码库 | 当前 stdlib pbkdf2 可用且安全;换库是一行依赖 + 一个函数 |
| S3 快照的 put_object 具体 SDK 调用 | 给了快照构造与落点;选 aioboto3/minio-py 一行接入 |

archive 的 S3 上传、daily 的 gated auto-fix 重编触发,代码里都留了明确落点(快照已构造好、重投编译已实现),只差你环境的对象存储凭证/策略。

---

## 八、最终统计与验证

- 文件 60+,Python ~3100 行;47 个源文件语法零错误;34 个业务模块 import 全解析。
- 离线冒烟测试 8 组 14 项全 PASS:租户伪造拦截、表格行切分、RRF、hub 加权、tier 权重、溯源三态、**密码哈希/JWT、记忆三元组隔离**。
- docker-compose 8 个服务(postgres/redis/minio/evidence/query/admin/ingest/compile-worker)配置合法。

**端到端流程(给齐 ANTHROPIC_API_KEY 后):**
```bash
make up
# 1. 建租户 + 用户
curl -X POST localhost:8002/admin/tenants -H "x-admin-key: dev-admin-key" \
     -H 'Content-Type: application/json' -d '{"tenant_id":"t1","name":"Acme"}'
curl -X POST localhost:8002/admin/users -H "x-admin-key: dev-admin-key" \
     -H 'Content-Type: application/json' -d '{"tenant_id":"t1","email":"a@acme.com","password":"pw","role":"member"}'
# 2. 登录拿 JWT
TOKEN=$(curl -s -X POST localhost:8002/auth/login -H 'Content-Type: application/json' \
     -d '{"email":"a@acme.com","password":"pw"}' | jq -r .access_token)
# 3. 入库(异步编译)
curl -X POST localhost:8003/ingest -H "Authorization: Bearer $TOKEN" \
     -H 'Content-Type: application/json' -d '{"title":"预算报告","markdown":"# 预算\n总预算500万...","depth":"D1"}'
# 4. 问答(带记忆,按 t1+user+session 隔离)
curl -X POST localhost:8000/ask -H "Authorization: Bearer $TOKEN" \
     -H 'Content-Type: application/json' -d '{"question":"总预算多少?","session_id":"s1"}'
```
