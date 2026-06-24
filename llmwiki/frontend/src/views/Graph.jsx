import React, { useState, useEffect } from "react";
import { api } from "../api.js";
import GraphCanvas from "../components/GraphCanvas.jsx";

/** 节点类型 → 中文标签 + 颜色(与设计系统 --node-* 对齐) */
const TYPE_META = {
  project: { label: "项目", color: "#CC785C" },
  product: { label: "产品", color: "#CC785C" },
  person:  { label: "人员", color: "#10A37F" },
  org:     { label: "组织", color: "#2563EB" },
  concept: { label: "概念", color: "#8B5CF6" },
  event:   { label: "事件", color: "#EC4899" },
};

function IconSearch() {
  return (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor"
         strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <circle cx="11" cy="11" r="7"/><path d="M21 21l-4.3-4.3"/>
    </svg>
  );
}

export default function Graph() {
  const [graph, setGraph] = useState({ nodes: [], edges: [] });
  const [sel, setSel] = useState(null);
  const [hover, setHover] = useState(null);
  const [raw, setRaw] = useState("");
  const [live, setLive] = useState(false);
  const [apiError, setApiError] = useState(null);
  const [searchTerm, setSearchTerm] = useState("");
  // ───── 新增过滤控件 ─────
  const [hideIsolated, setHideIsolated] = useState(false);  // 默认显示全部(避免边格式不匹配时全过滤掉)
  const [minDegree, setMinDegree] = useState(0);            // 度数阈值
  const [typeFilter, setTypeFilter] = useState(null);       // 按类型过滤
  const [topN, setTopN] = useState(80);                     // 最多显示 N 个节点(按度数)

  useEffect(() => {
    api.graph("json").then((r) => {
      const g = typeof r.data === "string" ? JSON.parse(r.data) : r;
      const gd = (g && g.nodes) ? g : (g && g.data ? g.data : { nodes: [], edges: [] });
      const edges = (gd.edges || []).map((e) => ({
        source: e.source, target: e.target,
        relation: e.relation_type || e.relation || "",
      }));
      // 计算每个节点的真实度数(忽略后端给的 degree,自己算)
      const degMap = {};
      edges.forEach((e) => {
        degMap[e.source] = (degMap[e.source] || 0) + 1;
        degMap[e.target] = (degMap[e.target] || 0) + 1;
      });
      const nodes = (gd.nodes || []).map((n) => {
        const id = n.id || n.entity_id;
        return {
          entity_id: id,
          name: n.name,
          type: n.type,
          degree: degMap[id] || 0,
        };
      });
      setGraph({ nodes, edges });
      setLive(true); setApiError(null);
    }).catch((e) => {
      setApiError(e.message || String(e));
    });
  }, []);

  // ───── 多重过滤 ─────
  const filteredNodes = (() => {
    let ns = graph.nodes;
    if (hideIsolated) ns = ns.filter((n) => (n.degree || 0) > 0);
    if (minDegree > 0) ns = ns.filter((n) => (n.degree || 0) >= minDegree);
    if (typeFilter) ns = ns.filter((n) => n.type === typeFilter);
    if (searchTerm.trim()) {
      const t = searchTerm.toLowerCase();
      ns = ns.filter((n) => n.name?.toLowerCase().includes(t));
    }
    // 按度数倒序,取 top N
    ns = [...ns].sort((a, b) => (b.degree || 0) - (a.degree || 0)).slice(0, topN);
    return ns;
  })();

  // 只保留与 filteredNodes 都相关的边
  const filteredNodeIds = new Set(filteredNodes.map((n) => n.entity_id));
  const filteredEdges = graph.edges.filter(
    (e) => filteredNodeIds.has(e.source) && filteredNodeIds.has(e.target)
  );

  const isolatedCount = graph.nodes.filter((n) => (n.degree || 0) === 0).length;

  const selEdges = sel
    ? graph.edges.filter((e) => e.source === sel.entity_id || e.target === sel.entity_id)
    : [];
  const selNeighbors = sel
    ? selEdges.map((e) => {
        const otherId = e.source === sel.entity_id ? e.target : e.source;
        const other = graph.nodes.find((n) => n.entity_id === otherId);
        return { edge: e, node: other || { entity_id: otherId, name: otherId.slice(0, 12), type: "?" } };
      })
    : [];

  // 统计每个 type 的节点数(用于 legend)
  const typeCounts = filteredNodes.reduce((m, n) => {
    m[n.type] = (m[n.type] || 0) + 1; return m;
  }, {});
  const presentTypes = Object.keys(typeCounts).sort();
  // 全量类型(用于过滤按钮)
  const presentTypesAll = Array.from(new Set(graph.nodes.map((n) => n.type).filter(Boolean))).sort();

  return (
    <>
      {/* 顶栏 */}
      <div className="row" style={{ marginBottom: 10, gap: 10 }}>
        <div style={{ flex: 1, position: "relative" }}>
          <input
            className="input"
            placeholder="搜索节点…"
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
            style={{ paddingLeft: 34 }}
          />
          <span style={{ position: "absolute", left: 12, top: "50%", transform: "translateY(-50%)", color: "var(--ink-3)" }}>
            <IconSearch />
          </span>
        </div>
        <span className="muted tabular" style={{ fontSize: 13, whiteSpace: "nowrap" }}>
          {graph.nodes.length > 0
            ? `${filteredNodes.length} / ${graph.nodes.length} 实体 · ${filteredEdges.length} / ${graph.edges.length} 关系`
            : apiError ? "连接失败" : "图谱为空"}
        </span>
        {live && !apiError && graph.nodes.length > 0 && (
          <span className="badge d1"><span className="dot" />实时</span>
        )}
      </div>

      {/* 过滤面板 */}
      {graph.nodes.length > 0 && (
        <div className="card" style={{ padding: "12px 16px", marginBottom: 12 }}>
          <div className="row" style={{ gap: 16, flexWrap: "wrap" }}>
            <label className="row" style={{ gap: 6, fontSize: 12.5, cursor: "pointer" }}>
              <input type="checkbox" checked={hideIsolated}
                     onChange={(e) => setHideIsolated(e.target.checked)} />
              <span>隐藏孤立节点</span>
              {isolatedCount > 0 && (
                <span className="muted tabular">({isolatedCount} 个无关系)</span>
              )}
            </label>

            <div className="row" style={{ gap: 6, fontSize: 12.5 }}>
              <span>最低度数</span>
              <select className="select" value={minDegree}
                      onChange={(e) => setMinDegree(Number(e.target.value))}
                      style={{ height: 28, padding: "0 8px", fontSize: 12.5, width: 60 }}>
                {[0, 1, 2, 3, 5, 10].map((v) => <option key={v} value={v}>≥{v}</option>)}
              </select>
            </div>

            <div className="row" style={{ gap: 6, fontSize: 12.5 }}>
              <span>显示前</span>
              <select className="select" value={topN}
                      onChange={(e) => setTopN(Number(e.target.value))}
                      style={{ height: 28, padding: "0 8px", fontSize: 12.5, width: 78 }}>
                {[30, 50, 80, 150, 300].map((v) => <option key={v} value={v}>{v}</option>)}
              </select>
              <span>个</span>
            </div>

            {presentTypesAll.length > 0 && (
              <div className="row" style={{ gap: 4, fontSize: 12.5 }}>
                <span>类型</span>
                <button className={`badge ${!typeFilter ? "d1" : ""}`}
                        style={{ cursor: "pointer" }} onClick={() => setTypeFilter(null)}>全部</button>
                {presentTypesAll.map((t) => (
                  <button key={t} className="badge"
                          style={{
                            cursor: "pointer",
                            background: typeFilter === t ? `${TYPE_META[t]?.color}1A` : "var(--surface)",
                            color: typeFilter === t ? TYPE_META[t]?.color : "var(--ink-2)",
                            borderColor: typeFilter === t ? `${TYPE_META[t]?.color}55` : "var(--line)",
                          }}
                          onClick={() => setTypeFilter(typeFilter === t ? null : t)}>
                    {TYPE_META[t]?.label || t}
                  </button>
                ))}
              </div>
            )}
          </div>
        </div>
      )}

      {/* 3D 图谱 + 悬浮 legend / hover card */}
      {graph.nodes.length === 0 ? (
        <div className="card" style={{ textAlign: "center", color: "var(--ink-3)", padding: 60 }}>
          {apiError ? `服务不可用: ${apiError}` : "知识图谱中没有实体。请用 D2 深度编译文档。"}
        </div>
      ) : (
        <div className="graph-wrap" style={{ marginBottom: 14 }}
             onMouseLeave={() => setHover(null)}>
          {/* 左上角图例 */}
          <div className="graph-legend">
            <div className="legend-title">节点类型</div>
            {presentTypes.map((t) => (
              <div key={t} className="legend-item">
                <span className="legend-dot" style={{ background: TYPE_META[t]?.color || "#A78BFA" }} />
                <span style={{ flex: 1 }}>{TYPE_META[t]?.label || t}</span>
                <span className="mono" style={{ color: "var(--ink-3)" }}>{typeCounts[t]}</span>
              </div>
            ))}
          </div>

          {/* hover 卡片 (跟随鼠标) */}
          {hover && hover.node && (
            <div className="graph-hover-card"
                 style={{ left: Math.min(hover.x + 16, (window.innerWidth - 600)), top: Math.max(8, hover.y - 64) }}>
              <div className="hc-name">{hover.node.name}</div>
              <div className="hc-type">{TYPE_META[hover.node.type]?.label || hover.node.type}</div>
              {hover.node.degree != null && (
                <div className="hc-degree">度数 · {hover.node.degree}</div>
              )}
            </div>
          )}

          <div className="graph-container" style={{ width: "100%", height: 520 }}>
            <GraphCanvas
              nodes={filteredNodes}
              edges={filteredEdges}
              onSelect={(n) => { setSel(n); setSearchTerm(""); }}
              onHover={(n, ev) => {
                if (n && ev) setHover({ node: n, x: ev.clientX || 0, y: ev.clientY || 0 });
                else setHover(null);
              }}
              height={520}
            />
          </div>
        </div>
      )}

      {/* 选中节点详情 */}
      {sel && (
        <div className="card" style={{ marginBottom: 14 }}>
          <div className="card-header">
            <div className="row" style={{ gap: 10 }}>
              <span className="badge" style={{
                background: `${TYPE_META[sel.type]?.color || "#A78BFA"}1A`,
                color: TYPE_META[sel.type]?.color || "var(--ink-2)",
                borderColor: `${TYPE_META[sel.type]?.color || "#A78BFA"}55`,
              }}>
                {TYPE_META[sel.type]?.label || sel.type}
              </span>
              <div className="card-title">{sel.name}</div>
            </div>
            <button className="btn ghost sm" onClick={() => setSel(null)}>关闭</button>
          </div>

          <div className="sub mono" style={{ marginBottom: 12, color: "var(--ink-3)" }}>{sel.entity_id}</div>

          {selNeighbors.length > 0 ? (
            <>
              <label className="label">关联关系 · {selNeighbors.length} 条</label>
              <div className="list">
                {selNeighbors.map(({ edge, node }, i) => (
                  <div key={i} className="list-row" style={{ cursor: "pointer" }} onClick={() => setSel(node)}>
                    <span className="badge" style={{
                      background: `${TYPE_META[node.type]?.color || "#A78BFA"}1A`,
                      color: TYPE_META[node.type]?.color || "var(--ink-2)",
                      borderColor: `${TYPE_META[node.type]?.color || "#A78BFA"}55`,
                    }}>
                      {TYPE_META[node.type]?.label || node.type}
                    </span>
                    <div className="grow">
                      <div className="title">{node.name}</div>
                    </div>
                    <span className="cite">{edge.relation || "—"}</span>
                  </div>
                ))}
              </div>
            </>
          ) : (
            <div className="muted">该实体没有关联关系</div>
          )}
        </div>
      )}

      {/* 导入 */}
      <div className="card">
        <label className="label">导入图数据(可选)</label>
        <textarea className="input" rows={2} value={raw} onChange={(e) => setRaw(e.target.value)}
                  placeholder='{"nodes":[…],"edges":[…]}' />
        <div className="row" style={{ marginTop: 10 }}>
          <button className="btn ghost" onClick={() => {
            try { const g = JSON.parse(raw); setGraph(g); setSel(null); }
            catch { alert("JSON 解析失败"); }
          }}>载入</button>
        </div>
      </div>
    </>
  );
}
