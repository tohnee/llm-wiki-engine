// LLM-Wiki Mock Backend - data + mock answer
export const DB = {
  users: new Map([['demo@llmwiki.test', { user_id: 'u_demo', password: 'demo', tenant_id: 'demo', role: 'admin' }]]),
  tenants: new Map([['demo', { tenant_id: 'demo', name: 'Demo Tenant', active: true }]]),
  schemas: new Map([['demo', {
    tenant_id: 'demo',
    entity_types: ['org','person','product','project','location','time','concept'],
    relation_types: ['works_for','owns','develops','depends_on','references','belongs_to','part_of','causes'],
    lint_ambiguous_ratio: 0.15, lint_inferred_ratio: 0.4, lint_hub_inferred_ratio: 0.2,
    default_depth: 'D1', summary_max_chars: 200, custom_rules: '',
  }]]),
  documents: [
    { document_id: 'doc_demo_001', title: '示例:Karpathy LLM Wiki v2 设计原则.md', status: 'queryable_full', depth: 'D2', page_count: 8, created_at: new Date().toISOString() },
    { document_id: 'doc_demo_002', title: '示例:技术决策记录(ADR).md', status: 'queryable_full', depth: 'D1', page_count: 4, created_at: new Date().toISOString() },
    { document_id: 'doc_demo_003', title: '示例:Q1 项目复盘.md', status: 'queryable_coarse', depth: 'D1', page_count: 12, created_at: new Date().toISOString() },
    { document_id: 'doc_demo_004', title: '示例:多租户安全架构白皮书.md', status: 'parsing', depth: 'D2', page_count: 0, created_at: new Date().toISOString() },
  ],
  graph: {
    nodes: [
      { id: 'en_llm_wiki', name: 'LLM-Wiki Engine', type: 'product', degree: 8 },
      { id: 'en_karpathy', name: 'Andrej Karpathy', type: 'person', degree: 3 },
      { id: 'en_anthropic', name: 'Anthropic', type: 'org', degree: 4 },
      { id: 'en_claude', name: 'Claude Sonnet 4.6', type: 'product', degree: 5 },
      { id: 'en_haiku', name: 'Claude Haiku 4.5', type: 'product', degree: 4 },
      { id: 'en_bgem3', name: 'BAAI/bge-m3', type: 'product', degree: 3 },
      { id: 'en_postgres', name: 'PostgreSQL + pgvector', type: 'product', degree: 6 },
      { id: 'en_redis', name: 'Redis Streams', type: 'product', degree: 4 },
      { id: 'en_compile', name: '编译期 DAG', type: 'concept', degree: 7 },
      { id: 'en_query', name: '查询期 Pipeline', type: 'concept', degree: 6 },
      { id: 'en_memory', name: 'Memory Lifecycle', type: 'concept', degree: 5 },
      { id: 'en_v2', name: 'V2 三层架构', type: 'concept', degree: 4 },
    ],
    edges: [
      { source: 'en_llm_wiki', target: 'en_karpathy',  relation_type: 'references', confidence: 0.95 },
      { source: 'en_llm_wiki', target: 'en_anthropic', relation_type: 'depends_on', confidence: 0.92 },
      { source: 'en_llm_wiki', target: 'en_claude',    relation_type: 'depends_on', confidence: 0.98 },
      { source: 'en_llm_wiki', target: 'en_haiku',     relation_type: 'depends_on', confidence: 0.98 },
      { source: 'en_llm_wiki', target: 'en_bgem3',     relation_type: 'depends_on', confidence: 0.85 },
      { source: 'en_llm_wiki', target: 'en_postgres',  relation_type: 'depends_on', confidence: 0.99 },
      { source: 'en_llm_wiki', target: 'en_redis',     relation_type: 'depends_on', confidence: 0.95 },
      { source: 'en_anthropic', target: 'en_claude',   relation_type: 'develops',   confidence: 1.0 },
      { source: 'en_anthropic', target: 'en_haiku',    relation_type: 'develops',   confidence: 1.0 },
      { source: 'en_compile', target: 'en_postgres',   relation_type: 'depends_on', confidence: 0.95 },
      { source: 'en_compile', target: 'en_redis',      relation_type: 'depends_on', confidence: 0.95 },
      { source: 'en_compile', target: 'en_haiku',      relation_type: 'depends_on', confidence: 0.9 },
      { source: 'en_compile', target: 'en_claude',     relation_type: 'depends_on', confidence: 0.9 },
      { source: 'en_query',   target: 'en_postgres',   relation_type: 'depends_on', confidence: 0.95 },
      { source: 'en_query',   target: 'en_claude',     relation_type: 'depends_on', confidence: 0.9 },
      { source: 'en_memory',  target: 'en_v2',         relation_type: 'part_of',    confidence: 0.85 },
      { source: 'en_v2',      target: 'en_karpathy',   relation_type: 'references', confidence: 0.9 },
    ],
  },
  status: {
    tenant: 'demo', documents: 4, entities: 12, relations: 17, facts: 32,
    chunks: 45, spans: 218, ambiguous_ratio: 0.08, orphan_entities: 1,
    hubs: [
      { entity_id: 'en_llm_wiki', name: 'LLM-Wiki Engine', degree: 8 },
      { entity_id: 'en_compile', name: '编译期 DAG', degree: 7 },
      { entity_id: 'en_postgres', name: 'PostgreSQL + pgvector', degree: 6 },
    ],
  },
};

