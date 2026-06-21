import React, { useState, useEffect } from "react";
import { api } from "../api.js";

const DEPTHS = [
  { v: "D0", label: "D0 快速", desc: "分钟级可问(span 检索)" },
  { v: "D1", label: "D1 标准", desc: "+ 事实/实体/消歧" },
  { v: "D2", label: "D2 图谱", desc: "+ 关系/跨文档/Wiki" },
];

export default function Documents() {
  const [title, setTitle] = useState("");
  const [markdown, setMarkdown] = useState("");
  const [depth, setDepth] = useState("D1");
  const [docs, setDocs] = useState([]);
  const [busy, setBusy] = useState(false);

  // 页面加载时从后端拉取已有文档
  useEffect(() => {
    api.listDocs().then((list) => {
      setDocs(list.map((d) => ({
        document_id: d.document_id,
        title: d.title,
        depth: d.depth,
        status: d.status,
      })));
    }).catch(() => { /* 忽略加载失败 */ });
  }, []);

  async function submit() {
    if (!title.trim() || !markdown.trim()) return;
    setBusy(true);
    try {
      const r = await api.ingest({ title, markdown, depth });
      setDocs((d) => [{ document_id: r.document_id, title, depth, status: r.status }, ...d]);
      setTitle(""); setMarkdown("");
    } catch (e) { alert("入库失败:" + e.message); } finally { setBusy(false); }
  }

  function handleFileUpload(e) {
    const file = e.target.files?.[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = (ev) => {
      const text = ev.target.result;
      setMarkdown(text);
      // 用文件名(去掉扩展名)作为默认标题
      if (!title.trim()) {
        setTitle(file.name.replace(/\.[^.]+$/, ""));
      }
    };
    reader.readAsText(file);
    // 重置 input 以便重复选择同一文件
    e.target.value = "";
  }

  async function refresh(id) {
    try {
      const s = await api.docStatus(id);
      setDocs((d) => d.map((x) => x.document_id === id ? { ...x, status: s.status } : x));
    } catch (e) { /* ignore */ }
  }

  return (
    <>
      <div className="card" style={{ marginBottom: 20 }}>
        <label className="label">文档标题</label>
        <input className="input" value={title} onChange={(e) => setTitle(e.target.value)}
          placeholder="如:2026 项目预算报告" />
        <div style={{ height: 14 }} />
        <label className="label">内容(Markdown,或经 MinerU 解析后的文本)</label>
        <div className="row" style={{ gap: 8, marginBottom: 8 }}>
          <label className="btn ghost" style={{ cursor: "pointer", display: "inline-flex", alignItems: "center", gap: 6 }}>
            <span>📄</span> 上传文件
            <input type="file" accept=".md,.txt" style={{ display: "none" }} onChange={handleFileUpload} />
          </label>
          <span className="muted" style={{ fontSize: 12 }}>支持 .md / .txt（上传后自动填入内容区）</span>
        </div>
        <textarea className="input" rows={8} value={markdown}
          onChange={(e) => setMarkdown(e.target.value)} placeholder="# 标题&#10;## 小节&#10;正文…" />
        <div style={{ height: 14 }} />
        <label className="label">编译深度</label>
        <div className="row" style={{ flexWrap: "wrap" }}>
          {DEPTHS.map((d) => (
            <button key={d.v} className={`btn ${depth === d.v ? "" : "ghost"}`}
              onClick={() => setDepth(d.v)} title={d.desc}>{d.label}</button>
          ))}
          <span className="muted">{DEPTHS.find((d) => d.v === depth).desc}</span>
        </div>
        <div style={{ height: 16 }} />
        <button className="btn" onClick={submit} disabled={busy}>{busy ? "入库中…" : "入库并编译"}</button>
      </div>

      <h3 style={{ margin: "0 0 12px", fontSize: 14 }}>本会话提交的文档</h3>
      <div className="list">
        {docs.length === 0 && <div className="muted">还没有文档。上方提交后会在这里追踪编译状态。</div>}
        {docs.map((d) => (
          <div className="list-row" key={d.document_id}>
            <span className={`badge ${d.depth.toLowerCase()}`}>{d.depth}</span>
            <div className="grow">
              <div className="title">{d.title}</div>
              <div className="mono muted">{d.document_id}</div>
            </div>
            <span className="badge">{d.status}</span>
            <button className="btn ghost" onClick={() => refresh(d.document_id)}>刷新状态</button>
          </div>
        ))}
      </div>
    </>
  );
}
