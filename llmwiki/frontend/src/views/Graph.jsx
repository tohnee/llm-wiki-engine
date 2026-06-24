import React, { useState, useEffect } from "react";
import { api } from "../api.js";
import GraphCanvas from "../components/GraphCanvas.jsx";
import {
  TYPE_META, RELATION_META, parseGraphResponse, filterNodes, filterEdges, neighborsOf, countByType, countByRelation,
} from "../lib/graph-utils.js";

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
  const [relationFilter, setRelationFilter] = useState(null); // 按 typed relation 过滤
  const [topN, setTopN] = useState(80);                     // 最多显示 N 个节点(按度数)

  useEffect(() => {
    api.graph("json").then((r) => {
      setGraph(parseGraphResponse(r));
      setLive(true); setApiError(null);
    }).catch((e) => {
      setApiError(e.message || String(e));
    });
  }, []);

  // ───── 多重过滤(用已测试的纯函数) ─────
  const filteredNodes = filterNodes(graph.nodes, { hideIsolated, minDegree, typeFilter, searchTerm, topN });
  const filteredEdges = filterEdges(graph.edges, filteredNodes, relationFilter);
  const isolatedCount = graph.nodes.filter((n) => (n.degree || 0) === 0).length;

  const selNeighbors = neighborsOf(sel, graph.nodes, graph.edges);

  // 统计各类型节点数
  const typeCounts = countByType(filteredNodes);
  const relationCounts = countByRelation(graph.edges);
  const presentRelations = Object.keys(relationCounts).sort();
  const presentTypes = Object.keys(typeCounts).sort();
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


            {presentRelations.length > 0 && (
              <div className="row" style={{ gap: 4, fontSize: 12.5 }}>
                <span>关系</span>
                <button className={`badge ${!relationFilter ? "d1" : ""}`}
                        style={{ cursor: "pointer" }} onClick={() => setRelationFilter(null)}>全部</button>
                {presentRelations.map((r) => (
                  <button key={r} className="badge relation-badge"
                          style={{
                            cursor: "pointer",
                            background: relationFilter === r ? `${RELATION_META[r]?.color || "#8A8780"}1A` : "var(--surface)",
                            color: relationFilter === r ? RELATION_META[r]?.color : "var(--ink-2)",
                            borderColor: relationFilter === r ? `${RELATION_META[r]?.color || "#8A8780"}55` : "var(--line)",
                          }}
                          onClick={() => setRelationFilter(relationFilter === r ? null : r)}>
                    {RELATION_META[r]?.label || r} · {relationCounts[r]}
                  </button>
                ))}
              </div>
            )}

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
                    <span className="cite relation-chip" style={{ borderColor: `${RELATION_META[edge.relation]?.color || "#8A8780"}55`, color: RELATION_META[edge.relation]?.color || "var(--ink-2)" }}>{RELATION_META[edge.relation]?.label || edge.relation || "—"}</span>
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
