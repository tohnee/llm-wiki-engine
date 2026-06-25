import React, { useState, useEffect, useMemo } from "react";
import { api } from "../api.js";
import { Provenance } from "../components/Citation.jsx";
import {
  LineChart, Line, BarChart, Bar,
  XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer, Area, AreaChart,
} from "recharts";

const DEMO = {
  documents: 12, entities: 340, relations: 512, facts: 1180,
  ambiguous_facts: 47, ambiguous_ratio: 0.04, orphan_entities: 23,
  hubs: [
    { name: "项目 X",   degree: 38 },
    { name: "供应商 A", degree: 21 },
    { name: "预算",     degree: 17 },
    { name: "合同 2026", degree: 12 },
    { name: "组织 B",   degree: 9  },
  ],
};

/** 生成最近 14 天 mock 趋势数据(供 Recharts 渲染) */
function makeTrendData(seedFacts) {
  const today = new Date();
  return Array.from({ length: 14 }, (_, i) => {
    const d = new Date(today.getTime() - (13 - i) * 86400000);
    const dayLabel = `${d.getMonth() + 1}/${d.getDate()}`;
    const growth = Math.round(seedFacts * (0.5 + i / 14 * 0.5));
    const noise = Math.floor(Math.random() * 15) - 7;
    return {
      day: dayLabel,
      facts: growth + noise,
      entities: Math.round(growth * 0.32) + Math.floor(Math.random() * 5),
      ambiguous: Math.max(0, Math.round(growth * 0.04) + Math.floor(Math.random() * 3) - 1),
    };
  });
}

