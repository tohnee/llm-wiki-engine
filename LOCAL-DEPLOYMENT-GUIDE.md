# 本地部署模型 API 配置指南

> 适用版本: **v1.0.0+**
> 目标读者: 想在自己的机器/服务器上完整跑通 LLM-Wiki Engine,并使用自己的 API 凭证的开发者
> 与 [`docs/DEPLOYMENT-READINESS.md`](llmwiki/docs/DEPLOYMENT-READINESS.md) 互补:本文聚焦"模型服务"的配置矩阵。

---

## 一、调用位置全景图(代码级精确)

```
┌─────────────── 编译期(后台) ───────────────┐  ┌──── 查询期(交互) ────┐
│ L0 parse      → 可选 MinerU 服务            │  │ Router       → LLM Haiku │
│ L1 chunk+span → Embedding(必填)            │  │ Fast QA      → LLM Haiku │
│ L2 fact/ent   → LLM Haiku (Batch 优先)      │  │ Agentic QA   → LLM Sonnet│
│ L3 relation   → LLM Sonnet                  │  │ Verify NLI   → LLM Haiku │
│ L4 wiki       → LLM Sonnet                  │  │ 检索 query   → Embedding│
│ Crystallize   → LLM Sonnet                  │  │ Rerank(可选) → CrossEnc │
│ Summarize     → LLM Haiku                   │  └─────────────────────────┘
│ Procedural    → LLM Sonnet                  │
└─────────────────────────────────────────────┘
```

**必填**: LLM(Haiku 档 + Sonnet 档) + Embedding(1024 维)
**可选**: Rerank 模型 + MinerU PDF 解析服务

---

## 二、必填 ①:LLM Chat 模型

### 两种 provider 模式

#### A. Anthropic 原生(默认,完整功能)

```env
LLM_PROVIDER=anthropic
ANTHROPIC_API_KEY=sk-ant-...
ANTHROPIC_BASE_URL=                    # 可选,第三方 Anthropic 兼容网关
MODEL_HAIKU=claude-haiku-4-5-20251001  # 高频小调用
MODEL_SONNET=claude-sonnet-4-6         # 深度推理
LLM_TIMEOUT=180
LLM_RETRIES=2
```

**完整支持的高级特性**:
- ✅ **Batch API**: 大文档 L2 抽取(≥30 chunk)自动走 batch,成本减半 + 不占交互配额
- ✅ **Prompt Caching**: 同 chunk 的 fact/entity 抽取复用前缀缓存,目标命中率 ≥70%(在 `/metrics` 看 `llmwiki_llm_cache_hits_total`)
- ✅ **Tool Use**: Agentic QA 多轮 navigate → search → read_span tool loop

#### B. OpenAI 兼容(适合接 GLM/Qwen/DeepSeek/vLLM/Ollama)

```env
LLM_PROVIDER=openai
OPENAI_API_KEY=sk-...
OPENAI_BASE_URL=https://api.deepseek.com/v1   # 或你自己的网关
MODEL_HAIKU=deepseek-chat                      # 小模型档
MODEL_SONNET=deepseek-reasoner                 # 推理档
```

**限制**(代码已显式声明):
- ❌ **Batch API** 不可用 → 大文档走实时(慢且贵)
- ❌ **Prompt Caching** 不可用 → cached_prefix 拼到 system 末尾(等价无缓存)
- ❌ **Anthropic tool_use** 不可用 → Agentic QA 自动降级为 `_direct_search_answer`(单轮检索 + 生成)

### 推荐组合矩阵

| 场景 | LLM_PROVIDER | Haiku 档 | Sonnet 档 | 备注 |
|------|-------------|----------|-----------|------|
| 极致效果(企业) | anthropic | claude-haiku-4-5 | claude-sonnet-4-6 | 全功能 |
| 国内 + 省钱 | openai | deepseek-chat | deepseek-reasoner | 推理档稍贵 |
| 国内 + 阿里 | openai | qwen-turbo-latest | qwen-max-latest | 百炼平台 |
| 国内 + 智谱 | openai | glm-4.5-flash | glm-4.5 | bigmodel.cn |
| 自部署 | openai → vLLM | Qwen2.5-7B-Instruct | Qwen2.5-72B-Instruct | 完全自主 |
| 纯离线开发 | LLM_MOCK=1 | 无 | 无 | 内置规则 mock |

