# LLM-Wiki 部署与测试工程文档

适用于本仓库当前版本(后端 61 源文件 / 前端 12 源文件,离线冒烟 41 项)。

---

## 一、系统拓扑

```
前端(Vite/React :5173)
  │  /api/{query,admin,ingest,gen}  (开发期 vite 代理;生产由 Ingress)
  ▼
┌─────────── 对外服务 ───────────┐   ┌──────── 内部服务 ────────┐
 query  :8000   ask/graph/status    evidence :8001  (HMAC 内部鉴权)
 admin  :8002   租户/用户/schema     compile-worker (消费 Redis Streams)
 ingest :8003   入库→编译生产端
 gen    :8004   报告/图表/表格/PPT
└────────────────────────────────┘   └──────────────────────────┘
        │                  │                    │
        ▼                  ▼                    ▼
   Postgres+pgvector   Redis(Streams/会话/manifest)   S3/MinIO
```

服务间信任:对外服务用 **JWT**;调用 evidence 用 **HMAC 内部签名 header**(`INTERNAL_HMAC_SECRET`)。

---

## 二、前置条件

| 依赖 | 版本 | 说明 |
|---|---|---|
| Docker / Compose | 最新 | 本地全栈 |
| Python | 3.11+ | 本地运行/测试 |
| Node | 18+ | 前端 |
| ANTHROPIC_API_KEY | — | 必填 |
| embedding 模型 | bge-m3 / bge-reranker-v2-m3 | 首次自动下载(数 GB);或换自部署/商用 |
| 中文字体(可选) | Noto Sans CJK SC | 图表渲染中文,设 `CHART_CJK_FONT` |
| MinerU(可选) | — | PDF→MD;不配置则仅支持 .md/.txt |

---

## 三、本地部署(docker-compose)

```bash
cp .env.example .env          # 填 ANTHROPIC_API_KEY,改 INTERNAL_HMAC_SECRET / JWT_SECRET
docker compose -f deploy/docker-compose.yml up -d --build
# 9 个服务:postgres redis minio evidence query admin ingest compile-worker generation
docker compose -f deploy/docker-compose.yml ps
```

Postgres 首次启动自动加载 `schema.sql` + `auth_schema.sql`(documents/chunks/spans/facts/entities/
relations/wiki_nodes + tenants/users/conversations/audit_log/observations)。

前端:
```bash
cd frontend && npm install && npm run dev   # http://localhost:5173
```

---

## 四、初始化与冒烟流程(端到端)

```bash
# 1) 建租户 + 用户(平台 admin key = .env 的 PLATFORM_ADMIN_KEY)
curl -X POST localhost:8002/admin/tenants -H "x-admin-key: dev-admin-key" \
  -H 'Content-Type: application/json' -d '{"tenant_id":"t1","name":"Acme"}'
curl -X POST localhost:8002/admin/users -H "x-admin-key: dev-admin-key" \
  -H 'Content-Type: application/json' \
  -d '{"tenant_id":"t1","email":"a@acme.com","password":"pw","role":"member"}'

# 2) 登录拿 JWT
TOKEN=$(curl -s -X POST localhost:8002/auth/login -H 'Content-Type: application/json' \
  -d '{"email":"a@acme.com","password":"pw"}' | python3 -c 'import sys,json;print(json.load(sys.stdin)["access_token"])')

# 3) 入库(异步编译;含 PII 脱敏 + 审计)
curl -X POST localhost:8003/ingest -H "Authorization: Bearer $TOKEN" \
  -H 'Content-Type: application/json' \
  -d '{"title":"预算报告","markdown":"# 预算\n## 1\n总预算500万元,实际支出620万元。","depth":"D1"}'

# 4) 轮询编译状态(queryable_coarse → queryable_full)
curl localhost:8003/documents/<doc_id>/status -H "Authorization: Bearer $TOKEN"

# 5) 问答(带会话记忆;回答后 on_query 钩子异步结晶回填)
curl -X POST localhost:8000/ask -H "Authorization: Bearer $TOKEN" \
  -H 'Content-Type: application/json' -d '{"question":"为什么超预算?","session_id":"s1"}'

# 6) 生成(报告 docx)
curl -X POST localhost:8004/generate/file -H "Authorization: Bearer $TOKEN" \
  -H 'Content-Type: application/json' -d '{"instruction":"生成超支分析报告","artifact_type":"report"}'

# 7) 图谱 / 健康
curl "localhost:8000/graph?fmt=json" -H "Authorization: Bearer $TOKEN"
curl localhost:8000/status -H "Authorization: Bearer $TOKEN"
```

