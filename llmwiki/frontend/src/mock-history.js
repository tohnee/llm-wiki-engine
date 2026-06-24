/**
 * 5 条历史对话 Mock(用于验证 Ask 视图在富文本下的布局表现)
 * - 涵盖: 短问短答 / 段落 / 列表 / 代码块 / 表格 / 多 citation / 高度延迟标识
 * - 在 Ask 视图通过"载入演示对话"按钮注入
 */

export const MOCK_HISTORY = [
  // === 1. 短问短答 ===
  { role: "user", text: "项目 Alpha 的负责人是谁?" },
  {
    role: "assistant",
    text: `项目 Alpha 的负责人是 **张三** [doc_demo_001:sp_a1b2]。她同时担任了 Beta 项目的技术顾问。`,
    ratio: 0.92, escalated: false, latency: 3,
  },

  // === 2. 段落 + 多 citation ===
  { role: "user", text: "项目 Alpha 的预算和风险有哪些?" },
  {
    role: "assistant",
    text: `项目 Alpha 的预算为 **2,400 万元**,执行周期 18 个月 [doc_demo_001:sp_b3c4]。主要风险包括:

1. **供应链风险**: 关键零部件依赖单一供应商 [doc_demo_002:sp_d5e6]
2. **人力风险**: 核心团队 3 名工程师属外包,合同 6 月到期 [doc_demo_002:sp_f7g8]
3. **合规风险**: 跨境数据传输尚未完成 GDPR 审查 [doc_demo_003:sp_h9i0]

建议立即启动供应商备份评估与 GDPR 合规咨询。`,
    ratio: 0.88, escalated: true, latency: 12,
  },

  // === 3. 代码块 ===
  { role: "user", text: "示范如何用 SDK 调用问答接口" },
  {
    role: "assistant",
    text: `下面是 Python SDK 的最简用法 [doc_demo_004:sp_j1k2]:

\`\`\`python
from llmwiki import Client

client = Client(api_key="your-key", base_url="http://localhost:8000")
resp = client.ask(
    question="项目 Alpha 的预算是多少?",
    session_id="s_1",
)
print(resp.answer)
print(resp.citations)  # [{document_id, span_id, content}, ...]
\`\`\`

返回的 \`citations\` 数组按相关度排序,前 3 条通常是核心证据 [doc_demo_004:sp_l3m4]。`,
    ratio: 0.95, escalated: false, latency: 5,
  },

  // === 4. 表格 + 简短回答 ===
  { role: "user", text: "对比 D0/D1/D2 三种编译深度" },
  {
    role: "assistant",
    text: `下表对比三种深度的核心差异 [doc_demo_001:sp_n5o6]:

| 深度 | 抽取层级 | 调用模型 | 单文档耗时 | 适用场景 |
|------|---------|----------|----------|----------|
| **D0** | 仅 chunk + span + embedding | 无 LLM | ~5s | 快速可问性验证 |
| **D1** | + fact + entity + 消歧 | Haiku × N | ~30s | 一般问答 |
| **D2** | + relation + wiki + 跨文档 | Sonnet | ~3min | 深度推理 / 知识图谱 |

D2 调用 Sonnet 档,成本约 **D0 的 8-10 倍** [doc_demo_001:sp_p7q8]。如果只是快速验证文档可问性,先用 D0 试试。`,
    ratio: 0.91, escalated: false, latency: 7,
  },

  // === 5. 高延迟 + Agentic 升级 ===
  { role: "user", text: "项目 Alpha 与项目 Beta 的供应商有没有重叠?如果有,会产生什么风险?" },
  {
    role: "assistant",
    text: `经多跳推理 [doc_demo_002:sp_r9s0] [doc_demo_005:sp_t1u2],两个项目共有 **2 家重叠供应商**:

- **供应商 A**(芯片) — 同时为 Alpha 与 Beta 提供 SoC,占两个项目 BOM 成本 23% [doc_demo_005:sp_v3w4]
- **供应商 B**(物流) — 承接两个项目全部跨境运输 [doc_demo_005:sp_x5y6]

> 🚨 这意味着任一供应商断供都会同时阻塞两个产品线,**集中度风险等级:高**。建议在 Q3 前完成至少一个替代供应商认证 [doc_demo_003:sp_z7a8]。

经查证,Alpha 团队已在 6 月启动供应商 A 的双源评估,但 Beta 团队尚未跟进 [doc_demo_002:sp_b9c0]。`,
    ratio: 0.82, escalated: true, latency: 38,
  },
];