---

## 三、必填 ②:Embedding 模型(1024 维)

### 维度强约束

`schema.sql` 写死 `vector(1024)`,**所有 embedding 必须 1024 维**。换其他维度需要:
1. 改 `schema.sql` 的 `vector(N)` 与 `app/core/config.py::embed_dim`
2. drop 并重建已存在租户的分区(因为 HNSW 索引绑定维度)

### 三种接入方式

#### A. OpenAI 兼容 Embeddings API(推荐 — 无需本地 GPU)

```env
EMBED_API_KEY=sk-...
EMBED_BASE_URL=https://api.siliconflow.cn/v1   # 示例:硅基流动
EMBED_MODEL=BAAI/bge-m3                        # 1024 维
```

**已验证的 1024 维 provider**:
| Provider | base_url | model | 备注 |
|---------|----------|-------|------|
| **硅基流动** | `https://api.siliconflow.cn/v1` | `BAAI/bge-m3` | 国内推荐 |
| **阿里百炼** | `https://dashscope.aliyuncs.com/compatible-mode/v1` | `text-embedding-v3` | 阿里官方 |
| **Cohere** | `https://api.cohere.ai/v1` | `embed-multilingual-v3.0` | 海外,多语优秀 |
| **Jina** | `https://api.jina.ai/v1` | `jina-embeddings-v3` | 长文档强 |
| **自部署 bge-m3** | 你的 vLLM/TEI 地址 | `BAAI/bge-m3` | 私有化 |
| **OpenAI ❌** | `https://api.openai.com/v1` | `text-embedding-3-small` | **1536 维,不兼容** |

#### B. 本地 sentence-transformers(首跑下载约 2.5GB)

不设 `EMBED_API_KEY` 即自动走本地 `BAAI/bge-m3`(需 PyTorch + 4GB 内存)。

#### C. Mock(纯测试)

```env
EMBED_MOCK=1
```
→ 零向量,BM25 仍工作,向量召回失效。适合冒烟测试。

---

## 四、可选:Rerank 模型

**调用点**: `app/llm/embed.py::rerank` → 混合检索 top-50 → top-8 的精排

**当前实现**:
- 仅本地 sentence-transformers `CrossEncoder`(`BAAI/bge-reranker-v2-m3`)
- API 模式下 fallback 为"按 RRF 原始顺序等分"(检索仍可用,精度略降)

**建议**:
- 不想跑本地模型 → 不开 rerank
- 想要 API rerank → 自己加一段 `_rerank_api()`,接 Jina rerank / Cohere rerank API

---

## 五、可选:PDF 解析(MinerU)

```env
MINERU_URL=                            # 留空 → 仅支持 .md/.txt 输入
MINERU_URL=http://your-mineru:8080     # 启用 PDF 解析
```

**替代方案**:
- 自己用 `pymupdf` / `unstructured` 写一段解析器替换 `app/compile/workers/l0_parse.py::stitch()`
- 入库前手工把 PDF 转 markdown(用任何工具)

---

## 六、模型 Mock(开发/CI)

```env
LLM_MOCK=1        # 跳过所有 LLM 调用,内置规则 mock(支持 抽取/路由/NLI/摘要/问答)
EMBED_MOCK=1      # 跳过 embedding,返回零向量
```

**用途**: 无任何 API key 即可跑通端到端流程,验证架构 + 前端联调。

---

## 七、完整 `.env` 模板(可直接用)

