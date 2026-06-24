import React, { useState, useRef, useEffect } from "react";
import { api } from "../api.js";
import { Citation } from "../components/Citation.jsx";
import { parseMarkdown, parseInline, extractCitations } from "../lib/markdown-parser.js";
import { MOCK_HISTORY } from "../mock-history.js";

const SUGGESTIONS = [
  "项目 Alpha 的预算是多少?",
  "项目 Alpha 的负责人是谁?",
  "对比 D0/D1/D2 三种编译深度",
  "项目 Alpha 与 Beta 的供应商有重叠吗?",
];

function SendIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none"
         stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="M5 12h14" /><path d="M13 6l6 6-6 6" />
    </svg>
  );
}

/* ─── 渲染层(薄): 把 parser 输出的数据结构转成 React 元素 ─── */
// 内联: 先按 citation 切分,再对每段做 bold/code
function renderInline(text) {
  if (text == null || text === "") return null;
  const cites = extractCitations(text);
  if (cites.length === 0) return renderTokens(text);

  // 按 citation raw 切分文本,citation 处插入 <Citation>
  const parts = [];
  let rest = text, key = 0;
  for (const c of cites) {
    const idx = rest.indexOf(c.raw);
    if (idx > 0) parts.push(<React.Fragment key={key++}>{renderTokens(rest.slice(0, idx))}</React.Fragment>);
    parts.push(<Citation key={key++} docId={c.docId} spanId={c.spanId} />);
    rest = rest.slice(idx + c.raw.length);
  }
  if (rest) parts.push(<React.Fragment key={key++}>{renderTokens(rest)}</React.Fragment>);
  return parts;
}

// 把 bold/code/text token 转成元素
function renderTokens(text) {
  return parseInline(text).map((tok, i) => {
    if (tok.type === "bold") return <strong key={i}>{tok.value}</strong>;
    if (tok.type === "code") return <code key={i} className="md-inline-code">{tok.value}</code>;
    return <React.Fragment key={i}>{tok.value}</React.Fragment>;
  });
}

// 把 parseMarkdown 输出的 block 数组转成 React 元素
function renderMarkdown(text) {
  const blocks = parseMarkdown(text);
  return (
    <>
      {blocks.map((b, i) => {
        switch (b.type) {
          case "code":
            return (
              <pre key={i} className="md-code">
                {b.lang && <div className="md-code-lang">{b.lang}</div>}
                <code>{b.content}</code>
              </pre>
            );
          case "table":
            return (
              <div key={i} className="md-table-wrap">
                <table className="md-table">
                  <thead><tr>{b.headers.map((h, k) => <th key={k}>{renderInline(h)}</th>)}</tr></thead>
                  <tbody>{b.rows.map((r, ri) => (
                    <tr key={ri}>{r.map((c, ci) => <td key={ci}>{renderInline(c)}</td>)}</tr>
                  ))}</tbody>
                </table>
              </div>
            );
          case "h": {
            const Tag = `h${b.level + 2}`;
            return <Tag key={i} className="md-h">{renderInline(b.text)}</Tag>;
          }
          case "quote":
            return <blockquote key={i} className="md-quote">{renderInline(b.text)}</blockquote>;
          case "ul":
            return <ul key={i} className="md-ul">{b.items.map((t, k) => <li key={k}>{renderInline(t)}</li>)}</ul>;
          case "ol":
            return <ol key={i} className="md-ol">{b.items.map((t, k) => <li key={k}>{renderInline(t)}</li>)}</ol>;
          default:
            return <p key={i} className="md-p">{renderInline(b.text)}</p>;
        }
      })}
    </>
  );
}

