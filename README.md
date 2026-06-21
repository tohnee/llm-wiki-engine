# LLM-Wiki 企业级知识引擎

> Knowledge Compiler + 证据落地的多租户知识库问答系统。

## 项目结构

```
llmwiki/
├── app/                  # 后端服务(Python / FastAPI)
│   ├── core/             # 配置 / 鉴权 / 钩子 / schema 层
│   ├── db/               # Postgres 存储 + DDL
│   ├── llm/              # LLM 网关 + 向量/rerank
│   ├── compile/          # 编译 DAG(L0→L4)
│   ├── evidence/         # 证据检索(6 只读工具)
│   ├── query/            # 查询网关 + QA pipeline
│   ├── maintain/         # 维护循环(decay/lint/crosslink)
│   ├── memory/           # 记忆生命周期(置信/遗忘/结晶/巩固)
│   └── models/           # 数据模型
├── frontend/             # React 前端(Vite)
│   └── src/
│       ├── views/        # 7 个功能视图
│       └── components/   # Citation / GraphCanvas
├── deploy/               # docker-compose + K8s manifests
│   ├── docker-compose.yml
│   └── k8s/
├── docs/                 # 设计文档 / 对比报告
├── tests/                # 冒烟 / e2e / 单元测试
├── scripts/              # 工具脚本(ingest_demo / issue_jwt)
├── Dockerfile
├── Makefile
└── requirements.txt
```

## 快速开始

详细文档见 [`llmwiki/README.md`](llmwiki/README.md)。

```bash
# 起本地全栈
cd llmwiki && make up

# 离线冒烟测试(无需 DB/API)
cd llmwiki && make smoke
```

## 文档索引

| 文档 | 说明 |
|---|---|
| [`llmwiki/README.md`](llmwiki/README.md) | 完整架构与代码地图 |
| [`llmwiki/docs/DEPLOYMENT-READINESS.md`](llmwiki/docs/DEPLOYMENT-READINESS.md) | 部署就绪检查 |
| [`llmwiki/docs/V2-FULL-CROSSCHECK-REPORT.md`](llmwiki/docs/V2-FULL-CROSSCHECK-REPORT.md) | V2 规范对比校验报告 |
| [`llmwiki/docs/CAPABILITIES.md`](llmwiki/docs/CAPABILITIES.md) | 能力清单 |

## 许可

仅用于研究与学习。