```env
# ============ 环境标记(影响生产安全闸门)============
APP_ENV=dev                              # dev / prod / production / staging

# ============ LLM(必填,二选一)============
LLM_PROVIDER=openai
OPENAI_API_KEY=sk-your-key
OPENAI_BASE_URL=https://api.deepseek.com/v1
MODEL_HAIKU=deepseek-chat
MODEL_SONNET=deepseek-reasoner
LLM_TIMEOUT=180
LLM_RETRIES=2

# ---- 或使用 Anthropic 原生 ----
# LLM_PROVIDER=anthropic
# ANTHROPIC_API_KEY=sk-ant-...
# ANTHROPIC_BASE_URL=
# MODEL_HAIKU=claude-haiku-4-5-20251001
# MODEL_SONNET=claude-sonnet-4-6

# ============ Embedding(必填,1024 维)============
EMBED_API_KEY=sk-your-embed-key
EMBED_BASE_URL=https://api.siliconflow.cn/v1
EMBED_MODEL=BAAI/bge-m3

# ============ 基础设施(docker-compose 内置)============
PG_DSN=postgresql://llmwiki:llmwiki@localhost:5432/llmwiki
REDIS_URL=redis://localhost:6379/0
S3_ENDPOINT=http://localhost:9000
S3_BUCKET=llmwiki

# ============ 密钥(生产务必用强随机)============
# 生成: openssl rand -hex 32
INTERNAL_HMAC_SECRET=__GENERATE_WITH_OPENSSL_RAND_HEX_32__
JWT_SECRET=__GENERATE_WITH_OPENSSL_RAND_HEX_32__
PLATFORM_ADMIN_KEY=__GENERATE_WITH_OPENSSL_RAND_HEX_32__

# ============ 服务间地址 ============
EVIDENCE_URL=http://localhost:8001

# ============ 可选 ============
# MINERU_URL=http://localhost:8081      # 启用 PDF 解析
# LLM_MOCK=1                            # 全 mock,无需 API
# EMBED_MOCK=1                          # embedding mock
# SCHEDULE_INTERVAL_SEC=86400           # on_schedule 周期(秒)
# LOG_LEVEL=INFO                        # DEBUG/INFO/WARNING/ERROR
```

---

## 八、最小启动流程

### 8.1 一次性准备
```bash
cd llmwiki
cp .env.example .env
# 编辑 .env 填入 LLM_PROVIDER / OPENAI_API_KEY / EMBED_API_KEY 等

# 生成强随机密钥(生产必须)
echo "INTERNAL_HMAC_SECRET=$(openssl rand -hex 32)" >> .env
echo "JWT_SECRET=$(openssl rand -hex 32)" >> .env
echo "PLATFORM_ADMIN_KEY=$(openssl rand -hex 32)" >> .env
```

### 8.2 启动全栈(7 个容器)
```bash
make up
# 等价于: docker compose -f deploy/docker-compose.yml up -d --build
# 包含:postgres / redis / minio / evidence / query / admin / ingest / compile-worker / scheduler / generation
```

### 8.3 健康检查
```bash
curl http://localhost:8000/health      # query gateway
curl http://localhost:8001/health      # evidence
curl http://localhost:8002/health      # admin
curl http://localhost:8003/health      # ingest
curl http://localhost:8004/health      # generation

# Prometheus 指标
curl http://localhost:8000/metrics | head -20
```

### 8.4 入库 + 问答(端到端验证)
```bash
# 1) 入库一篇 markdown
make ingest TENANT=t1 DOC=d1 MD=./sample.md DEPTH=D1

# 2) 签发 JWT
JWT=$(make jwt TENANT=t1 USER=u1)

# 3) 问答
curl -X POST http://localhost:8000/ask \
  -H "Authorization: Bearer $JWT" \
  -H "Content-Type: application/json" \
  -d '{"question":"项目为什么超预算?","session_id":"s1"}'
```

---

## 九、推荐验证顺序(渐进调试)

| 阶段 | 配置 | 验证目标 |
|------|------|---------|
| 1 | `LLM_MOCK=1 EMBED_MOCK=1 APP_ENV=dev` | docker compose 拉起 / DB schema / API 鉴权链路 OK |
| 2 | 仅开 EMBED API | embedding 维度对齐,向量召回返回非空 |
| 3 | 接入 LLM API(Haiku) | L2 抽取、Router 分流、Fast QA 真实输出 |
| 4 | 加大文档跑 D2(Sonnet) | L3/L4 关系与 wiki 渲染、Agentic QA(若 Anthropic) |
| 5 | `python -m tests.smoke && pytest -m "not integration"` | 34 项纯逻辑测试全 PASS(任何阶段都能跑) |
| 6 | 设 `APP_ENV=prod` 重启 | security_guard 闸门校验占位密钥拒绝放行 |

