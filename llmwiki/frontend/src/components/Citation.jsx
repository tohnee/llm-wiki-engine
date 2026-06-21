import React, { useState } from "react";

// 签名组件:把回答里的 [doc:span] 渲染为可展开的证据 chip。
// 点击调用 /read_span 取原文(此处经查询网关无该端点,改为展示已知证据;
// 生产可加 query 网关透传 /read_span)。这里用传入的 spanText 做即时展示。
export function Citation({ docId, spanId, spanText }) {
  const [open, setOpen] = useState(false);
  return (
    <span>
      <span className="cite" onClick={() => setOpen(!open)} title="查看原文证据">
        {docId}:{spanId}
      </span>
      {open && spanText && <div className="cite-pop">{spanText}</div>}
    </span>
  );
}

// 把回答文本里的 [doc:span] 标记替换为 Citation chip。
export function renderWithCitations(text, evidenceMap = {}) {
  const parts = [];
  const re = /\[([\w\-]+):([\w\-]+)\]/g;
  let last = 0, m, i = 0;
  while ((m = re.exec(text)) !== null) {
    if (m.index > last) parts.push(text.slice(last, m.index));
    parts.push(
      <Citation key={i++} docId={m[1]} spanId={m[2]} spanText={evidenceMap[`${m[1]}:${m[2]}`]} />
    );
    last = re.lastIndex;
  }
  if (last < text.length) parts.push(text.slice(last));
  return parts;
}

const PROV_LABEL = { extracted: "源文事实", inferred: "AI 推断", ambiguous: "多源矛盾" };

export function Provenance({ kind }) {
  return (
    <span className="muted" title={PROV_LABEL[kind] || kind}>
      <span className={`prov-dot prov-${kind}`} />
      {PROV_LABEL[kind] || kind}
    </span>
  );
}
