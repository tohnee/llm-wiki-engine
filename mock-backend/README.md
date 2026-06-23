# LLM-Wiki Mock Backend

零依赖的 Mock 后端,用纯 Node.js 内置 `http` 模块实现,覆盖前端 (`llmwiki/frontend/src/api.js`) 的所有 API 路径。用于本地预览 UI 而无需启动完整 docker-compose 栈。

## 启动

```bash
# 仓库根目录
./start.sh mock                      # Unix/macOS
start.bat mock                       # Windows

# 或直接进本目录
node server.js                       # 默认端口 8000
PORT=8888 node server.js             # 换端口
```

## 配套前端启动

```bash
cd llmwiki/frontend
npm install   # 首次
npm run dev   # http://localhost:5173
```

前端的 `vite.config.js` 已把 `/api/*` 全部代理到 `localhost:8000-8004`,Mock 后端监听 `:8000` 即可接管前端所有调用(其他端口的请求会通过 query 网关同样路由到 :8000)。

## 文件结构

| 文件 | 作用 |
|------|------|
| `server.js` | HTTP server + 路由分发 + 日志 |
| `routes.js` | 14 个 API 路由定义 |
| `db.js`     | 内存数据(用户/租户/文档/图谱/状态)+ mockAnswer 答案生成器 |
| `package.json` | ESM 配置,无 npm 依赖 |

## 已覆盖 API

| Method | Path | 说明 |
|--------|------|------|
| GET    | `/api/health` `/health` `/` | 健康检查 + 服务信息 |
| GET    | `/metrics` | Prometheus 占位指标 |
| POST   | `/api/admin/auth/login` | 登录(任何邮箱+密码均可,返回 mock JWT) |
| POST   | `/api/admin/admin/tenants` | 建租户 |
| POST   | `/api/admin/admin/users` | 建用户 |
| GET    | `/api/admin/admin/schema/:tenant` | 读 schema |
| PUT    | `/api/admin/admin/schema/:tenant` | 改 schema |
| POST   | `/api/ingest/ingest` | 入库(3s 后 coarse,8s 后 full,模拟编译进度) |
| GET    | `/api/ingest/documents` | 文档列表 |
| GET    | `/api/ingest/documents/:id/status` | 文档状态 |
| POST   | `/api/query/ask` | 问答(根据问题关键词返回不同预设答案) |
| GET    | `/api/query/graph` | 知识图谱(12 节点 + 17 边) |
| GET    | `/api/query/status` | 健康洞察 |
| POST   | `/api/gen/generate` | 生成结构化内容 |
| POST   | `/api/gen/generate/file` | 生成文件(返回 metadata) |

## 问答触发关键词

试着问以下话题,会触发不同预设答案:
- "**架构** / **设计**" — 系统两层架构
- "**记忆** / **memory**" — Memory Lifecycle 4 分层
- "**安全** / **租户**" — 三道安全闸门
- "**检索** / **search**" — 混合检索三流 RRF

其他问题会返回默认引导文案 + 上面 4 个关键词提示。

## 与真实后端的区别

| 行为 | 真实后端 | Mock 后端 |
|------|----------|-----------|
| LLM 调用 | 真调 Anthropic/OpenAI 兼容 API | 静态模板回答 |
| 编译 | L0→L4 完整 DAG | 仅 setTimeout 切换状态字段 |
| 向量检索 | pgvector HNSW + BM25 + 图遍历 | 无 |
| 鉴权 | JWT + HMAC + 物理分区 | 任意凭证通过 |
| 数据持久 | Postgres + Redis + S3 | 内存 Map(重启清空) |
| Verify | NLI 引用蕴含校验 | 总是 `verified_ratio: 0.8~0.96` |

## 何时不要用 Mock 后端

- 评估真实问答准确度
- 评估编译/检索性能
- 测试租户安全隔离
- 任何与"真实 API 凭证 / 真实数据"相关的验证

→ 这些场景请按 [`LOCAL-DEPLOYMENT-GUIDE.md`](../LOCAL-DEPLOYMENT-GUIDE.md) 起完整 docker-compose 栈。