export default function Ask() {
  const [sessionId] = useState(() => "s_" + Math.random().toString(36).slice(2, 10));
  const [msgs, setMsgs] = useState([]);
  const [q, setQ] = useState("");
  const [busy, setBusy] = useState(false);
  const [startedAt, setStartedAt] = useState(null);
  const [elapsed, setElapsed] = useState(0);
  const endRef = useRef(null);

  useEffect(() => { endRef.current?.scrollIntoView({ behavior: "smooth" }); }, [msgs, busy]);

  // 等待计时器
  useEffect(() => {
    if (!busy || !startedAt) return;
    const t = setInterval(() => setElapsed(Math.floor((Date.now() - startedAt) / 1000)), 1000);
    return () => clearInterval(t);
  }, [busy, startedAt]);

  async function send(question) {
    const text = (question ?? q).trim();
    if (!text || busy) return;

    // ===== 详细日志: 请求发送 =====
    const t0 = Date.now();
    const reqId = "req_" + t0.toString(36) + Math.random().toString(36).slice(2, 6);
    const tsSend = new Date(t0).toISOString();
    console.groupCollapsed(`%c[Ask] → POST /ask  ${reqId}`, "color:#CC785C;font-weight:600");
    console.log("%c  ⏱  发送时间", "color:#8A8780", tsSend);
    console.log("%c  💬  会话",     "color:#8A8780", sessionId);
    console.log("%c  ❓  问题",     "color:#8A8780", text);
    console.log("%c  📦  payload",  "color:#8A8780", { question: text, session_id: sessionId });
    console.groupEnd();

    setMsgs((m) => [...m, { role: "user", text }]);
    setQ("");
    setBusy(true);
    setStartedAt(t0);
    setElapsed(0);

    try {
      const r = await api.ask(text, sessionId);
      const t1 = Date.now();
      const took = t1 - t0;

      // ===== 详细日志: 响应接收 =====
      const tsRecv = new Date(t1).toISOString();
      const latencyColor = took < 5000 ? "#16A34A" : took < 15000 ? "#D97706" : "#DC2626";
      console.groupCollapsed(
        `%c[Ask] ← 200  ${reqId}  ${took}ms`,
        `color:${latencyColor};font-weight:600`
      );
      console.log("%c  ⏱  接收时间",         "color:#8A8780", tsRecv);
      console.log("%c  ⏳  端到端延迟",       "color:#8A8780", `${took}ms (${(took/1000).toFixed(2)}s)`);
      console.log("%c  📊  verified_ratio",   "color:#8A8780", r.verified_ratio);
      console.log("%c  🔁  escalated",        "color:#8A8780", r.escalated);
      console.log("%c  📝  answer.length",    "color:#8A8780", (r.answer || "").length);
      console.log("%c  🔗  citations",        "color:#8A8780", r.citations?.length || 0);
      console.log("%c  raw",                  "color:#B5B2AA", r);
      console.groupEnd();

      setMsgs((m) => [...m, {
        role: "assistant",
        text: r.answer || "(空回答)",
        ratio: r.verified_ratio,
        escalated: r.escalated,
        latency: Math.floor(took / 1000),
        citations: r.citations || [],
        claims: r.claims || [],
        toolTrace: r.tool_trace || [],
      }]);
    } catch (e) {
      const took = Date.now() - t0;
      console.error(`%c[Ask] ✗ FAIL ${reqId} ${took}ms`, "color:#DC2626;font-weight:600", e);
      setMsgs((m) => [...m, { role: "assistant", text: `请求失败: ${e.message}`, error: true }]);
    } finally {
      setBusy(false);
      setStartedAt(null);
    }
  }

  function loadMockHistory() {
    console.log("%c[Ask] 载入 5 组演示对话(MOCK_HISTORY)", "color:#10A37F;font-weight:600", MOCK_HISTORY);
    setMsgs(MOCK_HISTORY);
  }

  function clearHistory() {
    console.log("%c[Ask] 清空对话", "color:#8A8780");
    setMsgs([]);
  }

  function ratioClass(r) {
    if (r == null) return "";
    if (r >= 0.8) return "good";
    if (r >= 0.5) return "warn";
    return "poor";
  }

  const showEmpty = msgs.length === 0 && !busy;

  return (
    <div className="chat-wrap">
      <div className="session-bar">
        <span>会话 <span className="session-id">{sessionId}</span></span>
        <div className="row" style={{ gap: 8 }}>
          {msgs.length === 0 ? (
            <button className="btn ghost sm" onClick={loadMockHistory}>载入演示对话</button>
          ) : (
            <button className="btn subtle sm" onClick={clearHistory}>清空</button>
          )}
        </div>
      </div>

      <div className="chat">
        {showEmpty && (
          <div className="empty-state">
            <div className="empty-icon">
              <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor"
                   strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round">
                <path d="M21 11.5a8.4 8.4 0 0 1-13.5 6.8L3 19l1-3.7a8.4 8.4 0 1 1 17-3.8z"/>
              </svg>
            </div>
            <div className="empty-title">问任何关于知识库的问题</div>
            <div className="empty-desc">每个回答都基于已编译的文档,引用可一键回链原文</div>
            <div className="suggestion-chips">
              {SUGGESTIONS.map((s) => (
                <button key={s} className="suggestion-chip" onClick={() => send(s)}>{s}</button>
              ))}
            </div>
          </div>
        )}

        {msgs.map((m, i) => (
          <div key={i} className={`msg ${m.role}`}>
            <div className="msg-meta-top">
              <div className="msg-avatar">{m.role === "user" ? "你" : "W"}</div>
              <span>{m.role === "user" ? "提问" : "LLM-Wiki"}</span>
            </div>
            <div className="bubble" style={m.error ? { color: "#fff", background: "var(--danger)", borderColor: "var(--danger)" } : undefined}>
              {m.role === "assistant" ? renderMarkdown(m.text) : m.text}
            </div>
            {m.role === "assistant" && !m.error && (
              <div className="answer-meta">
                {typeof m.ratio === "number" && (
                  <span className={`ratio ${ratioClass(m.ratio)}`}>
                    <span className="dot" />证据校验 {Math.round(m.ratio * 100)}%
                  </span>
                )}
                {m.escalated && (
                  <span className="badge warn"><span className="dot" />多跳深度检索</span>
                )}
                {m.latency != null && (
                  <span className="muted tabular" style={{ fontSize: 11.5 }}>
                    {m.latency < 60 ? `${m.latency}s` : `${Math.floor(m.latency / 60)}m ${m.latency % 60}s`}
                  </span>
                )}
              </div>
            )}
            {m.role === "assistant" && !m.error && (m.citations?.length || m.claims?.length || m.toolTrace?.length) ? (
              <div className="audit-panel">
                <div className="audit-strip">
                  <span>Evidence Mesh</span>
                  <b>{m.citations?.length || 0}</b><em>citations</em>
                  <b>{m.claims?.filter(c => c.verified === true).length || 0}/{m.claims?.length || 0}</b><em>claims</em>
                  <b>{m.toolTrace?.length || 0}</b><em>tools</em>
                </div>
                {m.toolTrace?.length > 0 && (
                  <div className="trace-list">
                    {m.toolTrace.slice(0, 6).map((t, ti) => (
                      <span key={ti} className={`trace-pill ${t.ok ? "ok" : "bad"}`}>
                        {t.turn}:{t.tool}
                      </span>
                    ))}
                  </div>
                )}
              </div>
            ) : null}
          </div>
        ))}

        {busy && (
          <div className="msg assistant">
            <div className="msg-meta-top">
              <div className="msg-avatar">W</div>
              <span>LLM-Wiki</span>
            </div>
            <div className="bubble" style={{ display: "flex", alignItems: "center", gap: 12 }}>
              <span className="spinner">
                推理中
                <span className="dot-pulse"><i/><i/><i/></span>
              </span>
              {elapsed > 4 && (
                <span className="muted tabular" style={{ fontSize: 11.5 }}>{elapsed}s</span>
              )}
            </div>
          </div>
        )}

        <div ref={endRef} />
      </div>

      <div className="composer-wrap">
        <div className="composer">
          <input
            className="input"
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder="向你的知识库提问…"
            onKeyDown={(e) => e.key === "Enter" && send()}
            disabled={busy}
          />
          <button className="btn primary" onClick={() => send()} disabled={busy || !q.trim()}>
            {busy ? "等待…" : (<><span>发送</span><SendIcon /></>)}
          </button>
        </div>
      </div>
    </div>
  );
}
