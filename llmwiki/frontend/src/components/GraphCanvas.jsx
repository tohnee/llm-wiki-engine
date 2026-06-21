import React from "react";
import ForceGraph3D from "react-force-graph-3d";

// 节点颜色映射(按 type),与 CSS 变量对齐
const TYPE_COLORS = {
  project: "#7C5CFC",
  person: "#2DD4BF",
  org: "#FB923C",
  concept: "#60A5FA",
  event: "#F472B6",
  default: "#A78BFA",
};

function nodeColor(n) {
  return TYPE_COLORS[n.type] || TYPE_COLORS.default;
}

export default function GraphCanvas({ nodes = [], edges = [], onSelect, width, height }) {
  // react-force-graph-3d 需要节点有 id 字段
  const gData = {
    nodes: nodes.map((n) => ({ ...n, id: n.entity_id })),
    links: edges.map((e) => ({ source: e.source, target: e.target, relation: e.relation })),
  };

  return (
    <ForceGraph3D
      graphData={gData}
      width={width}
      height={height}
      backgroundColor="rgba(0,0,0,0)"
      nodeColor={nodeColor}
      nodeLabel={(n) => `${n.name} (${n.type})`}
      linkLabel={(l) => l.relation || ""}
      linkColor={() => "rgba(255,255,255,0.15)"}
      linkWidth={0.5}
      nodeRelSize={6}
      linkDirectionalParticles={1}
      linkDirectionalParticleSpeed={0.005}
      linkDirectionalParticleColor={() => "rgba(124,92,252,0.5)"}
      onNodeClick={(n) => onSelect && onSelect(n)}
      d3AlphaDecay={0.02}
      d3VelocityDecay={0.3}
      warmupTicks={40}
      cooldownTicks={60}
    />
  );
}