---

## 五、测试体系

### 5.1 离线冒烟(无需 DB/API,CI 必跑)
```bash
make smoke          # 或 python -m tests.smoke
```
覆盖 41 项纯逻辑断言:租户伪造拦截、chunk/表格行切分、RRF、hub 加权、tier 权重、溯源三态、
密码/JWT、记忆三元组隔离、图导出(graphml/cypher/html)、抽取解析、渲染、schema 层、
**记忆生命周期(衰减/强化/置信)、矛盾解决、PII 脱敏、质量评分**。

### 5.2 前端编译校验
```bash
cd frontend && npx esbuild src/**/*.jsx --bundle --external:react --external:react-dom --outfile=/dev/null
```
11 个 JSX 全部应编译通过。

### 5.3 集成测试(需全栈起来 + API Key)
按第四节 1→7 串行执行,断言:
- 跨租户探测:用 t1 的 JWT 访问 t2 的 doc_id → 401/404(隔离验证)
- 会话隔离:不同 session_id 的记忆互不可见
- 编译增量:同文档重复入库,未变 chunk 不重抽(看 compile-worker 日志)
- 生成证据:报告中 citation 可回链(verified_ratio 非空)

### 5.4 集成测试矩阵

| 用例 | 入口 | 期望 |
|---|---|---|
| 鉴权失败 | 无 token /ask | 401 |
| 跨租户隔离 | t1 token 读 t2 span | 401/404 |
| viewer 限权 | viewer 角色 /ingest | 403 |
| 渐进可问 | 大文档入库后立即问 | D0 即可答(span 检索) |
| 多跳问答 | 跨文档问题 | navigate 扩邻域 + 升级标记 |
| PII 脱敏 | 含 sk-/邮箱的文档 | 库内已脱敏 |
| 结晶回填 | 高质量问答后 | wiki_nodes 新增 + 审计 crystallize |
| 衰减 | daily_maintenance | facts.retention/confidence 下降 |

### 5.5 负载测试(可选)
```bash
# locust/k6 打 /ask,关注 Fast 路径 P50<4s、Agentic P99<60s、各优先级排队时延
```

---

## 六、Kubernetes 部署

```bash
kubectl apply -f deploy/k8s/core-services.yaml      # pg/redis/evidence/query + secret + HPA
kubectl apply -f deploy/k8s/compile-worker.yaml     # gVisor 隔离 + KEDA 按流深扩缩
# admin/ingest/generation 按 core-services 同构补 Deployment(镜像同 llmwiki:latest,改 command/port)
```
要点:`INTERNAL_HMAC_SECRET`/`JWT_SECRET`/`ANTHROPIC_API_KEY` 入 Secret;compile-worker 用
`runtimeClassName: gvisor` + 只读根 + 出口白名单;query 用 HPA 按 CPU/QPS 扩。

---

## 七、运维与排障

| 现象 | 排查 |
|---|---|
| 入库后一直 uploaded | compile-worker 是否在消费 compile:L1;Redis 连通 |
| 问答空答/证据不足 | 文档是否 queryable;embedding 模型是否加载 |
| 图表中文方框 | 装中文字体 + 设 `CHART_CJK_FONT` |
| evidence 401 | `INTERNAL_HMAC_SECRET` 各服务是否一致;header 是否过期(>300s) |
| Batch 编译慢 | 正常(分钟级);D0 已先可问;查 LLM Gateway 优先级队列 |
| 跨租户疑似泄露 | 查分区是否生效;Evidence 是否服务端注入 tenant |

健康检查:各服务 `GET /health`。审计:查 `audit_log` 表。知识健康:`GET /status`。

---

## 八、配置项速查(`.env` / 环境变量)

`ANTHROPIC_API_KEY` `PG_DSN` `REDIS_URL` `S3_ENDPOINT/S3_BUCKET`
`INTERNAL_HMAC_SECRET` `JWT_SECRET` `JWT_TTL_SEC` `PLATFORM_ADMIN_KEY`
`EVIDENCE_URL` `MODEL_HAIKU` `MODEL_SONNET` `MINERU_URL` `CHART_CJK_FONT`
`GENERATION_OUTPUT_DIR`
编译/检索/生命周期参数在 `app/core/config.py` 与 `app/core/schema_layer.py`(后者每租户可配)。
