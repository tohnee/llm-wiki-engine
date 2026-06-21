import React, { useState, useRef, useEffect } from "react";
import { api } from "../api.js";
import { renderWithCitations } from "../components/Citation.jsx";

// 示例问题列表
const SUGGESTIONS = [
  "项目Alpha的预算是多少?",
  "项目Alpha的负责人是谁?",
  "项目Alpha的供应商是哪家?",
  "项目Alpha有哪些风险?",
];

export default function Ask() {
  const [sessionId] = useState(() => "s_" + Math.random().toString(36).slice(2, 10));
  const [msgs, setMsgs] = useState([]);
  const [q, setQ] = useState("");
  const [busy, setBusy] = useState(false);
  const [startTime, setStartTime] = useState(null);
  const [latency, setLatency] = useState(0);
  const endRef = useRef(null);

  useEffect(() => { endRef.current?.scrollIntoView({ behavior: "smooth" }); }, [msgs, busy]);

  async function send(question) {
    const qText = (question || q).trim();
    if (!qText || busy) return;
    setMsgs((m) => [...m, { role: "user", text: qText }]);
    setQ("");
    setBusy(true);
    setStartTime(Date.now());
    setLatency(0);

    // 计时器显示等待时间
    const timer = setInterval(() => {
      setLatency(Math.floor((Date.now() - startTime) / 1000));
    }, 1000);

    try {
      const r = await api.ask(qText, sessionId);
      clearInterval(timer);
      const elapsed = Math.floor((Date.now() - startTime) / 1000);
      setMsgs((m) => [
        ...m,
        {
          role: "assistant",
          text: r.answer || "(空回答)",
          ratio: r.verified_ratio,
          escalated: r.escalated,
          latency: elapsed,
        },
      ]);
    } catch (e) {
      clearInterval(timer);
      setMsgs((m) => [...m, { role: "assistant", text: `请求失败: ${e.message}`, error: true }]);
    } finally {
      setBusy(false);
      setStartTime(null);
    }
  }

  function handleSuggestion(s) {
    send(s);
  }

  const showEmpty = msgs.length === 0 && !busy;

  return (
    <>
      {/* 会话信息 */}
      <div className="row" style={{ justifyContent: "space-between", marginBottom: 16, flexWrap: "wrap", gap: 6 }}>
        <span className="muted" style={{ fontSize: 12 }}>
          会话 <span className="mono" style={{ fontSize: 10.5 }}>{sessionId}</span>
        </span>
        <span className="muted" style={{ fontSize: 12 }}>
          知识基于已编译文档 · 证据可追溯原文
        </span>
      </div>

      {/* 消息区 */}
      <div className="chat" style={{ minHeight: showEmpty ? "auto" : 300 }}>
        {/* 空状态:引导用户提问 */}
        {showEmpty && (
          <div className="card" style={{ textAlign: "center", padding: "32px 20px" }}>
            <div style={{ fontSize: 14, color: "var(--ink-2)", marginBottom: 16, lineHeight: 1.6 }}>
              基于知识库文档的智能问答系统
            </div>
            <div style={{ display: "flex", flexWrap: "wrap", gap: 8, justifyContent: "center", maxWidth: 500, margin: "0 auto" }}>
              {SUGGESTIONS.map((s) => (
                <button
                  key={s}
                  className="btn ghost"
                  style={{ fontSize: 12.5, padding: "8px 14px" }}
                  onClick={() => handleSuggestion(s)}
                >
                  {s}
                </button>
              ))}
            </div>
            <div className="muted" style={{ marginTop: 16, fontSize: 12 }}>
              或自行输入问题 ↓
            </div>
          </div>
        )}

        {msgs.map((m, i) => (
          <div key={i} className={`msg ${m.role}`}>
            <div className="bubble" style={m.error ? { color: "var(--prov-ambiguous)" } : undefined}>
              {m.role === "assistant" ? renderWithCitations(m.text) : m.text}
            </div>
            {m.role === "assistant" && !m.error && (
              <div className="answer-meta">
                {typeof m.ratio === "number" && (
                  <span className={`ratio ${m.ratio >= 0.8 ? "good" : "warn"}`}>
                    证据校验 {Math.round(m.ratio * 100)}%
                  </span>
                )}
                {m.escalated && (
                  <span
                    className="badge"
                    style={{
                      background: "rgba(251, 191, 36, 0.1)",
                      color: "var(--amber)",
                      borderColor: "rgba(251, 191, 36, 0.2)",
                    }}
                  >
                    多跳深度检索
                  </span>
                )}
                {m.latency != null && (
                  <span className="muted" style={{ fontSize: 11 }}>
                    {m.latency < 60 ? `${m.latency}s` : `${Math.floor(m.latency / 60)}m${m.latency % 60}s`}
                  </span>
                )}
              </div>
            )}
          </div>
        ))}

        {/* 加载状态 */}
        {busy && (
          <div className="msg assistant">
            <div
              className="bubble"
              style={{ display: "flex", alignItems: "center", gap: 10, color: "var(--ink-2)" }}
            >
              <div className="spinner">
                推理中
                <span className="dots" />
              </div>
              {latency > 5 && (
                <span className="muted" style={{ fontSize: 11 }}>
                  ({latency}s 等待中…)
                </span>
              )}
            </div>
          </div>
        )}

        <div ref={endRef} />
      </div>

      {/* 输入框 */}
      <div className="composer">
        <input
          className="input"
          value={q}
          onChange={(e) => setQ(e.target.value)}
          placeholder="输入问题…"
          onKeyDown={(e) => e.key === "Enter" && send()}
          disabled={busy}
        />
        <button className="btn" onClick={() => send()} disabled={busy || !q.trim()}>
          {busy ? "等待…" : "发送"}
        </button>
      </div>
    </>
  );
}
