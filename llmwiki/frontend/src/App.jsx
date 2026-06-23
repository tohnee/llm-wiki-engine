import React, { useState } from "react";
import { auth, IS_DEMO } from "./api.js";
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

function DemoBanner() {
  return (
    <div style={{
      background: "linear-gradient(90deg, #fde68a 0%, #fcd34d 100%)",
      color: "#78350f", padding: "10px 16px", fontSize: 13,
      borderBottom: "1px solid #f59e0b", textAlign: "center",
    }}>
      <b>🎬 Demo 模式</b> · 这是 GitHub Pages 上的纯前端预览,后端 API 未连接,
      所有数据展示均为静态/模拟。要真正使用问答能力,请按
      <a href="https://github.com/tohnee/llm-wiki-engine#%E6%9C%AC%E5%9C%B0%E9%83%A8%E7%BD%B2"
         target="_blank" rel="noreferrer" style={{ color: "#7c2d12", textDecoration: "underline" }}>
        本地部署指南
      </a>
      启动 docker-compose 全栈。
    </div>
  );
}

export default function App() {
  // Demo 模式:自动注入一个 mock user 绕过 Login,直接进入 UI 预览
  const [authed, setAuthed] = useState(!!auth.token || IS_DEMO);
  const [view, setView] = useState("documents");

  if (IS_DEMO && !auth.user) {
    // mock 一个用户进 UI;不存 token 避免误调 API
    auth.user = { tenant_id: "demo", user_id: "guest" };
  }

  if (!authed) return <Login onLogin={() => setAuthed(true)} />;

  const active = NAV.find((n) => n.id === view);
  const View = active.comp;

  return (
    <div className="shell">
      {IS_DEMO && <DemoBanner />}
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