---

## 十、常见错误诊断

### "[embed] WARNING: model returns dim=1536 but schema expects 1024"
你用了 OpenAI `text-embedding-3-small`(1536 维)。换成 1024 维模型:
- 推荐 `BAAI/bge-m3`(硅基流动 / 阿里百炼 / 自部署)
- 或修改 `schema.sql` + `embed_dim` 后重建表

### "FATAL: 生产环境检测到不安全配置"
你设了 `APP_ENV=prod`(或 production / staging)但 `JWT_SECRET` 仍是占位值。
- 临时:`unset APP_ENV` 或 `APP_ENV=dev`
- 正确:`openssl rand -hex 32` 生成强随机密钥写入 `.env`

### "batch API not supported in OpenAI-compatible mode"
OpenAI 兼容模式不支持 Anthropic Batch API。已自动降级实时调用,无需修复(只是会慢一些)。

### Agentic QA 不进 tool_use 多轮
OpenAI 兼容模式不支持 `tool_use`,已自动降级为单轮检索+生成。要拿到完整 multi-hop 能力请用 Anthropic 原生。

### 文档编译卡在 "queryable_coarse" 状态
L2 抽取失败但 L1 已完成。看 compile-worker 日志:`docker compose logs compile-worker | tail -50`,常见是 LLM API 限流(429) → 提高 `LLM_RETRIES` 或换 provider。

---

## 十一、监控与可观测(v1.0 新增)

每个服务都暴露 `/metrics`,可直接接入 Prometheus / Grafana:

```yaml
# prometheus.yml
scrape_configs:
  - job_name: llmwiki
    static_configs:
      - targets:
        - localhost:8000  # query
        - localhost:8001  # evidence
        - localhost:8002  # admin
        - localhost:8003  # ingest
        - localhost:8004  # generation
```

**关键指标看板**:
- `rate(llmwiki_llm_calls_total[5m])` — LLM 调用速率
- `histogram_quantile(0.99, rate(llmwiki_llm_latency_seconds_bucket[5m]))` — LLM P99 延迟
- `llmwiki_llm_cache_hits_total / llmwiki_llm_calls_total` — prompt cache 命中率(目标 ≥0.7)
- `rate(llmwiki_hook_fires_total{status="error"}[5m])` — 钩子失败率
- `histogram_quantile(0.95, rate(llmwiki_retrieve_latency_seconds_bucket[5m]))` — 检索 P95

**日志**: 全部 JSON 结构化输出,字段 `service / level / msg / ts` + extra,可直接接 Loki / Elasticsearch / 阿里云 SLS。

---

## 十二、成本估算参考(单租户,100 篇 50 页 PDF)

| 阶段 | 模型 | tokens 约 | Anthropic 费用 | DeepSeek 费用 |
|------|------|----------|----------------|---------------|
| L0 parse | (本地或 MinerU) | 0 | $0 | $0 |
| L1 embedding | bge-m3 | 5M | $5(硅基流动 ¥0.5/1M tokens) | $5 |
| L2 抽取(Haiku, Batch) | Haiku-4-5 | 20M | $5(Batch 5 折) | $1 |
| L3/L4 关系+wiki(Sonnet) | Sonnet-4-6 | 5M | $15 | $2 |
| 100 次问答(Haiku Fast) | Haiku-4-5 | 2M | $0.5 | $0.1 |
| 10 次 Agentic(Sonnet) | Sonnet-4-6 | 1M | $3 | $0.5 |
| **合计** | | | **~$28** | **~$8.6** |

> 注:实际成本受文档复杂度、缓存命中率、流量分布影响很大。给个 order-of-magnitude 参考。

---

**最后建议**: 首次部署建议从 `LLM_MOCK=1 EMBED_MOCK=1` 跑通整个 docker-compose 链路后,再逐步换上真实 API,避免 API 错误把架构问题盖住。
