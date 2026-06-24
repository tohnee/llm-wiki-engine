import React, { useState, useEffect } from "react";
import { api } from "../api.js";

const DEPTHS = [
  { v: "D0", label: "D0 快速", desc: "分钟级可问 · span 检索" },
  { v: "D1", label: "D1 标准", desc: "+ 事实 / 实体 / 消歧" },
  { v: "D2", label: "D2 图谱", desc: "+ 关系 / 跨文档 / Wiki" },
];

const STATUS_META = {
  queued: { label: "排队中", className: "" },
  parsing: { label: "解析中", className: "" },
  queryable_coarse: { label: "粗可问", className: "d0" },
  queryable_full: { label: "完整就绪", className: "d1" },
  failed: { label: "失败", className: "danger" },
};

function IconUpload() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor"
         strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><path d="M17 8l-5-5-5 5"/><path d="M12 3v12"/>
    </svg>
  );
}
function IconRefresh() {
  return (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor"
         strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="M23 4v6h-6"/><path d="M1 20v-6h6"/>
      <path d="M3.5 9a9 9 0 0 1 15-3.4l4.5 4.4"/><path d="M20.5 15a9 9 0 0 1-15 3.4L1 14"/>
    </svg>
  );
}

export default function Documents() {
  const [title, setTitle] = useState("");
  const [markdown, setMarkdown] = useState("");
  const [depth, setDepth] = useState("D1");
  const [docs, setDocs] = useState([]);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    api.listDocs().then((list) => {
      if (Array.isArray(list)) setDocs(list);
    }).catch(() => {});
  }, []);

  async function submit() {
    if (!title.trim() || !markdown.trim()) return;
    setBusy(true);
    try {
      const r = await api.ingest({ title, markdown, depth });
      setDocs((d) => [{ document_id: r.document_id, title, depth, status: r.status }, ...d]);
      setTitle(""); setMarkdown("");
    } catch (e) { alert("入库失败: " + e.message); } finally { setBusy(false); }
  }

  function handleFileUpload(e) {
    const file = e.target.files?.[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = (ev) => {
      setMarkdown(ev.target.result);
      if (!title.trim()) setTitle(file.name.replace(/\.[^.]+$/, ""));
    };
    reader.readAsText(file);
    e.target.value = "";
  }

  async function refresh(id) {
    try {
      const s = await api.docStatus(id);
      setDocs((d) => d.map((x) => x.document_id === id ? { ...x, status: s.status } : x));
    } catch {}
  }

  return (
    <div className="split">
      {/* ====== 主区: 入库表单 + 文档列表 ====== */}
      <div className="split-main">
        <div className="card">
          <div className="card-header">
            <div>
              <div className="card-title">入库新文档</div>
              <div className="card-desc">支持 Markdown / 已解析的文本,自动切分编译</div>
            </div>
          </div>

          <div className="form-block">
            <label className="label">文档标题</label>
            <input className="input" value={title} onChange={(e) => setTitle(e.target.value)}
                   placeholder="如:2026 项目预算报告" />
          </div>

          <div className="form-block">
            <label className="label">内容</label>
            <div className="row" style={{ marginBottom: 6 }}>
              <label className="file-btn">
                <IconUpload /> 上传 .md / .txt
                <input type="file" accept=".md,.txt" style={{ display: "none" }} onChange={handleFileUpload} />
              </label>
              <span className="form-hint">或直接在下方粘贴内容</span>
            </div>
            <textarea className="input" rows={8} value={markdown}
                      onChange={(e) => setMarkdown(e.target.value)}
                      placeholder="# 标题&#10;## 小节&#10;正文…" />
          </div>

          <div className="form-block">
            <label className="label">编译深度</label>
            <div className="choice-grid">
              {DEPTHS.map((d) => (
                <button key={d.v}
                        className={`choice ${depth === d.v ? "active" : ""}`}
                        onClick={() => setDepth(d.v)}>
                  <span className="choice-title">{d.label}</span>
                  <span className="choice-desc">{d.desc}</span>
                </button>
              ))}
            </div>
          </div>

          <div className="row" style={{ marginTop: 6 }}>
            <button className="btn primary" onClick={submit} disabled={busy || !title.trim() || !markdown.trim()}>
              {busy ? "入库中…" : "入库并编译"}
            </button>
            <span className="muted">{markdown.length} 字符</span>
          </div>
        </div>

        <div className="card">
          <div className="card-header">
            <div>
              <div className="card-title">已入库文档</div>
              <div className="card-desc">{docs.length} 个 · 状态随编译进度自动更新</div>
            </div>
          </div>

          <div className="list">
            {docs.length === 0 && (
              <div className="muted" style={{ padding: "16px 0", textAlign: "center" }}>
                还没有文档。上方提交后将在这里追踪。
              </div>
            )}
            {docs.map((d) => {
              const meta = STATUS_META[d.status] || { label: d.status, className: "" };
              return (
                <div className="list-row" key={d.document_id}>
                  <span className={`badge ${(d.depth || "").toLowerCase()}`}>{d.depth}</span>
                  <div className="grow">
                    <div className="title">{d.title}</div>
                    <div className="sub mono">{d.document_id}</div>
                  </div>
                  <span className={`badge ${meta.className}`}>{meta.label}</span>
                  <button className="btn ghost sm icon" onClick={() => refresh(d.document_id)} title="刷新状态">
                    <IconRefresh />
                  </button>
                </div>
              );
            })}
          </div>
        </div>
      </div>

      {/* ====== 右侧: 提示卡 / 深度说明 ====== */}
      <aside className="split-side">
        <div className="card" style={{ padding: 18 }}>
          <div className="card-title" style={{ marginBottom: 8, fontSize: 13 }}>关于编译深度</div>
          <div style={{ fontSize: 12.5, color: "var(--ink-2)", lineHeight: 1.6 }}>
            <div style={{ marginBottom: 8 }}>
              <span className="badge d0" style={{ marginRight: 6 }}>D0</span>
              仅做切分与向量化,适合先让文档"可问"。
            </div>
            <div style={{ marginBottom: 8 }}>
              <span className="badge d1" style={{ marginRight: 6 }}>D1</span>
              在 D0 基础上抽取事实/实体并消歧,适合一般问答。
            </div>
            <div>
              <span className="badge d2" style={{ marginRight: 6 }}>D2</span>
              完整图谱编译,跨文档关系打通,支持深度推理。
            </div>
          </div>
        </div>

        <div className="card" style={{ padding: 18 }}>
          <div className="card-title" style={{ marginBottom: 8, fontSize: 13 }}>建议</div>
          <ul style={{ fontSize: 12.5, color: "var(--ink-2)", paddingLeft: 18, margin: 0, lineHeight: 1.7 }}>
            <li>大于 50 页的文档先用 D0 验证可问性</li>
            <li>需要跨文档检索的强烈推荐 D2</li>
            <li>D2 调用 Sonnet 档,成本是 D0 的 8-10×</li>
          </ul>
        </div>
      </aside>
    </div>
  );
}
