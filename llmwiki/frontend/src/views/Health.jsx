import React, { useState, useEffect } from "react";
import { api } from "../api.js";
import { Provenance } from "../components/Citation.jsx";

// 健康面板:展示 /status 的知识库洞察。经查询网关需透传 /status;
// 为前端可独立运行,支持手动载入演示数据。生产由 query 网关加 /status 透传。
const DEMO = {
  documents: 12, entities: 340, relations: 512, facts: 1180,
  ambiguous_facts: 47, ambiguous_ratio: 0.04, orphan_entities: 23,
  hubs: [
    { name: "项目X", degree: 38 }, { name: "供应商A", degree: 21 },
    { name: "预算", degree: 17 }, { name: "合同2026", degree: 12 },
  ],
};

export default function Health() {
  const [s, setS] = useState(DEMO);
  const [raw, setRaw] = useState("");

  useEffect(() => {
    api.status().then((d) => { if (d && typeof d.entities === "number") setS({ ...DEMO, ...d }); })
      .catch(() => {/* 用演示数据 */});
  }, []);

  return (
    <>
      <div className="stat-grid">
        <div className="stat"><div className="n">{s.documents}</div><div className="k">文档</div></div>
        <div className="stat"><div className="n">{s.entities}</div><div className="k">实体</div></div>
        <div className="stat"><div className="n">{s.relations}</div><div className="k">关系</div></div>
        <div className="stat"><div className="n">{s.facts}</div><div className="k">事实</div></div>
      </div>

      <div className="card" style={{ marginTop: 18 }}>
        <div className="title" style={{ fontWeight: 650, marginBottom: 10 }}>知识健康</div>
        <div className="row" style={{ gap: 24, flexWrap: "wrap" }}>
          <div>
            <div className="muted">矛盾事实比例</div>
            <div style={{ fontSize: 20, fontWeight: 650,
              color: s.ambiguous_ratio > 0.15 ? "var(--prov-ambiguous)" : "var(--prov-extracted)" }}>
              {Math.round(s.ambiguous_ratio * 100)}%
            </div>
          </div>
          <div>
            <div className="muted">孤立实体(无关系)</div>
            <div style={{ fontSize: 20, fontWeight: 650 }}>{s.orphan_entities}</div>
          </div>
        </div>
        <div style={{ marginTop: 14 }}>
          <div className="muted" style={{ marginBottom: 6 }}>Hub 实体(度数最高,错误传播面最大,优先维护)</div>
          <div className="list">
            {s.hubs.map((h, i) => (
              <div className="list-row" key={i} style={{ padding: "8px 12px" }}>
                <span className="grow title">{h.name}</span>
                <span className="badge mono">deg {h.degree}</span>
              </div>
            ))}
          </div>
        </div>
      </div>

      <div className="card" style={{ marginTop: 14 }}>
        <div className="title" style={{ fontWeight: 650, marginBottom: 8 }}>溯源图例</div>
        <div className="row" style={{ gap: 20 }}>
          <Provenance kind="extracted" /><Provenance kind="inferred" /><Provenance kind="ambiguous" />
        </div>
      </div>

      <div className="card" style={{ marginTop: 14 }}>
        <label className="label">载入实时数据 — 粘贴 evidence <span className="mono">GET /status</span> 响应</label>
        <textarea className="input" rows={3} value={raw} onChange={(e) => setRaw(e.target.value)} />
        <div style={{ height: 10 }} />
        <button className="btn ghost" onClick={() => { try { setS(JSON.parse(raw)); } catch { alert("JSON 无效"); } }}>载入</button>
      </div>
    </>
  );
}
