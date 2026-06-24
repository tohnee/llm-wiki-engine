/**
 * markdown-parser.js — 极简 Markdown 解析(无 React 依赖,纯数据结构输出)
 * 从 Ask.jsx 抽离,把"解析"和"渲染"解耦,便于单元测试解析正确性。
 *
 * 输出 block 数组,每个 block 形如:
 *   { type: "p" | "h" | "ul" | "ol" | "quote" | "code" | "table", ... }
 * 由 Ask.jsx 的 renderBlocks 负责转成 React 元素。
 */

/** 把整段文本解析为 block 数组 */
export function parseMarkdown(text) {
  if (!text) return [];
  const lines = text.split("\n");
  const blocks = [];
  let i = 0;

  while (i < lines.length) {
    const line = lines[i];

    // 代码块 ```
    if (line.trim().startsWith("```")) {
      const lang = line.trim().slice(3).trim();
      const buf = []; i++;
      while (i < lines.length && !lines[i].trim().startsWith("```")) { buf.push(lines[i]); i++; }
      i++;
      blocks.push({ type: "code", lang, content: buf.join("\n") });
      continue;
    }

    // 表格
    if (line.trim().startsWith("|") && lines[i + 1]?.trim().match(/^\|[\s:|-]+\|$/)) {
      const headers = line.split("|").slice(1, -1).map((s) => s.trim());
      const rows = []; i += 2;
      while (i < lines.length && lines[i].trim().startsWith("|")) {
        rows.push(lines[i].split("|").slice(1, -1).map((s) => s.trim()));
        i++;
      }
      blocks.push({ type: "table", headers, rows });
      continue;
    }

    // 标题
    const h = /^(#{1,3})\s+(.+)/.exec(line);
    if (h) {
      blocks.push({ type: "h", level: h[1].length, text: h[2] });
      i++; continue;
    }

    // 引用
    if (line.startsWith("> ")) {
      const buf = [];
      while (i < lines.length && lines[i].startsWith("> ")) { buf.push(lines[i].slice(2)); i++; }
      blocks.push({ type: "quote", text: buf.join(" ") });
      continue;
    }

    // 无序列表
    if (/^\s*[-*]\s+/.test(line)) {
      const items = [];
      while (i < lines.length && /^\s*[-*]\s+/.test(lines[i])) { items.push(lines[i].replace(/^\s*[-*]\s+/, "")); i++; }
      blocks.push({ type: "ul", items });
      continue;
    }

    // 有序列表
    if (/^\s*\d+\.\s+/.test(line)) {
      const items = [];
      while (i < lines.length && /^\s*\d+\.\s+/.test(lines[i])) { items.push(lines[i].replace(/^\s*\d+\.\s+/, "")); i++; }
      blocks.push({ type: "ol", items });
      continue;
    }

    // 段落
    if (line.trim()) {
      const buf = [line]; i++;
      while (i < lines.length && lines[i].trim() && !/^(#|>|\s*[-*]\s|\s*\d+\.\s|```|\|)/.test(lines[i])) {
        buf.push(lines[i]); i++;
      }
      blocks.push({ type: "p", text: buf.join(" ") });
      continue;
    }

    i++; // 空行
  }

  return blocks;
}

/**
 * 把内联文本拆成 token 数组(用于渲染 **bold** / `code` / 普通文本)。
 * 输出: [{ type: "text"|"bold"|"code", value }]
 */
export function parseInline(text) {
  if (text == null || text === "") return [];
  const tokens = [];
  let rest = text;
  while (rest.length) {
    const mBold = /^\*\*([^*]+)\*\*/.exec(rest);
    const mCode = /^`([^`]+)`/.exec(rest);
    if (mBold) { tokens.push({ type: "bold", value: mBold[1] }); rest = rest.slice(mBold[0].length); continue; }
    if (mCode) { tokens.push({ type: "code", value: mCode[1] }); rest = rest.slice(mCode[0].length); continue; }
    const next = rest.search(/\*\*|`/);
    if (next === -1) { tokens.push({ type: "text", value: rest }); break; }
    if (next > 0) tokens.push({ type: "text", value: rest.slice(0, next) });
    rest = rest.slice(next === 0 ? 1 : next); // 防止死循环
    if (next === 0) tokens.push({ type: "text", value: rest[0] || "" });
  }
  return tokens;
}

/** 提取文本中的 citation 标记 [doc:span] */
export function extractCitations(text) {
  const re = /\[([\w\-]+):([\w\-]+)\]/g;
  const cites = [];
  let m;
  while ((m = re.exec(text)) !== null) {
    cites.push({ docId: m[1], spanId: m[2], raw: m[0] });
  }
  return cites;
}
