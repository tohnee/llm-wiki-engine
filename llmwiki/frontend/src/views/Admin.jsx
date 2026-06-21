import React, { useState } from "react";
import { api } from "../api.js";

export default function Admin() {
  const [key, setKey] = useState("");
  const [log, setLog] = useState([]);
  // tenant
  const [tId, setTId] = useState(""); const [tName, setTName] = useState("");
  // user
  const [uTenant, setUTenant] = useState(""); const [uEmail, setUEmail] = useState("");
  const [uPw, setUPw] = useState(""); const [uRole, setURole] = useState("member");

  function note(msg, ok = true) {
    setLog((l) => [{ msg, ok, t: new Date().toLocaleTimeString() }, ...l].slice(0, 8));
  }

  async function createTenant() {
    try { const r = await api.createTenant(key, tId, tName); note(`租户已创建:${r.tenant_id}`); }
    catch (e) { note("租户创建失败:" + e.message, false); }
  }
  async function createUser() {
    try {
      const r = await api.createUser(key, { tenant_id: uTenant, email: uEmail, password: uPw, role: uRole });
      note(`用户已创建:${r.user_id} (${uRole})`);
    } catch (e) { note("用户创建失败:" + e.message, false); }
  }

  return (
    <>
      <div className="card" style={{ marginBottom: 18 }}>
        <label className="label">平台管理密钥(x-admin-key)</label>
        <input className="input" type="password" value={key} onChange={(e) => setKey(e.target.value)}
          placeholder="仅平台管理员持有" />
        <div className="muted" style={{ marginTop: 6 }}>用于创建租户与用户。生产应替换为完整控制台 + RBAC。</div>
      </div>

      <div className="row" style={{ alignItems: "flex-start", gap: 18 }}>
        <div className="card" style={{ flex: 1 }}>
          <div className="title" style={{ fontWeight: 650, marginBottom: 12 }}>创建租户</div>
          <label className="label">租户 ID</label>
          <input className="input" value={tId} onChange={(e) => setTId(e.target.value)} placeholder="acme" />
          <div style={{ height: 10 }} />
          <label className="label">名称</label>
          <input className="input" value={tName} onChange={(e) => setTName(e.target.value)} placeholder="Acme Inc." />
          <div style={{ height: 14 }} />
          <button className="btn" onClick={createTenant} disabled={!key}>创建租户</button>
        </div>

        <div className="card" style={{ flex: 1 }}>
          <div className="title" style={{ fontWeight: 650, marginBottom: 12 }}>创建用户</div>
          <label className="label">所属租户 ID</label>
          <input className="input" value={uTenant} onChange={(e) => setUTenant(e.target.value)} placeholder="acme" />
          <div style={{ height: 10 }} />
          <label className="label">邮箱</label>
          <input className="input" value={uEmail} onChange={(e) => setUEmail(e.target.value)} placeholder="a@acme.com" />
          <div style={{ height: 10 }} />
          <div className="row">
            <div style={{ flex: 1 }}>
              <label className="label">密码</label>
              <input className="input" type="password" value={uPw} onChange={(e) => setUPw(e.target.value)} />
            </div>
            <div style={{ width: 120 }}>
              <label className="label">角色</label>
              <select className="select" value={uRole} onChange={(e) => setURole(e.target.value)}>
                <option value="admin">admin</option>
                <option value="member">member</option>
                <option value="viewer">viewer</option>
              </select>
            </div>
          </div>
          <div style={{ height: 14 }} />
          <button className="btn" onClick={createUser} disabled={!key}>创建用户</button>
        </div>
      </div>

      {log.length > 0 && (
        <div className="card" style={{ marginTop: 18 }}>
          <div className="title" style={{ fontWeight: 650, marginBottom: 8 }}>操作日志</div>
          {log.map((l, i) => (
            <div key={i} style={{ fontSize: 12.5, color: l.ok ? "var(--ink-2)" : "var(--prov-ambiguous)" }}>
              <span className="mono muted">{l.t}</span> · {l.msg}
            </div>
          ))}
        </div>
      )}
    </>
  );
}