export function mockAnswer(question) {
  const q = (question || '').toLowerCase();
  if (q.includes('架构') || q.includes('设计') || q.includes('architecture')) {
    return {
      answer: 'LLM-Wiki Engine 采用 Knowledge Compiler + 证据落地 的两层架构:\n\n1. 编译期(L0→L4): 解析 → chunk/span → fact/entity → 关系 → wiki\n2. 查询期: Router 分流 → Fast/Agentic QA → Verify 校验\n\n两层不变量:**导航层可有损,证据层必须无损** — 一切 citation 落到 (doc_id, span_id) 原文。[doc_demo_001:sp_a1b2]',
      verified_ratio: 0.95, escalated: false,
      citations: [
        { document_id: 'doc_demo_001', span_id: 'sp_a1b2', content: '本系统采用两层架构,导航层与证据层分离。' },
        { document_id: 'doc_demo_001', span_id: 'sp_c3d4', content: '编译期 L0→L4 五阶段流水线,无状态 worker 并行。' },
      ],
    };
  }
  if (q.includes('记忆') || q.includes('memory')) {
    return {
      answer: 'Memory Lifecycle 4 个分层:\n- working: 当前会话原始观察\n- episodic: 会话结束压缩(2-3 条要点)\n- semantic: 跨会话稳定结论(≥5 条触发归并)\n- procedural: 从 ≥8 条 semantic 识别工作流\n\n伴随 Ebbinghaus 衰减 + 多源置信 + 矛盾检测 + supersession。[doc_demo_001:sp_e5f6]',
      verified_ratio: 0.92, escalated: false,
      citations: [{ document_id: 'doc_demo_001', span_id: 'sp_e5f6', content: 'Memory v2 分层: working/episodic/semantic/procedural' }],
    };
  }
  if (q.includes('安全') || q.includes('租户') || q.includes('security')) {
    return {
      answer: '安全三道闸门:\n1. JWT 鉴权(tenant_id only from token)\n2. HMAC 内部签名跨服务防伪造\n3. Postgres LIST 分区物理隔离 + 服务端 ACL\n\n生产 security_guard 校验占位密钥/默认 DSN,违反直接 exit(78)。[doc_demo_004:sp_g7h8]',
      verified_ratio: 0.96, escalated: false,
      citations: [{ document_id: 'doc_demo_004', span_id: 'sp_g7h8', content: '三道闸门: JWT + HMAC + LIST 分区' }],
    };
  }
  if (q.includes('检索') || q.includes('search') || q.includes('rag')) {
    return {
      answer: '混合检索三流 RRF 融合:\n1. BM25 (Postgres tsvector)\n2. 向量 (pgvector HNSW, bge-m3 1024 维)\n3. 图遍历 (link_entities → neighbors → 收集 span_ids)\n\n三流 RRF 融合 → cross-encoder rerank → top-8 进生成。[doc_demo_002:sp_i9j0]',
      verified_ratio: 0.93, escalated: false,
      citations: [{ document_id: 'doc_demo_002', span_id: 'sp_i9j0', content: '混合检索: BM25 + 向量 + 图遍历' }],
    };
  }
  return {
    answer: `这是 Mock 后端模拟回答。你问的是: "${question || '(空)'}"。\n\n要触发不同的预设答案,试试问以下话题:\n- "架构 / 设计" — 系统两层架构\n- "记忆 / memory" — Memory Lifecycle 4 分层\n- "安全 / 租户" — 三道安全闸门\n- "检索 / search" — 混合检索三流 RRF\n\n本演示无真实 LLM,所有回答均为静态模板。要体验真实问答,请按 LOCAL-DEPLOYMENT-GUIDE.md 本地部署。[doc_demo_001:sp_x0y0]`,
    verified_ratio: 0.8, escalated: false,
    citations: [{ document_id: 'doc_demo_001', span_id: 'sp_x0y0', content: 'Mock 后端默认响应' }],
  };
}
