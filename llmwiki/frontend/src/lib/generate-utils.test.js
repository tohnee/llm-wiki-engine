import { describe, it, expect } from "vitest";
import { classifyResult, summarizeSpec, typeHint } from "../lib/generate-utils.js";

describe("generate-utils: classifyResult", () => {
  it("null/undefined → empty", () => {
    expect(classifyResult(null).kind).toBe("empty");
    expect(classifyResult(undefined).kind).toBe("empty");
  });

  it("error 字段 → error", () => {
    const r = classifyResult({ error: "调用失败" });
    expect(r.kind).toBe("error");
    expect(r.message).toBe("调用失败");
  });

  it("markdown 格式", () => {
    const r = classifyResult({ format: "markdown", content: "# 报告", evidence_count: 5 });
    expect(r.kind).toBe("markdown");
    expect(r.content).toBe("# 报告");
    expect(r.evidenceCount).toBe(5);
  });

  it("json 格式 + summary", () => {
    const r = classifyResult({ format: "json", spec: { slides: [{}, {}, {}] } });
    expect(r.kind).toBe("json");
    expect(r.summary).toBe("3 页幻灯片");
  });

  it("纯文件导出 → file", () => {
    const r = classifyResult({ file_path: "/out/report.docx", evidence_count: 8 });
    expect(r.kind).toBe("file");
    expect(r.filePath).toBe("/out/report.docx");
  });

  it("兜底: 有 content 但 format 缺失 → text", () => {
    const r = classifyResult({ content: "一些文本" });
    expect(r.kind).toBe("text");
    expect(r.content).toBe("一些文本");
  });

  it("兜底: 有 spec 但 format 非 json → json", () => {
    const r = classifyResult({ spec: { chart_type: "bar" } });
    expect(r.kind).toBe("json");
  });

  it("回归: format 大小写不敏感", () => {
    expect(classifyResult({ format: "MARKDOWN", content: "x" }).kind).toBe("markdown");
    expect(classifyResult({ format: "JSON", spec: {} }).kind).toBe("json");
  });

  it("完全空结果对象 → empty", () => {
    expect(classifyResult({}).kind).toBe("empty");
  });
});

describe("generate-utils: summarizeSpec", () => {
  it("幻灯片页数", () => {
    expect(summarizeSpec({ slides: [{}, {}] })).toBe("2 页幻灯片");
  });
  it("表格行列", () => {
    expect(summarizeSpec({ columns: ["a", "b"], rows: [{}, {}, {}] })).toBe("2 列 · 3 行");
  });
  it("图表类型", () => {
    expect(summarizeSpec({ chart_type: "line" })).toBe("line 图");
  });
  it("空 spec", () => {
    expect(summarizeSpec(null)).toBe("");
    expect(summarizeSpec({})).toBe("");
  });
});

describe("generate-utils: typeHint", () => {
  it("各类型提示", () => {
    expect(typeHint("slides")).toContain("PPT");
    expect(typeHint("chart")).toContain("图表");
    expect(typeHint("table")).toContain("表格");
    expect(typeHint("report")).toContain("Markdown");
    expect(typeHint("unknown")).toContain("Markdown"); // 默认
  });
});
