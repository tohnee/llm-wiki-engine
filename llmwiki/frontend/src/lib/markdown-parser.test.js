import { describe, it, expect } from "vitest";
import { parseMarkdown, parseInline, extractCitations } from "../lib/markdown-parser.js";

describe("markdown-parser: parseMarkdown", () => {
  it("解析段落", () => {
    const b = parseMarkdown("这是一段普通文本。");
    expect(b).toHaveLength(1);
    expect(b[0]).toEqual({ type: "p", text: "这是一段普通文本。" });
  });

  it("解析标题(h1-h3 → level)", () => {
    const b = parseMarkdown("# 一级\n## 二级\n### 三级");
    expect(b.map((x) => x.level)).toEqual([1, 2, 3]);
    expect(b[0].type).toBe("h");
  });

  it("解析无序列表", () => {
    const b = parseMarkdown("- 项A\n- 项B\n- 项C");
    expect(b[0].type).toBe("ul");
    expect(b[0].items).toEqual(["项A", "项B", "项C"]);
  });

  it("解析有序列表", () => {
    const b = parseMarkdown("1. 第一\n2. 第二");
    expect(b[0].type).toBe("ol");
    expect(b[0].items).toHaveLength(2);
  });

  it("解析引用", () => {
    const b = parseMarkdown("> 这是引用");
    expect(b[0]).toEqual({ type: "quote", text: "这是引用" });
  });

  it("解析代码块(含语言标识)", () => {
    const b = parseMarkdown("```python\nprint(1)\nprint(2)\n```");
    expect(b[0].type).toBe("code");
    expect(b[0].lang).toBe("python");
    expect(b[0].content).toBe("print(1)\nprint(2)");
  });

  it("解析表格", () => {
    const md = "| 名称 | 值 |\n|------|-----|\n| A | 1 |\n| B | 2 |";
    const b = parseMarkdown(md);
    expect(b[0].type).toBe("table");
    expect(b[0].headers).toEqual(["名称", "值"]);
    expect(b[0].rows).toEqual([["A", "1"], ["B", "2"]]);
  });

  it("混合内容顺序正确", () => {
    const md = "# 标题\n\n段落文本\n\n- 列表项\n\n```js\ncode\n```";
    const b = parseMarkdown(md);
    expect(b.map((x) => x.type)).toEqual(["h", "p", "ul", "code"]);
  });

  it("空输入返回空数组", () => {
    expect(parseMarkdown("")).toEqual([]);
    expect(parseMarkdown(null)).toEqual([]);
  });
});

describe("markdown-parser: parseInline", () => {
  it("解析粗体", () => {
    const t = parseInline("这是**重点**内容");
    expect(t).toEqual([
      { type: "text", value: "这是" },
      { type: "bold", value: "重点" },
      { type: "text", value: "内容" },
    ]);
  });

  it("解析行内代码", () => {
    const t = parseInline("用 `npm install` 安装");
    expect(t.find((x) => x.type === "code").value).toBe("npm install");
  });

  it("纯文本", () => {
    expect(parseInline("纯文本")).toEqual([{ type: "text", value: "纯文本" }]);
  });

  it("空输入返回空数组", () => {
    expect(parseInline("")).toEqual([]);
    expect(parseInline(null)).toEqual([]);
  });

  it("不死循环(连续特殊符号)", () => {
    const t = parseInline("**a** **b**");
    expect(t.filter((x) => x.type === "bold")).toHaveLength(2);
  });
});

describe("markdown-parser: extractCitations", () => {
  it("提取单个 citation", () => {
    const c = extractCitations("答案 [doc_001:sp_a1b2] 完毕");
    expect(c).toEqual([{ docId: "doc_001", spanId: "sp_a1b2", raw: "[doc_001:sp_a1b2]" }]);
  });

  it("提取多个 citation", () => {
    const c = extractCitations("[d1:s1] 和 [d2:s2]");
    expect(c).toHaveLength(2);
  });

  it("无 citation 返回空", () => {
    expect(extractCitations("普通文本")).toEqual([]);
  });
});