export default function Health() {
  const [s, setS] = useState(DEMO);
  const [raw, setRaw] = useState("");
  const [ambiguous, setAmbiguous] = useState([]);

  async function loadAmbiguous() {
    try { const r = await api.ambiguousFacts(); setAmbiguous(r.facts || []); } catch {}
  }

  useEffect(() => {
    api.status().then((d) => { if (d && typeof d.entities === "number") setS({ ...DEMO, ...d }); })
      .catch(() => {});
    loadAmbiguous();
  }, []);

  async function resolveFact(fact_id, action) {
    try {
      await api.resolveFact(fact_id, { action });
      setAmbiguous((xs) => xs.filter((x) => x.fact_id !== fact_id));
    } catch (e) { alert("处理失败: " + e.message); }
  }

  const trend = useMemo(() => makeTrendData(s.facts || 100), [s.facts]);
  const hubData = useMemo(() => (s.hubs || []).slice(0, 5).map((h) => ({ name: h.name, degree: h.degree })), [s.hubs]);
  const ambColor = s.ambiguous_ratio > 0.15 ? "var(--danger)" : s.ambiguous_ratio > 0.08 ? "var(--warn)" : "var(--success)";

  return (
    <>
      {/* KPI 卡 */}
      <div className="stat-grid">
        <div className="stat"><div className="n tabular">{s.documents}</div><div className="k">文档</div><div className="delta up tabular">+2 本周</div></div>
        <div className="stat"><div className="n tabular">{s.entities}</div><div className="k">实体</div><div className="delta up tabular">+18 本周</div></div>
        <div className="stat"><div className="n tabular">{s.relations}</div><div className="k">关系</div><div className="delta up tabular">+34 本周</div></div>
        <div className="stat"><div className="n tabular">{s.facts}</div><div className="k">事实</div><div className="delta up tabular">+92 本周</div></div>
      </div>

      {/* 趋势折线 */}
      <div className="card chart-card" style={{ marginTop: 18 }}>
        <div className="chart-title">📈 知识增长趋势 · 最近 14 天</div>
        <div className="chart-desc">每日累计的事实、实体与未消歧的矛盾事实数</div>
        <ResponsiveContainer width="100%" height={260}>
          <AreaChart data={trend} margin={{ top: 8, right: 16, left: -8, bottom: 0 }}>
            <defs>
              <linearGradient id="gradFacts" x1="0" y1="0" x2="0" y2="1">
                <stop offset="5%" stopColor="#CC785C" stopOpacity={0.32}/>
                <stop offset="95%" stopColor="#CC785C" stopOpacity={0}/>
              </linearGradient>
              <linearGradient id="gradEnts" x1="0" y1="0" x2="0" y2="1">
                <stop offset="5%" stopColor="#10A37F" stopOpacity={0.28}/>
                <stop offset="95%" stopColor="#10A37F" stopOpacity={0}/>
              </linearGradient>
            </defs>
            <CartesianGrid strokeDasharray="3 3" vertical={false} />
            <XAxis dataKey="day" tickLine={false} axisLine={{ stroke: "#E8E5DE" }} />
            <YAxis tickLine={false} axisLine={false} />
            <Tooltip />
            <Legend iconType="circle" wrapperStyle={{ paddingTop: 8 }} />
            <Area type="monotone" name="事实"   dataKey="facts"    stroke="#CC785C" strokeWidth={2} fill="url(#gradFacts)" />
            <Area type="monotone" name="实体"   dataKey="entities" stroke="#10A37F" strokeWidth={2} fill="url(#gradEnts)" />
            <Line type="monotone" name="矛盾事实" dataKey="ambiguous" stroke="#D97706" strokeWidth={2} dot={false} />
          </AreaChart>
        </ResponsiveContainer>
      </div>

      {/* Hub 柱状 + 健康指标 */}
      <div style={{ display: "grid", gridTemplateColumns: "minmax(0, 1.4fr) 1fr", gap: 16, marginTop: 16 }}>
        <div className="card chart-card">
          <div className="chart-title">🌐 Hub 实体度数</div>
          <div className="chart-desc">度数最高的节点错误传播面最大,优先维护</div>
          <ResponsiveContainer width="100%" height={220}>
            <BarChart data={hubData} layout="vertical" margin={{ top: 8, right: 24, left: 8, bottom: 0 }}>
              <CartesianGrid strokeDasharray="3 3" horizontal={false} />
              <XAxis type="number" tickLine={false} axisLine={false} />
              <YAxis type="category" dataKey="name" tickLine={false} axisLine={false} width={84} />
              <Tooltip cursor={{ fill: "rgba(204, 120, 92, 0.08)" }} />
              <Bar dataKey="degree" name="度数" fill="#CC785C" radius={[0, 6, 6, 0]} barSize={18} />
            </BarChart>
          </ResponsiveContainer>
        </div>

        <div className="card chart-card">
          <div className="chart-title">🩺 知识健康</div>
          <div className="chart-desc">关键质量指标</div>
          <div style={{ display: "flex", flexDirection: "column", gap: 14, marginTop: 4 }}>
            <div>
              <div className="muted">矛盾事实比例</div>
              <div className="tabular" style={{ fontSize: 26, fontWeight: 600, color: ambColor, letterSpacing: "-0.02em" }}>
                {Math.round((s.ambiguous_ratio || 0) * 100)}%
              </div>
              <div className="muted" style={{ fontSize: 11.5 }}>{s.ambiguous_facts} / {s.facts} 条事实未消歧</div>
            </div>
            <div>
              <div className="muted">孤立实体(无关系)</div>
              <div className="tabular" style={{ fontSize: 26, fontWeight: 600, letterSpacing: "-0.02em" }}>
                {s.orphan_entities}
              </div>
              <div className="muted" style={{ fontSize: 11.5 }}>约占 {Math.round(((s.orphan_entities || 0) / Math.max(1, s.entities)) * 100)}%</div>
            </div>
          </div>
        </div>
      </div>

      <div className="card" style={{ marginTop: 16 }}>
        <div className="card-header">
          <div>
            <div className="card-title">矛盾事实待确认</div>
            <div className="card-desc">用户确认后会写回 facts,不再只停留在健康报表中</div>
          </div>
          <button className="btn ghost sm" onClick={loadAmbiguous}>刷新</button>
        </div>
        <div className="list">
          {ambiguous.length === 0 && <div className="muted" style={{ padding: 12 }}>当前没有待确认矛盾事实</div>}
          {ambiguous.map((f) => (
            <div className="list-row" key={f.fact_id}>
              <span className="badge warn">ambiguous</span>
              <div className="grow">
                <div className="title">{f.subject_entity} · {f.predicate} · {f.object_value}</div>
                <div className="sub mono">{f.fact_id} · source spans {(f.source_span_ids || []).join(", ") || "—"}</div>
              </div>
              <button className="btn ghost sm" onClick={() => resolveFact(f.fact_id, "confirm")}>确认保留</button>
              <button className="btn subtle sm" onClick={() => resolveFact(f.fact_id, "reject")}>标记过时</button>
            </div>
          ))}
        </div>
      </div>

      {/* 溯源图例 + 载入数据 */}
      <div className="card" style={{ marginTop: 16 }}>
        <div className="card-title" style={{ marginBottom: 12 }}>溯源图例</div>
        <div className="row" style={{ gap: 20 }}>
          <Provenance kind="extracted" />
          <Provenance kind="inferred" />
          <Provenance kind="ambiguous" />
        </div>
      </div>

      <div className="card" style={{ marginTop: 12 }}>
        <label className="label">载入实时数据 · 粘贴 <span className="mono">GET /status</span> 响应</label>
        <textarea className="input" rows={3} value={raw} onChange={(e) => setRaw(e.target.value)}
                  placeholder='{"documents":12,"entities":340,…}' />
        <div className="row" style={{ marginTop: 10 }}>
          <button className="btn ghost" onClick={() => { try { setS({ ...DEMO, ...JSON.parse(raw) }); } catch { alert("JSON 无效"); } }}>
            载入
          </button>
          <button className="btn subtle" onClick={() => { setS(DEMO); setRaw(""); }}>
            重置为演示数据
          </button>
        </div>
      </div>
    </>
  );
}
