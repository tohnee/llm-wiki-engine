import React, { useState } from "react";
import { api } from "../api.js";
import { SKILL_TEMPLATES, getTemplateInstruction, getDefaultSubType } from "../generation-templates.js";

const TYPES = Object.entries(SKILL_TEMPLATES).map(([k, v]) => ({ v: k, ...v }));

export default function Generate() {
  const [type, setType] = useState("report");
  const [subType, setSubType] = useState(getDefaultSubType("report"));
  const [instruction, setInstruction] = useState(getTemplateInstruction("report", getDefaultSubType("report")));
  const [result, setResult] = useState(null);
  const [busy, setBusy] = useState(false);
  const [docFilter, setDocFilter] = useState("");

  const tpl = SKILL_TEMPLATES[type];
  const currentSub = tpl?.subTypes.find((s) => s.id === subType);

  function handleTypeChange(newType) {
    const def = getDefaultSubType(newType);
    setType(newType);
    setSubType(def);
    setInstruction(getTemplateInstruction(newType, def));
    setResult(null);
  }

  function handleSubTypeChange(id) {
    setSubType(id);
    setInstruction(getTemplateInstruction(type, id));
    setResult(null);
  }

  async function run(asFile) {
    if (!instruction.trim()) return;
    setBusy(true);
    setResult(null);
    try {
      const payload = { instruction, artifact_type: type };
      if (docFilter.trim()) {
        // 按文档筛选:支持逗号分隔的文档 ID 或标题关键词
        payload.document_ids = docFilter.split(",").map((s) => s.trim()).filter(Boolean);
      }
      const fn = asFile ? api.generateFile : api.generate;
      const r = await fn(payload);
      setResult(r);
    } catch (e) {
      setResult({ error: e.message });
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      {/* ---- 主类型卡片 ---- */}
      <div className="card" style={{ marginBottom: 16 }}>
        <label className="label">产物类型</label>
        <div className="row" style={{ flexWrap: "wrap", gap: 8, marginBottom: 4 }}>
          {TYPES.map((t) => (
            <button
              key={t.v}
              className={`btn ${type === t.v ? "" : "ghost"}`}
              onClick={() => handleTypeChange(t.v)}
            >
              <span style={{ marginRight: 4 }}>{t.glyph}</span>
              {t.label}
            </button>
          ))}
        </div>
      </div>

      {/* ---- 子类型(Skill 模板选择) ---- */}
      {tpl && (
        <div className="card" style={{ marginBottom: 16 }}>
          <label className="label">
            {tpl.glyph} {tpl.label} — 选择模板
          </label>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(180px, 1fr))", gap: 8 }}>
            {tpl.subTypes.map((st) => (
              <button
                key={st.id}
                className={`btn ${subType === st.id ? "" : "ghost"}`}
                onClick={() => handleSubTypeChange(st.id)}
                style={{
                  flexDirection: "column",
                  alignItems: "flex-start",
                  gap: 4,
                  padding: "12px 14px",
                  height: "auto",
                  textAlign: "left",
                }}
              >
                <div style={{ display: "flex", alignItems: "center", gap: 6, fontWeight: 600, fontSize: 13 }}>
                  <span>{st.icon}</span>
                  {st.label}
                </div>
                {st.desc && (
                  <div style={{ fontSize: 11.5, color: subType === st.id ? "rgba(255,255,255,0.7)" : "var(--ink-3)", fontWeight: 400 }}>
                    {st.desc}
                  </div>
                )}
              </button>
            ))}
          </div>
        </div>
      )}

      {/* ---- 指令编辑区 ---- */}
      <div className="card" style={{ marginBottom: 16 }}>
        <label className="label">指令{currentSub && currentSub.id !== "custom" ? `(${currentSub.label} 模板已预设)` : ""}</label>
        <textarea
          className="input"
          rows={4}
          value={instruction}
          onChange={(e) => setInstruction(e.target.value)}
          placeholder="输入生成指令,或选择上方模板自动填充…"
          style={{ fontFamily: "var(--sans)", fontSize: 13.5, lineHeight: 1.6 }}
        />

        {/* 图表类型子类型额外提示 */}
        {type === "chart" && currentSub && currentSub.chartHint && (
          <div style={{ marginTop: 8, fontSize: 12, color: "var(--ink-3)" }}>
            💡 提示: {currentSub.chartHint}。请确保指令中指明要提取的数据字段。
          </div>
        )}

        <div style={{ height: 12 }} />

        {/* 文档筛选(可选) */}
        <label className="label">文档筛选(可选)</label>
        <input
          className="input"
          value={docFilter}
          onChange={(e) => setDocFilter(e.target.value)}
          placeholder="留空=全部文档,或用逗号分隔指定文档ID"
          style={{ marginBottom: 12 }}
        />

        <div className="row">
          <button className="btn" onClick={() => run(false)} disabled={busy}>
            {busy ? "生成中…" : "🚀 生成内容"}
          </button>
          <button className="btn ghost" onClick={() => run(true)} disabled={busy}>
            生成并导出文件
          </button>
          <span className="muted">
            {type === "slides" ? "生成PPT大纲(JSON)" :
             type === "chart" ? "生成图表规范(JSON)" :
             type === "table" ? "生成结构化表格(JSON)" :
             "生成Markdown报告"}
          </span>
        </div>
      </div>

      {/* ---- 加载状态 ---- */}
      {busy && (
        <div className="card" style={{ textAlign: "center", padding: 30 }}>
          <div className="spinner">
            <span style={{ fontSize: 15 }}>⏳</span> 生成中,正在检索证据并调用 AI 模型…
            <span className="dots" />
          </div>
        </div>
      )}

      {/* ---- 结果展示 ---- */}
      {result && (
        <div className="card" style={{ marginTop: 4 }}>
          {result.error ? (
            <div style={{ color: "var(--prov-ambiguous)", display: "flex", alignItems: "center", gap: 8 }}>
              <span>⚠️</span> 生成失败: {result.error}
            </div>
          ) : (
            <>
              {/* 文件导出结果 */}
              {result.file_path && (
                <div style={{ marginBottom: 14, padding: "10px 14px", background: "var(--surface)", borderRadius: "var(--radius-sm)" }}>
                  <div className="row" style={{ gap: 8 }}>
                    <span>✅</span>
                    <div>
                      <div className="title" style={{ fontSize: 13 }}>已生成文件</div>
                      <div className="mono muted" style={{ fontSize: 11.5, marginTop: 2 }}>{result.file_path}</div>
                    </div>
                    <span className="badge" style={{ marginLeft: "auto" }}>证据 {result.evidence_count} 条</span>
                  </div>
                </div>
              )}

              {/* 报告(markdown) */}
              {result.format === "markdown" && (
                <div>
                  <div className="row" style={{ marginBottom: 10, gap: 8 }}>
                    <span className="badge" style={{ background: "var(--accent-soft)", color: "var(--accent-hover)", borderColor: "rgba(124,92,252,0.25)" }}>
                      Markdown 报告
                    </span>
                    <span className="muted">基于 {result.evidence_count} 条证据生成</span>
                  </div>
                  <div
                    style={{
                      background: "rgba(0,0,0,0.2)",
                      borderRadius: "var(--radius-sm)",
                      padding: 20,
                      fontSize: 13.5,
                      lineHeight: 1.7,
                      whiteSpace: "pre-wrap",
                      fontFamily: "var(--sans)",
                      maxHeight: 500,
                      overflow: "auto",
                    }}
                  >
                    {result.content}
                  </div>
                </div>
              )}

              {/* JSON 格式(图表/表格/幻灯片) */}
              {result.format === "json" && result.spec && (
                <div>
                  <div className="row" style={{ marginBottom: 10, gap: 8 }}>
                    <span className="badge" style={{ background: "rgba(96,165,250,0.1)", color: "#60A5FA", borderColor: "rgba(96,165,250,0.2)" }}>
                      JSON 规范
                    </span>
                    <span className="muted">
                      {result.spec.slides ? `${result.spec.slides.length} 页幻灯片` :
                       result.spec.columns ? `${result.spec.columns.length} 列 · ${result.spec.rows?.length || 0} 行` :
                       result.spec.chart_type ? `${result.spec.chart_type} 图` : ""}
                    </span>
                  </div>
                  <pre
                    className="mono"
                    style={{
                      background: "rgba(0,0,0,0.2)",
                      borderRadius: "var(--radius-sm)",
                      padding: 16,
                      fontSize: 12,
                      lineHeight: 1.5,
                      whiteSpace: "pre-wrap",
                      maxHeight: 400,
                      overflow: "auto",
                      margin: 0,
                    }}
                  >
                    {JSON.stringify(result.spec, null, 2)}
                  </pre>
                </div>
              )}
            </>
          )}
        </div>
      )}
    </>
  );
}
