// 后端 API 客户端。token 存内存 + localStorage;tenant/user 从登录响应得来。
const TOKEN_KEY = "llmwiki_token";

export const auth = {
  get token() { return localStorage.getItem(TOKEN_KEY) || ""; },
  set token(t) { t ? localStorage.setItem(TOKEN_KEY, t) : localStorage.removeItem(TOKEN_KEY); },
  user: JSON.parse(localStorage.getItem("llmwiki_user") || "null"),
  save(data) {
    this.token = data.access_token;
    const u = { tenant_id: data.tenant_id, user_id: data.user_id };
    localStorage.setItem("llmwiki_user", JSON.stringify(u));
    this.user = u;
  },
  logout() { this.token = ""; localStorage.removeItem("llmwiki_user"); this.user = null; },
};

async function req(path, { method = "GET", body, headers = {}, admin } = {}) {
  const h = { "Content-Type": "application/json", ...headers };
  if (!admin && auth.token) h["Authorization"] = `Bearer ${auth.token}`;
  const res = await fetch(path, { method, headers: h, body: body ? JSON.stringify(body) : undefined });
  if (!res.ok) {
    if (res.status === 401) auth.logout();  // token 过期,自动登出
    let detail = res.statusText;
    try { detail = (await res.json()).detail || detail; } catch {}
    throw new Error(detail);
  }
  return res.json();
}

export const api = {
  // 认证
  login: (email, password) => req("/api/admin/auth/login", { method: "POST", body: { email, password } }),
  // 管理(平台 admin key)
  createTenant: (key, tenant_id, name) =>
    req("/api/admin/admin/tenants", { method: "POST", admin: true, headers: { "x-admin-key": key }, body: { tenant_id, name } }),
  createUser: (key, b) =>
    req("/api/admin/admin/users", { method: "POST", admin: true, headers: { "x-admin-key": key }, body: b }),
  getSchema: (key, t) =>
    req(`/api/admin/admin/schema/${t}`, { admin: true, headers: { "x-admin-key": key } }),
  setSchema: (key, t, body) =>
    req(`/api/admin/admin/schema/${t}`, { method: "PUT", admin: true, headers: { "x-admin-key": key }, body }),
  // 入库
  ingest: (b) => req("/api/ingest/ingest", { method: "POST", body: b }),
  listDocs: () => req("/api/ingest/documents"),
  docStatus: (id) => req(`/api/ingest/documents/${id}/status`),
  // 问答
  ask: (question, session_id) => req("/api/query/ask", { method: "POST", body: { question, session_id } }),
  // 生成
  generate: (b) => req("/api/gen/generate", { method: "POST", body: b }),
  generateFile: (b) => req("/api/gen/generate/file", { method: "POST", body: b }),
  // 图谱 / 健康(经查询网关透传 evidence)
  graph: (fmt = "json") => req(`/api/query/graph?fmt=${fmt}`),
  status: () => req("/api/query/status"),
};
