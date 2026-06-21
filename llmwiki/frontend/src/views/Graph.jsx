import React, { useState, useEffect } from "react";
import { api } from "../api.js";
import GraphCanvas from "../components/GraphCanvas.jsx";

/** 节点类型 → 中文标签 + 颜色 */
const TYPE_META = {
  project: { label: "项目", color: "var(--node-project)" },
  person: { label: "人员", color: "var(--node-person)" },
  org: { label: "组织", color: "var(--node-org)" },
  concept: { label: "概念", color: "var(--node-concept)" },
  event: { label: "事件", color: "var(--node-event)" },
};

export default function Graph() {
  const [graph, setGraph] = useState({ nodes: [], edges: [] });
  const [sel, setSel] = useState(null);
  const [raw, setRaw] = useState("");
  const [live, setLive] = useState(false);
  const [apiError, setApiError] = useState(null);
  const [searchTerm, setSearchTerm] = useState("");
  const [highlightNode, setHighlightNode] = useState(null);

  useEffect(() => {
    api.graph("json").then((r) => {
      const g = typeof r.data === "string" ? JSON.parse(r.data) : r.data;
      if (g.nodes?.length) { setGraph(g); setLive(true); setApiError(null); }
      else { setGraph({ nodes: [], edges: [] }); setLive(true); setApiError(null); }
    }).catch((e) => {
      setApiError(e.message || String(e));
      setGraph({ nodes: [], edges: [] });
    });
  }, []);

  function load() {
    try { setGraph(JSON.parse(raw)); setSel(null); }
    catch { alert("JSON 解析失败"); }
  }

  // 搜索过滤
  const filteredNodes = searchTerm.trim()
    ? graph.nodes.filter((n) => n.name?.toLowerCase().includes(searchTerm.toLowerCase()))
    : graph.nodes;

  // 选中节点的关联关系
  const selEdges = sel
    ? graph.edges.filter((e) => e.source === sel.entity_id || e.target === sel.entity_id)
    : [];

  // 关联节点
  const selNeighbors = sel
    ? selEdges.map((e) => {
        const otherId = e.source === sel.entity_id ? e.target : e.source;
        const other = graph.nodes.find((n) => n.entity_id === otherId);
        return { edge: e, node: other || { entity_id: otherId, name: otherId.slice(0, 12), type: "?" } };
      })
    : [];

  return (
    <>
      {/* 搜索栏 */}
      <div className="row" style={{ marginBottom: 12, gap: 10 }}>
        <div style={{ flex: 1, position: "relative" }}>
          <input
            className="input"
            placeholder="🔍 搜索节点…"
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
            style={{ paddingLeft: 32 }}
          />
          <span style={{ position: "absolute", left: 10, top: 11, opacity: 0.4, fontSize: 13 }}>🔍</span>
        </div>
        <span className="muted" style={{ fontSize: 13, whiteSpace: "nowrap" }}>
          {graph.nodes.length > 0
            ? `${graph.nodes.length} 实体 · ${graph.edges.length} 关系`
            : apiError
              ? "连接失败"
              : "图谱为空"}
        </span>
        {live && !apiError && graph.nodes.length > 0 && (
          <span className="badge" style={{ background: "rgba(74,222,128,0.1)", color: "var(--green)", borderColor: "rgba(74,222,128,0.2)" }}>
            实时
          </span>
        )}
      </div>

      {/* 3D 图谱区域 */}
      {graph.nodes.length === 0 ? (
        <div className="card" style={{ textAlign: "center", color: "var(--ink-3)", padding: 60 }}>
          {apiError ? `服务不可用: ${apiError}` : "知识图谱中没有实体。请用 D2 深度编译文档。"}
        </div>
      ) : (
        <div className="graph-container" style={{ width: "100%", height: 520, marginBottom: 14 }}>
          <GraphCanvas
            nodes={filteredNodes}
            edges={graph.edges}
            onSelect={(n) => {
              setSel(n);
              setSearchTerm("");
            }}
            width={window.innerWidth - 320}
            height={520}
          />
        </div>
      )}

      {/* 选中节点的详情面板 */}
      {sel && (
        <div className="card" style={{ marginBottom: 14 }}>
          <div className="row" style={{ justifyContent: "space-between", marginBottom: 10 }}>
            <div className="row" style={{ gap: 10 }}>
              <span
                className="badge"
                style={{
                  background: `${TYPE_META[sel.type]?.color || "var(--ink-3)"}22`,
                  color: TYPE_META[sel.type]?.color || "var(--ink-2)",
                  borderColor: `${TYPE_META[sel.type]?.color || "var(--ink-3)"}44`,
                }}
              >
                {TYPE_META[sel.type]?.label || sel.type}
              </span>
              <div className="title" style={{ fontWeight: 650, fontSize: 16 }}>{sel.name}</div>
            </div>
            <button className="btn ghost" style={{ padding: "4px 10px", fontSize: 12 }} onClick={() => setSel(null)}>
              关闭 ✕
            </button>
          </div>
          <div className="muted mono" style={{ fontSize: 11, marginBottom: 12 }}>{sel.entity_id}</div>

          {/* 关联关系列表 */}
          {selNeighbors.length > 0 ? (
            <div>
              <label className="label" style={{ marginBottom: 8 }}>关联关系 ({selNeighbors.length})</label>
              <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
                {selNeighbors.map(({ edge, node }, i) => (
                  <div
                    key={i}
                    className="list-row"
                    style={{ cursor: "pointer", padding: "10px 14px" }}
                    onClick={() => {
                      setSel(node);
                    }}
                  >
                    <span
                      className="badge"
                      style={{
                        background: `${TYPE_META[node.type]?.color || "var(--ink-3)"}22`,
                        color: TYPE_META[node.type]?.color || "var(--ink-2)",
                        borderColor: `${TYPE_META[node.type]?.color || "var(--ink-3)"}44`,
                        fontSize: 9.5,
                      }}
                    >
                      {TYPE_META[node.type]?.label || node.type}
                    </span>
                    <div style={{ flex: 1 }}>
                      <span style={{ fontWeight: 500 }}>{node.name}</span>
                      <span className="cite" style={{ marginLeft: 8, fontSize: 10.5 }}>
                        {edge.relation}
                      </span>
                    </div>
                    <span style={{ color: "var(--ink-3)", fontSize: 11 }}>→</span>
                  </div>
                ))}
              </div>
            </div>
          ) : (
            <div className="muted" style={{ fontSize: 12 }}>该实体没有关联关系</div>
          )}
        </div>
      )}

      {/* 导入数据 */}
      <div className="card">
        <label className="label">导入图数据(可选)</label>
        <textarea className="input" rows={2} value={raw} onChange={(e) => setRaw(e.target.value)}
          placeholder='{"nodes":[…],"edges":[…]}' />
        <div style={{ height: 10 }} />
        <button className="btn ghost" onClick={load}>载入</button>
      </div>
    </>
  );
}
