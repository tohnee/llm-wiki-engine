import { describe, it, expect } from "vitest";
import {
  parseGraphResponse, filterNodes, filterEdges, neighborsOf, countByType, countByRelation, TYPE_META, RELATION_META, normalizeRelation,
} from "../lib/graph-utils.js";

describe("graph-utils: parseGraphResponse", () => {
  it("解析直接 {nodes,edges} 结构", () => {
    const r = {
      nodes: [{ entity_id: "a", name: "A", type: "project" }, { entity_id: "b", name: "B", type: "person" }],
      edges: [{ source: "a", target: "b", relation: "owns" }],
    };
    const { nodes, edges } = parseGraphResponse(r);
    expect(nodes).toHaveLength(2);
    expect(edges).toHaveLength(1);
    expect(edges[0].relation).toBe("owns");
  });

  it("计算节点度数", () => {
    const r = {
      nodes: [{ entity_id: "a" }, { entity_id: "b" }, { entity_id: "c" }],
      edges: [{ source: "a", target: "b" }, { source: "a", target: "c" }],
    };
    const { nodes } = parseGraphResponse(r);
    expect(nodes.find((n) => n.entity_id === "a").degree).toBe(2);
    expect(nodes.find((n) => n.entity_id === "b").degree).toBe(1);
  });

  it("兼容 data 字符串包装", () => {
    const r = { data: JSON.stringify({ nodes: [{ entity_id: "x", name: "X" }], edges: [] }) };
    const { nodes } = parseGraphResponse(r);
    expect(nodes).toHaveLength(1);
    expect(nodes[0].name).toBe("X");
  });

  it("relation_type 优先于 relation", () => {
    const r = { nodes: [{ entity_id: "a" }, { entity_id: "b" }], edges: [{ source: "a", target: "b", relation_type: "depends_on" }] };
    const { edges } = parseGraphResponse(r);
    expect(edges[0].relation).toBe("depends_on");
    expect(RELATION_META.depends_on.label).toBe("depends on");
  });

  it("空数据不崩溃", () => {
    expect(parseGraphResponse({}).nodes).toEqual([]);
    expect(parseGraphResponse({ nodes: [], edges: [] }).edges).toEqual([]);
  });
});

describe("graph-utils: filterNodes", () => {
  const nodes = [
    { entity_id: "a", name: "Alpha", type: "project", degree: 5 },
    { entity_id: "b", name: "Beta", type: "person", degree: 0 },
    { entity_id: "c", name: "Gamma", type: "project", degree: 2 },
  ];

  it("hideIsolated 过滤度数为 0 的节点", () => {
    const r = filterNodes(nodes, { hideIsolated: true });
    expect(r.map((n) => n.entity_id)).toEqual(["a", "c"]);
  });

  it("minDegree 阈值过滤", () => {
    expect(filterNodes(nodes, { minDegree: 3 }).map((n) => n.entity_id)).toEqual(["a"]);
  });

  it("typeFilter 按类型过滤", () => {
    expect(filterNodes(nodes, { typeFilter: "project" })).toHaveLength(2);
  });

  it("searchTerm 大小写不敏感", () => {
    expect(filterNodes(nodes, { searchTerm: "alph" })).toHaveLength(1);
    expect(filterNodes(nodes, { searchTerm: "ALPHA" })).toHaveLength(1);
  });

  it("按度数倒序取 topN", () => {
    const r = filterNodes(nodes, { topN: 2 });
    expect(r.map((n) => n.entity_id)).toEqual(["a", "c"]); // 度数 5,2
  });

  it("默认不过滤孤立节点(回归: 避免全部消失)", () => {
    expect(filterNodes(nodes, {})).toHaveLength(3);
  });
});

describe("graph-utils: filterEdges", () => {
  it("只保留两端可见的边", () => {
    const edges = [{ source: "a", target: "b" }, { source: "a", target: "z" }];
    const visible = [{ entity_id: "a" }, { entity_id: "b" }];
    const r = filterEdges(edges, visible);
    expect(r).toHaveLength(1);
    expect(r[0].target).toBe("b");
  });

  it("支持 typed relation 过滤", () => {
    const edges = [{ source: "a", target: "b", relation: "depends_on" }, { source: "a", target: "b", relation: "uses" }];
    const visible = [{ entity_id: "a" }, { entity_id: "b" }];
    const r = filterEdges(edges, visible, "depends_on");
    expect(r).toHaveLength(1);
    expect(r[0].relation).toBe("depends_on");
  });
});

describe("graph-utils: neighborsOf", () => {
  const nodes = [
    { entity_id: "a", name: "A", type: "project" },
    { entity_id: "b", name: "B", type: "person" },
  ];
  const edges = [{ source: "a", target: "b", relation: "owns" }];

  it("返回选中节点的邻居", () => {
    const r = neighborsOf(nodes[0], nodes, edges);
    expect(r).toHaveLength(1);
    expect(r[0].node.entity_id).toBe("b");
    expect(r[0].edge.relation).toBe("owns");
  });

  it("无节点返回空", () => {
    expect(neighborsOf(null, nodes, edges)).toEqual([]);
  });

  it("邻居不存在时降级", () => {
    const r = neighborsOf(nodes[0], [nodes[0]], [{ source: "a", target: "ghost" }]);
    expect(r[0].node.entity_id).toBe("ghost");
  });
});

describe("graph-utils: countByType + TYPE_META", () => {
  it("统计各类型数量", () => {
    const c = countByType([{ type: "project" }, { type: "project" }, { type: "person" }]);
    expect(c).toEqual({ project: 2, person: 1 });
  });

  it("TYPE_META 覆盖核心类型", () => {
    expect(TYPE_META.project.label).toBe("项目");
    expect(TYPE_META.person.color).toBe("#10A37F");
  });
});


describe("graph-utils: typed relations", () => {
  it("normalizeRelation fallback + relation counts", () => {
    expect(normalizeRelation("depends on")).toBe("depends_on");
    expect(normalizeRelation("unknown_relation")).toBe("unknown_relation");
    expect(countByRelation([{ relation: "uses" }, { relation: "uses" }, { relation: "fixed_by" }])).toEqual({ uses: 2, fixed_by: 1 });
  });
});
