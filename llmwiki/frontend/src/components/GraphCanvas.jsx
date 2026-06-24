import React, { useRef, useEffect } from "react";
import ForceGraph3D from "react-force-graph-3d";

/** 节点颜色映射 (与 Graph 视图 TYPE_META 保持一致) */
const TYPE_COLORS = {
  project: "#CC785C",
  product: "#CC785C",
  person:  "#10A37F",
  org:     "#2563EB",
  concept: "#8B5CF6",
  event:   "#EC4899",
  default: "#A78BFA",
};
function nodeColor(n) { return TYPE_COLORS[n.type] || TYPE_COLORS.default; }

export default function GraphCanvas({ nodes = [], edges = [], onSelect, onHover, width, height }) {
  const fgRef = useRef();

  // 节点 size 按度数缩放
  const nodeSize = (n) => Math.max(4, Math.min(12, 4 + Math.sqrt(n.degree || 0) * 1.5));

  const gData = {
    nodes: nodes.map((n) => ({ ...n, id: n.entity_id, val: nodeSize(n) })),
    links: edges.map((e) => ({ source: e.source, target: e.target, relation: e.relation })),
  };

  // 调整物理布局参数: 加大斥力,缩短链接,让聚类更紧凑
  useEffect(() => {
    if (!fgRef.current) return;
    const fg = fgRef.current;
    try {
      // 节点间斥力(默认 -30,加大让节点不重叠)
      const chargeForce = fg.d3Force("charge");
      if (chargeForce) chargeForce.strength(-80);
      // 链接距离(默认 30,缩短让有关系的节点更紧)
      const linkForce = fg.d3Force("link");
      if (linkForce) linkForce.distance(50);
      // 让图谱稳定收敛
      fg.d3ReheatSimulation();
    } catch {}
  }, [nodes, edges]);

  return (
    <ForceGraph3D
      ref={fgRef}
      graphData={gData}
      width={width}
      height={height}
      backgroundColor="#FFFFFF"
      nodeColor={nodeColor}
      nodeVal={(n) => n.val || 4}
      nodeLabel={(n) => `${n.name} (${n.type}) · 度 ${n.degree || 0}`}
      linkLabel={(l) => l.relation || ""}
      linkColor={() => "rgba(31, 30, 29, 0.22)"}
      linkWidth={0.8}
      linkOpacity={0.5}
      nodeRelSize={5}
      linkDirectionalParticles={1}
      linkDirectionalParticleSpeed={0.005}
      linkDirectionalParticleColor={() => "rgba(204, 120, 92, 0.7)"}
      cooldownTicks={120}
      warmupTicks={20}
      enableNodeDrag={true}
      onNodeClick={(n) => onSelect && onSelect(n)}
      onNodeHover={(n) => {
        if (!onHover) return;
        const ev = (typeof window !== "undefined" && window.event) ? window.event : null;
        onHover(n, ev);
        if (typeof document !== "undefined") {
          document.body.style.cursor = n ? "pointer" : "default";
        }
      }}
    />
  );
}
