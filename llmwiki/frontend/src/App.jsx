import React, { useState } from "react";
import { auth, IS_DEMO } from "./api.js";
import Login from "./views/Login.jsx";
import Documents from "./views/Documents.jsx";
import Graph from "./views/Graph.jsx";
import Ask from "./views/Ask.jsx";
import Generate from "./views/Generate.jsx";
import Health from "./views/Health.jsx";
import Admin from "./views/Admin.jsx";

/* ----- 内嵌精简 SVG 图标(stroke 1.6,与 Claude/OpenAI 风格一致)----- */
const Icon = ({ d, size = 18 }) => (
  <svg className="nav-icon" viewBox="0 0 24 24" width={size} height={size}
       fill="none" stroke="currentColor" strokeWidth="1.6"
       strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    {d}
  </svg>
);
const IconDoc = () => <Icon d={<><path d="M14 3H6a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V9z"/><path d="M14 3v6h6"/><path d="M9 13h6M9 17h6M9 9h2"/></>} />;
const IconGraph = () => <Icon d={<><circle cx="6" cy="6" r="2.4"/><circle cx="18" cy="6" r="2.4"/><circle cx="6" cy="18" r="2.4"/><circle cx="18" cy="18" r="2.4"/><circle cx="12" cy="12" r="2.4"/><path d="M8.1 7.4l2.5 3M15.9 7.4l-2.5 3M8.1 16.6l2.5-3M15.9 16.6l-2.5-3"/></>} />;
const IconAsk = () => <Icon d={<><path d="M21 11.5a8.4 8.4 0 0 1-13.5 6.8L3 19l1-3.7a8.4 8.4 0 1 1 17-3.8z"/></>} />;
const IconGen = () => <Icon d={<><path d="M12 20l9-9-3-3-9 9-1.5 4.5z"/><path d="M14 5l5 5"/></>} />;
const IconHealth = () => <Icon d={<><path d="M3 12h4l3-8 4 16 3-8h4"/></>} />;
const IconAdmin = () => <Icon d={<><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.6 1.6 0 0 0 .3 1.8l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.6 1.6 0 0 0-1.8-.3 1.6 1.6 0 0 0-1 1.5V21a2 2 0 1 1-4 0v-.1a1.6 1.6 0 0 0-1-1.5 1.6 1.6 0 0 0-1.8.3l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1a1.6 1.6 0 0 0 .3-1.8 1.6 1.6 0 0 0-1.5-1H3a2 2 0 1 1 0-4h.1a1.6 1.6 0 0 0 1.5-1 1.6 1.6 0 0 0-.3-1.8l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1a1.6 1.6 0 0 0 1.8.3h.1a1.6 1.6 0 0 0 1-1.5V3a2 2 0 1 1 4 0v.1a1.6 1.6 0 0 0 1 1.5 1.6 1.6 0 0 0 1.8-.3l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1a1.6 1.6 0 0 0-.3 1.8v.1a1.6 1.6 0 0 0 1.5 1H21a2 2 0 1 1 0 4h-.1a1.6 1.6 0 0 0-1.5 1z"/></>} />;
const IconLogout = () => <Icon d={<><path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"/><path d="M16 17l5-5-5-5"/><path d="M21 12H9"/></>} />;

const NAV_GROUPS = [
  {
    title: "工作台",
    items: [
      { id: "documents", label: "文档",   desc: "入库与编译 (D0 / D1 / D2)",         comp: Documents, Icon: IconDoc },
      { id: "ask",       label: "问答",   desc: "基于证据的多跳问答,引用回链原文",    comp: Ask,       Icon: IconAsk },
      { id: "generate",  label: "生成",   desc: "报告 · 表格 · 图表 · 幻灯片",        comp: Generate,  Icon: IconGen },
    ],
  },
  {
    title: "洞察",
    items: [
      { id: "graph",  label: "知识图谱", desc: "3D 交互式实体与关系图谱",  comp: Graph,  Icon: IconGraph },
      { id: "health", label: "健康",     desc: "知识库洞察与溯源审计",     comp: Health, Icon: IconHealth },
    ],
  },
  {
    title: "管理",
    items: [
      { id: "admin", label: "管理", desc: "租户与用户(平台管理员)", comp: Admin, Icon: IconAdmin },
    ],
  },
];

// flatten,方便按 id 查找
const NAV_FLAT = NAV_GROUPS.flatMap(g => g.items);

function DemoBanner() {
  return (
    <div className="demo-banner">
      <b>🎬 Demo 模式</b> · 这是 GitHub Pages 上的纯前端预览,后端 API 未连接。
      <a href="https://github.com/tohnee/llm-wiki-engine#%E6%9C%AC%E5%9C%B0%E9%83%A8%E7%BD%B2"
         target="_blank" rel="noreferrer"> 查看本地部署指南 →</a>
    </div>
  );
}

export default function App() {
  // Demo 模式: 自动注入 mock user
  const [authed, setAuthed] = useState(!!auth.token || IS_DEMO);
  const [view, setView] = useState("documents");

  if (IS_DEMO && !auth.user) {
    auth.user = { tenant_id: "demo", user_id: "guest" };
  }

  if (!authed) return <Login onLogin={() => setAuthed(true)} />;

  const active = NAV_FLAT.find((n) => n.id === view);
  const View = active.comp;
  const userInitial = (auth.user?.user_id || "?").slice(0, 1).toUpperCase();

  return (
    <div className="shell">
      <aside className="sidebar">
        <div className="brand">
          <div className="brand-mark">W</div>
          <div>
            <div className="brand-name">LLM-Wiki</div>
            <div className="brand-sub">Knowledge Engine</div>
          </div>
        </div>

        <nav className="nav">
          {NAV_GROUPS.map((g, gi) => (
            <React.Fragment key={g.title}>
              <div className="nav-section-title">{g.title}</div>
              {g.items.map((n) => (
                <button key={n.id}
                  className={`nav-item ${view === n.id ? "active" : ""}`}
                  onClick={() => setView(n.id)}
                  aria-current={view === n.id ? "page" : undefined}>
                  <n.Icon />
                  <span>{n.label}</span>
                </button>
              ))}
            </React.Fragment>
          ))}
        </nav>

        <div className="sidebar-foot">
          <div className="user-chip">
            <div className="user-avatar">{userInitial}</div>
            <div>
              <div><b>{auth.user?.user_id || "—"}</b></div>
              <div className="tenant-tag" style={{ paddingLeft: 0, marginTop: 0 }}>租户 · {auth.user?.tenant_id || "—"}</div>
            </div>
          </div>
          <button className="logout-btn" onClick={() => { auth.logout(); setAuthed(false); }}>
            <IconLogout /> <span>退出登录</span>
          </button>
        </div>
      </aside>

      <main className="main">
        {IS_DEMO && <DemoBanner />}
        <div className="topbar">
          <h1>{active.label}</h1>
          <span className="desc">{active.desc}</span>
        </div>
        <div className="content"><View /></div>
      </main>
    </div>
  );
}
