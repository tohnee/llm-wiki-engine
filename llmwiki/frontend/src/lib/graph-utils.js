/**
 * graph-utils.js — 知识图谱纯逻辑(无 React 依赖,易测试)
 * 从 Graph.jsx 抽离,实现数据处理与渲染解耦。
 */

/** 节点类型 → 中文标签 + 颜色 */
export const TYPE_META = {
  project: { label: "项目", color: "#CC785C" },
  product: { label: "产品", color: "#CC785C" },
  person:  { label: "人员", color: "#10A37F" },
  org:     { label: "组织", color: "#2563EB" },
  concept: { label: "概念", color: "#8B5CF6" },
  event:   { label: "事件", color: "#EC4899" },
};

/**
 * 解析后端返回的图数据为统一的 {nodes, edges} 结构,并计算节点度数。
 * 兼容: 直接 {nodes,edges} / {data:{...}} / {data:"json字符串"}
 */
export function parseGraphResponse(r) {
  let g = typeof r?.data === "string" ? JSON.parse(r.data) : r;
  const gd = (g && g.nodes) ? g : (g && g.data ? g.data : { nodes: [], edges: [] });

  const edges = (gd.edges || []).map((e) => ({
    source: e.source,
    target: e.target,
    relation: e.relation_type || e.relation || "",
  }));

  // 计算每个节点的真实度数
  const degMap = {};
  edges.forEach((e) => {
    degMap[e.source] = (degMap[e.source] || 0) + 1;
    degMap[e.target] = (degMap[e.target] || 0) + 1;
  });

  const nodes = (gd.nodes || []).map((n) => {
    const id = n.id || n.entity_id;
    return { entity_id: id, name: n.name, type: n.type, degree: degMap[id] || 0 };
  });

  return { nodes, edges };
}

/**
 * 多重过滤 + 按度数排序取 topN。
 * options: { hideIsolated, minDegree, typeFilter, searchTerm, topN }
 */
export function filterNodes(nodes, options = {}) {
  const { hideIsolated = false, minDegree = 0, typeFilter = null, searchTerm = "", topN = 80 } = options;
  let ns = nodes;
  if (hideIsolated) ns = ns.filter((n) => (n.degree || 0) > 0);
  if (minDegree > 0) ns = ns.filter((n) => (n.degree || 0) >= minDegree);
  if (typeFilter) ns = ns.filter((n) => n.type === typeFilter);
  if (searchTerm.trim()) {
    const t = searchTerm.toLowerCase();
    ns = ns.filter((n) => n.name?.toLowerCase().includes(t));
  }
  return [...ns].sort((a, b) => (b.degree || 0) - (a.degree || 0)).slice(0, topN);
}

/** 只保留两端都在 visibleNodes 内的边 */
export function filterEdges(edges, visibleNodes) {
  const idSet = new Set(visibleNodes.map((n) => n.entity_id));
  return edges.filter((e) => idSet.has(e.source) && idSet.has(e.target));
}

/** 求某节点的邻居(含边信息) */
export function neighborsOf(node, nodes, edges) {
  if (!node) return [];
  const related = edges.filter((e) => e.source === node.entity_id || e.target === node.entity_id);
  return related.map((e) => {
    const otherId = e.source === node.entity_id ? e.target : e.source;
    const other = nodes.find((n) => n.entity_id === otherId);
    return { edge: e, node: other || { entity_id: otherId, name: otherId.slice(0, 12), type: "?" } };
  });
}

/** 统计各类型节点数 */
export function countByType(nodes) {
  return nodes.reduce((m, n) => { m[n.type] = (m[n.type] || 0) + 1; return m; }, {});
}
