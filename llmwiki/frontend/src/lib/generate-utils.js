/**
 * generate-utils.js — 生成结果格式判定(无 React 依赖,易测试)
 * 从 Generate.jsx 抽离,解决"format 不匹配导致结果不可见"的脆弱判断。
 */

/**
 * 归一化后端返回的生成结果,判定该如何渲染。
 * 返回: { kind: "error"|"markdown"|"json"|"text"|"file"|"empty", ... }
 */
export function classifyResult(result) {
  if (!result) return { kind: "empty" };
  if (result.error) return { kind: "error", message: result.error };

  const out = { kind: "empty", filePath: result.file_path, evidenceCount: result.evidence_count };

  // 文件导出
  if (result.file_path && !result.content && !result.spec) {
    return { ...out, kind: "file" };
  }

  // Markdown 报告(format 显式 markdown,或有 content 但无 spec)
  const fmt = (result.format || "").toLowerCase();
  if (fmt === "markdown" && result.content) {
    return { ...out, kind: "markdown", content: result.content };
  }
  if (fmt === "json" && result.spec) {
    return { ...out, kind: "json", spec: result.spec, summary: summarizeSpec(result.spec) };
  }

  // 兜底: 有 content 当 markdown/text
  if (result.content) {
    return { ...out, kind: fmt === "markdown" ? "markdown" : "text", content: result.content };
  }
  // 兜底: 有 spec 当 json
  if (result.spec) {
    return { ...out, kind: "json", spec: result.spec, summary: summarizeSpec(result.spec) };
  }

  return out; // empty
}

/** 概括 JSON spec(幻灯片页数 / 表格行列 / 图表类型) */
export function summarizeSpec(spec) {
  if (!spec) return "";
  if (spec.slides) return `${spec.slides.length} 页幻灯片`;
  if (spec.columns) return `${spec.columns.length} 列 · ${spec.rows?.length || 0} 行`;
  if (spec.chart_type) return `${spec.chart_type} 图`;
  return "";
}

/** 根据产物类型返回提示文案 */
export function typeHint(type) {
  switch (type) {
    case "slides": return "→ PPT 大纲 JSON";
    case "chart": return "→ 图表规范 JSON";
    case "table": return "→ 结构化表格 JSON";
    default: return "→ Markdown 报告";
  }
}
