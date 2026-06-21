import React, { useState } from "react";
import { auth } from "./api.js";
import Login from "./views/Login.jsx";
import Documents from "./views/Documents.jsx";
import Graph from "./views/Graph.jsx";
import Ask from "./views/Ask.jsx";
import Generate from "./views/Generate.jsx";
import Health from "./views/Health.jsx";
import Admin from "./views/Admin.jsx";

const NAV = [
  { id: "documents", label: "文档", glyph: "▤", desc: "入库与编译(D0/D1/D2)", comp: Documents },
  { id: "graph", label: "知识图谱", glyph: "❖", desc: "3D 交互式知识图谱导航", comp: Graph },
  { id: "ask", label: "问答", glyph: "◆", desc: "基于证据的多跳问答,引用可回链原文", comp: Ask },
  { id: "generate", label: "生成", glyph: "✎", desc: "报告 / 图表 / 表格 / 幻灯片", comp: Generate },
  { id: "health", label: "健康", glyph: "◉", desc: "知识库洞察与溯源审计", comp: Health },
  { id: "admin", label: "管理", glyph: "⚙", desc: "租户与用户(平台管理员)", comp: Admin },
];

export default function App() {
  const [authed, setAuthed] = useState(!!auth.token);
  const [view, setView] = useState("documents");

  if (!authed) return <Login onLogin={() => setAuthed(true)} />;

  const active = NAV.find((n) => n.id === view);
  const View = active.comp;

  return (
    <div className="shell">
      <aside className="sidebar">
        <div className="brand">
          <div className="brand-mark">W</div>
          <div>
            <div className="brand-name">LLM-Wiki</div>
            <div className="brand-sub">KNOWLEDGE ENGINE</div>
          </div>
        </div>
        <nav className="nav">
          {NAV.map((n) => (
            <button key={n.id} className={`nav-item ${view === n.id ? "active" : ""}`}
              onClick={() => setView(n.id)}>
              <span className="nav-glyph">{n.glyph}</span>{n.label}
            </button>
          ))}
        </nav>
        <div className="sidebar-foot">
          <div className="user-chip"><b>{auth.user?.user_id || "—"}</b></div>
          <div className="tenant-tag">租户 {auth.user?.tenant_id || "—"}</div>
          <button className="nav-item" style={{ marginTop: 8, color: "var(--ink-3)" }}
            onClick={() => { auth.logout(); setAuthed(false); }}>
            <span className="nav-glyph">⎋</span>退出登录
          </button>
        </div>
      </aside>
      <main className="main">
        <div className="topbar">
          <h1>{active.label}</h1>
          <span className="desc">{active.desc}</span>
        </div>
        <div className="content"><View /></div>
      </main>
    </div>
  );
}
