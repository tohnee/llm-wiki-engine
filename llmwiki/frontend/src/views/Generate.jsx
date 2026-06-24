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
    setType(newType); setSubType(def);
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
    setBusy(true); setResult(null);
    try {
      const payload = { instruction, artifact_type: type };
      if (docFilter.trim()) {
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
    <div className="split">
      <div className="split-main">
        {/* 类型选择 */}
        <div className="card">
          <div className="card-header">
            <div>
              <div className="card-title">产物类型</div>
              <div className="card-desc">选择想生成的形态,再挑模板</div>
            </div>
          </div>
          <div className="choice-grid">
            {TYPES.map((t) => (
              <button key={t.v} className={`choice ${type === t.v ? "active" : ""}`}
                      onClick={() => handleTypeChange(t.v)}>
                <span className="choice-title">
                  <span>{t.glyph}</span>{t.label}
                </span>
                {t.desc && <span className="choice-desc">{t.desc}</span>}
              </button>
            ))}
          </div>
        </div>

        {/* 模板选择 */}
        {tpl && (
          <div className="card">
            <div className="card-header">
              <div>
                <div className="card-title">{tpl.label} · 模板</div>
                <div className="card-desc">挑一个模板,指令会自动预填到下方</div>
              </div>
            </div>
            <div className="choice-grid">
              {tpl.subTypes.map((st) => (
                <button key={st.id} className={`choice ${subType === st.id ? "active" : ""}`}
                        onClick={() => handleSubTypeChange(st.id)}>
                  <span className="choice-title">
                    {st.icon && <span>{st.icon}</span>}{st.label}
                  </span>
                  {st.desc && <span className="choice-desc">{st.desc}</span>}
                </button>
              ))}
            </div>
          </div>
        )}

        {/* 指令编辑 */}
        <div className="card">
          <div className="card-header">
            <div>
              <div className="card-title">指令</div>
              <div className="card-desc">
                {currentSub && currentSub.id !== "custom" ? `已预填「${currentSub.label}」模板,可继续编辑` : "自由输入生成指令"}
              </div>
            </div>
          </div>

          <textarea className="input" rows={6} value={instruction}
                    onChange={(e) => setInstruction(e.target.value)}
                    placeholder="输入生成指令,或先选模板自动填充…" />

          {type === "chart" && currentSub?.chartHint && (
            <div className="form-hint" style={{ marginTop: 6 }}>
              💡 提示: {currentSub.chartHint}。请在指令中指明要提取的数据字段。
            </div>
          )}

          <div className="form-block" style={{ marginTop: 14 }}>
            <label className="label">文档筛选(可选)</label>
            <input className="input" value={docFilter}
                   onChange={(e) => setDocFilter(e.target.value)}
                   placeholder="留空 = 全部文档,或用逗号分隔指定 document_id" />
          </div>

          <div className="row" style={{ marginTop: 14 }}>
            <button className="btn primary" onClick={() => run(false)} disabled={busy || !instruction.trim()}>
              {busy ? "生成中…" : "生成内容"}
            </button>
            <button className="btn ghost" onClick={() => run(true)} disabled={busy || !instruction.trim()}>
              生成并导出文件
            </button>
            <span className="muted">
              {type === "slides" ? "→ PPT 大纲 JSON" :
               type === "chart" ? "→ 图表规范 JSON" :
               type === "table" ? "→ 结构化表格 JSON" :
                                  "→ Markdown 报告"}
            </span>
          </div>
        </div>

        {/* 加载态 */}
        {busy && (
          <div className="card" style={{ textAlign: "center", padding: 36 }}>
            <span className="spinner">
              正在检索证据并调用模型
              <span className="dot-pulse"><i/><i/><i/></span>
            </span>
          </div>
        )}

        {/* 结果 */}
        {result && (
          <div className="card">
            {result.error ? (
              <div style={{ color: "var(--danger)", display: "flex", alignItems: "center", gap: 8 }}>
                <span>⚠️</span> 生成失败: {result.error}
              </div>
            ) : (
              <>
                {result.file_path && (
                  <div className="list-row" style={{ marginBottom: 12 }}>
                    <span style={{ fontSize: 16 }}>✅</span>
                    <div className="grow">
                      <div className="title">已生成文件</div>
                      <div className="sub mono">{result.file_path}</div>
                    </div>
                    {result.evidence_count != null && (
                      <span className="badge">证据 {result.evidence_count} 条</span>
                    )}
                  </div>
                )}

                {result.format === "markdown" && (
                  <>
                    <div className="row" style={{ marginBottom: 10 }}>
                      <span className="badge d2">Markdown 报告</span>
                      {result.evidence_count != null && (
                        <span className="muted">基于 {result.evidence_count} 条证据</span>
                      )}
                    </div>
                    <div className="result-pre">{result.content}</div>
                  </>
                )}

                {result.format === "json" && result.spec && (
                  <>
                    <div className="row" style={{ marginBottom: 10 }}>
                      <span className="badge d0">JSON 规范</span>
                      <span className="muted">
                        {result.spec.slides ? `${result.spec.slides.length} 页幻灯片` :
                         result.spec.columns ? `${result.spec.columns.length} 列 · ${result.spec.rows?.length || 0} 行` :
                         result.spec.chart_type ? `${result.spec.chart_type} 图` : ""}
                      </span>
                    </div>
                    <pre className="result-pre code">{JSON.stringify(result.spec, null, 2)}</pre>
                  </>
                )}
              </>
            )}
          </div>
        )}
      </div>

      {/* 右侧帮助 */}
      <aside className="split-side">
        <div className="card" style={{ padding: 18 }}>
          <div className="card-title" style={{ marginBottom: 8, fontSize: 13 }}>当前产物</div>
          <div style={{ fontSize: 13, color: "var(--ink)" }}>
            <span style={{ fontWeight: 600 }}>{tpl?.label || "—"}</span>
            {currentSub && <span style={{ color: "var(--ink-3)" }}> · {currentSub.label}</span>}
          </div>
          {currentSub?.desc && (
            <div className="muted" style={{ marginTop: 6 }}>{currentSub.desc}</div>
          )}
        </div>

        <div className="card" style={{ padding: 18 }}>
          <div className="card-title" style={{ marginBottom: 8, fontSize: 13 }}>使用建议</div>
          <ul style={{ fontSize: 12.5, color: "var(--ink-2)", paddingLeft: 18, margin: 0, lineHeight: 1.7 }}>
            <li>指令越具体,产出越聚焦</li>
            <li>用文档筛选缩小检索范围,可大幅减少幻觉</li>
            <li>JSON 产物可在外部渲染为 docx / xlsx / pptx</li>
          </ul>
        </div>
      </aside>
    </div>
  );
}
