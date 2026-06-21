import React, { useState } from "react";
import { api, auth } from "../api.js";

export default function Login({ onLogin }) {
  const [email, setEmail] = useState("");
  const [pw, setPw] = useState("");
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);

  async function submit() {
    setErr(""); setBusy(true);
    try {
      const data = await api.login(email, pw);
      auth.save(data);
      onLogin();
    } catch (e) { setErr(e.message); } finally { setBusy(false); }
  }

  return (
    <div className="auth-wrap">
      <div className="card auth-card">
        <div className="brand">
          <div className="brand-mark">W</div>
          <div>
            <div className="brand-name">LLM-Wiki</div>
            <div className="brand-sub">KNOWLEDGE ENGINE</div>
          </div>
        </div>
        <label className="label">邮箱</label>
        <input className="input" value={email} onChange={(e) => setEmail(e.target.value)}
          placeholder="you@company.com" onKeyDown={(e) => e.key === "Enter" && submit()} />
        <div style={{ height: 12 }} />
        <label className="label">密码</label>
        <input className="input" type="password" value={pw} onChange={(e) => setPw(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && submit()} />
        {err && <div style={{ color: "var(--prov-ambiguous)", fontSize: 12.5, marginTop: 10 }}>{err}</div>}
        <div style={{ height: 18 }} />
        <button className="btn" style={{ width: "100%" }} onClick={submit} disabled={busy}>
          {busy ? "登录中…" : "登录"}
        </button>
        <div className="muted" style={{ marginTop: 14, textAlign: "center" }}>
          租户与账号由管理员创建
        </div>
      </div>
    </div>
  );
}
