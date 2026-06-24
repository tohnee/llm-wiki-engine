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
      <div className="auth-card">
        <div className="brand">
          <div className="brand-mark">W</div>
          <div>
            <div className="brand-name">LLM-Wiki</div>
            <div className="brand-sub">Knowledge Engine</div>
          </div>
        </div>

        <h1 className="auth-title">登录到工作台</h1>
        <p className="auth-subtitle">使用管理员分配给你的账号继续</p>

        {err && <div className="error-msg">{err}</div>}

        <div className="field">
          <label className="label">邮箱</label>
          <input className="input" type="email" autoComplete="email"
                 value={email} onChange={(e) => setEmail(e.target.value)}
                 placeholder="you@company.com"
                 onKeyDown={(e) => e.key === "Enter" && submit()} />
        </div>

        <div className="field">
          <label className="label">密码</label>
          <input className="input" type="password" autoComplete="current-password"
                 value={pw} onChange={(e) => setPw(e.target.value)}
                 placeholder="••••••••"
                 onKeyDown={(e) => e.key === "Enter" && submit()} />
        </div>

        <button className="btn primary lg" style={{ width: "100%", marginTop: 4 }}
                onClick={submit} disabled={busy || !email || !pw}>
          {busy ? "登录中…" : "登录"}
        </button>

        <div className="auth-foot">租户与账号由平台管理员创建</div>
      </div>
    </div>
  );
}
