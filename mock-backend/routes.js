// Mock backend routes (dispatch table)
import { DB, mockAnswer } from './db.js';

function issueJWT(tenant_id, user_id, role = 'member') {
  const p = { tenant_id, sub: user_id, role, iat: Math.floor(Date.now()/1000), exp: Math.floor(Date.now()/1000)+3600 };
  return 'mockjwt.' + Buffer.from(JSON.stringify(p)).toString('base64url') + '.sig';
}

export const ROUTES = [
  // health
  { method: 'GET', path: '/', handler: (req, res, _, __, send) => send(res, 200, {
    service: 'llmwiki-mock-backend', version: '1.0.0',
    message: 'Mock 后端运行中。所有数据均为模拟,用于本地预览前端 UI。',
    docs: 'https://github.com/tohnee/llm-wiki-engine',
  }) },
  { method: 'GET', path: '/api/health', handler: (_, res, __, ___, send) => send(res, 200, { ok: true, mock: true }) },
  { method: 'GET', path: '/health',     handler: (_, res, __, ___, send) => send(res, 200, { ok: true, mock: true }) },
  { method: 'GET', path: '/metrics',    handler: (_, res, __, ___, send) =>
    send(res, 200, '# HELP llmwiki_mock_up Mock backend up\n# TYPE llmwiki_mock_up gauge\nllmwiki_mock_up 1\n',
      { 'Content-Type': 'text/plain; version=0.0.4' }) },

  // auth: 任何邮箱+密码都允许登录(便于演示)
  { method: 'POST', path: '/api/admin/auth/login', handler: async (req, res, _, body, send) => {
    const email = (body.email || 'guest@demo').trim();
    const u = DB.users.get(email) || { user_id: email.split('@')[0] || 'guest', tenant_id: 'demo', role: 'admin' };
    send(res, 200, {
      access_token: issueJWT(u.tenant_id, u.user_id, u.role),
      tenant_id: u.tenant_id, user_id: u.user_id, role: u.role,
    });
  }},

  // admin
  { method: 'POST', path: '/api/admin/admin/tenants', handler: async (req, res, _, b, send) => {
    if (!b.tenant_id) return send(res, 400, { detail: 'tenant_id required' });
    DB.tenants.set(b.tenant_id, { tenant_id: b.tenant_id, name: b.name || b.tenant_id, active: true });
    send(res, 200, { ok: true, tenant_id: b.tenant_id });
  }},
  { method: 'POST', path: '/api/admin/admin/users', handler: async (req, res, _, b, send) => {
    if (!b.email || !b.tenant_id) return send(res, 400, { detail: 'email + tenant_id required' });
    DB.users.set(b.email, {
      user_id: b.user_id || b.email.split('@')[0],
      password: b.password || 'demo',
      tenant_id: b.tenant_id, role: b.role || 'member',
    });
    send(res, 200, { ok: true, email: b.email });
  }},
  { method: 'GET', path: '/api/admin/admin/schema/:tenant', handler: (_, res, p, __, send) => {
    const s = DB.schemas.get(p.tenant);
    if (!s) return send(res, 404, { detail: 'schema not found' });
    send(res, 200, s);
  }},
  { method: 'PUT', path: '/api/admin/admin/schema/:tenant', handler: async (req, res, p, b, send) => {
    const old = DB.schemas.get(p.tenant) || { tenant_id: p.tenant };
    DB.schemas.set(p.tenant, { ...old, ...b, tenant_id: p.tenant });
    send(res, 200, { ok: true, tenant_id: p.tenant });
  }},

  // ingest
  { method: 'POST', path: '/api/ingest/ingest', handler: async (req, res, _, b, send) => {
    const id = 'doc_' + Date.now().toString(36) + Math.random().toString(36).slice(2, 8);
    DB.documents.unshift({
      document_id: id, title: b.title || 'untitled.md', status: 'queued',
      depth: b.depth || 'D1', page_count: 0, created_at: new Date().toISOString(),
    });
    // 模拟编译进度
    setTimeout(() => {
      const d = DB.documents.find(x => x.document_id === id);
      if (d) { d.status = 'queryable_coarse'; d.page_count = 5; }
    }, 3000);
    setTimeout(() => {
      const d = DB.documents.find(x => x.document_id === id);
      if (d) { d.status = 'queryable_full'; d.page_count = 7; }
    }, 8000);
    send(res, 200, { document_id: id, status: 'queued', depth: b.depth || 'D1' });
  }},
  { method: 'GET', path: '/api/ingest/documents', handler: (_, res, __, ___, send) => send(res, 200, DB.documents) },
  { method: 'GET', path: '/api/ingest/documents/:id/status', handler: (_, res, p, __, send) => {
    const d = DB.documents.find(x => x.document_id === p.id);
    if (!d) return send(res, 404, { detail: 'document not found' });
    send(res, 200, { status: d.status, depth: d.depth, page_count: d.page_count });
  }},

  // query
  { method: 'POST', path: '/api/query/ask', handler: async (req, res, _, b, send) => {
    await new Promise(r => setTimeout(r, 300));  // 模拟延迟
    send(res, 200, mockAnswer(b.question));
  }},
  { method: 'GET', path: '/api/query/graph',  handler: (_, res, __, ___, send) => send(res, 200, DB.graph) },
  { method: 'GET', path: '/api/query/status', handler: (_, res, __, ___, send) => send(res, 200, DB.status) },

  // generation
  { method: 'POST', path: '/api/gen/generate', handler: async (req, res, _, b, send) => {
    await new Promise(r => setTimeout(r, 400));
    send(res, 200, {
      artifact_id: 'art_' + Date.now().toString(36),
      artifact_type: b.artifact_type || 'report',
      content: `# ${b.instruction || '示例报告'}\n\n## 概述\n\n这是 Mock 后端生成的示例 ${b.artifact_type || 'report'},仅用于 UI 预览。\n\n## 关键发现\n\n- 系统采用两层架构,导航层与证据层分离 [doc_demo_001:sp_a1b2]\n- Memory v2 引入 procedural 分层 [doc_demo_001:sp_e5f6]\n- 混合检索三流 RRF 融合 [doc_demo_002:sp_i9j0]\n\n## 建议\n\n请按 LOCAL-DEPLOYMENT-GUIDE.md 本地部署后体验真实生成能力。`,
      citations: [
        { document_id: 'doc_demo_001', span_id: 'sp_a1b2' },
        { document_id: 'doc_demo_001', span_id: 'sp_e5f6' },
        { document_id: 'doc_demo_002', span_id: 'sp_i9j0' },
      ],
    });
  }},
  { method: 'POST', path: '/api/gen/generate/file', handler: async (req, res, _, b, send) => {
    await new Promise(r => setTimeout(r, 500));
    const ext = ({ report: 'docx', table: 'xlsx', chart: 'png', slides: 'pptx' })[b.artifact_type] || 'txt';
    send(res, 200, {
      file_path: `/tmp/llmwiki-generated/mock_${Date.now()}.${ext}`,
      filename: `${b.artifact_type || 'report'}_demo.${ext}`,
      size_bytes: 12345,
      message: 'Mock 后端不实际生成文件,仅返回 metadata。',
    });
  }},
];
