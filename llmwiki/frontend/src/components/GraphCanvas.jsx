import React, { useRef, useEffect, useState, useCallback } from "react";

/**
 * GraphCanvas2D — 轻量 2D 力导向图(纯 Canvas,无外部依赖)
 *
 * 替代 react-force-graph-3d,彻底消除 tick 崩溃。
 * 自包含 force simulation: Verlet 积分 + 斥力 + 弹簧 + 中心引力。
 */

const TYPE_COLORS = {
  project: "#CC785C", product: "#CC785C", person: "#10A37F",
  org: "#2563EB", concept: "#8B5CF6", event: "#EC4899", default: "#A78BFA",
};
const RELATION_COLORS = {
  uses: "#10A37F", depends_on: "#2563EB", contradicts: "#DC2626",
  caused_by: "#D97706", fixed_by: "#16A34A", superseded_by: "#8B5CF6",
  references: "#8A8780", related_to: "#B5B2AA", default: "rgba(31,30,29,0.22)",
};

export default function GraphCanvas({ nodes = [], edges = [], onSelect, onHover, width, height }) {
  const canvasRef = useRef(null);
  const containerRef = useRef(null);
  const stateRef = useRef({ positions: new Map(), velocities: new Map(), raf: null, hovered: null, tick: 0 });
  const [measuredWidth, setMeasuredWidth] = useState(width || 800);
  const [ready, setReady] = useState(false);

  const h = height || 500;
  const w = measuredWidth;

  // 测量容器宽度
  useEffect(() => {
    if (width) { setMeasuredWidth(width); setReady(true); return; }
    const el = containerRef.current;
    if (!el) return;
    const update = () => {
      const cw = el.clientWidth;
      if (cw > 0) { setMeasuredWidth(cw); setReady(true); }
    };
    update();
    const ro = new ResizeObserver(update);
    ro.observe(el);
    return () => ro.disconnect();
  }, [width]);

  // 数据清洗
  const nodeIdSet = new Set(nodes.map((n) => n.entity_id || n.id));
  const cleanNodes = nodes.filter((n) => (n.entity_id || n.id));
  const cleanEdges = (edges || []).filter(
    (e) => nodeIdSet.has(e.source) && nodeIdSet.has(e.target)
  );

  // 初始化节点位置(圆形分布)
  useEffect(() => {
    const st = stateRef.current;
    const cx = w / 2, cy = h / 2;
    const r = Math.min(w, h) * 0.35;
    cleanNodes.forEach((n, i) => {
      const id = n.entity_id || n.id;
      if (!st.positions.has(id)) {
        let seed = 0; for (const ch of String(id)) seed = (seed * 31 + ch.charCodeAt(0)) >>> 0;
        const angle = (i / Math.max(1, cleanNodes.length)) * Math.PI * 2 + (seed % 100) / 500;
        const jitter = ((seed % 17) - 8) * 0.8;
        st.positions.set(id, {
          x: cx + Math.cos(angle) * (r + jitter),
          y: cy + Math.sin(angle) * (r + jitter),
        });
        st.velocities.set(id, { x: 0, y: 0 });
      }
    });
    // 清除已不存在的节点
    const validIds = new Set(cleanNodes.map((n) => n.entity_id || n.id));
    for (const id of st.positions.keys()) {
      if (!validIds.has(id)) { st.positions.delete(id); st.velocities.delete(id); }
    }
  }, [cleanNodes, w, h]);

  // 力导向动画
  useEffect(() => {
    if (!ready || !cleanNodes.length) return;
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    const st = stateRef.current;
    const dpr = window.devicePixelRatio || 1;
    canvas.width = w * dpr;
    canvas.height = h * dpr;
    ctx.scale(dpr, dpr);

    const cx = w / 2, cy = h / 2;
    const REPULSION = 800;
    const SPRING = 0.02;
    const SPRING_LEN = 80;
    const CENTER = 0.005;
    const DAMPING = 0.72;
    const MAX_VEL = 10;

    let running = true;
    const pos = st.positions;
    const vel = st.velocities;

    st.tick = 0;
    function tick() {
      if (!running) return;
      st.tick += 1;
      let energy = 0;

      // 斥力(O(n²) 但 452 节点可接受)
      const ids = cleanNodes.map((n) => n.entity_id || n.id);
      for (let i = 0; i < ids.length; i++) {
        const a = pos.get(ids[i]); if (!a) continue;
        let fx = 0, fy = 0;
        for (let j = 0; j < ids.length; j++) {
          if (i === j) continue;
          const b = pos.get(ids[j]); if (!b) continue;
          let dx = a.x - b.x, dy = a.y - b.y;
          let dist2 = dx * dx + dy * dy + 0.01;
          let force = REPULSION / dist2;
          let dist = Math.sqrt(dist2);
          fx += (dx / dist) * force;
          fy += (dy / dist) * force;
        }
        // 中心引力
        fx += (cx - a.x) * CENTER;
        fy += (cy - a.y) * CENTER;
        // 弹簧(边)
        for (const e of cleanEdges) {
          let other = null;
          if (e.source === ids[i]) other = e.target;
          else if (e.target === ids[i]) other = e.source;
          if (!other) continue;
          const b = pos.get(other); if (!b) continue;
          let dx = b.x - a.x, dy = b.y - a.y;
          let dist = Math.sqrt(dx * dx + dy * dy) + 0.01;
          let force = (dist - SPRING_LEN) * SPRING;
          fx += (dx / dist) * force;
          fy += (dy / dist) * force;
        }
        const v = vel.get(ids[i]) || { x: 0, y: 0 };
        v.x = (v.x + fx) * DAMPING;
        v.y = (v.y + fy) * DAMPING;
        if (v.x > MAX_VEL) v.x = MAX_VEL;
        if (v.x < -MAX_VEL) v.x = -MAX_VEL;
        if (v.y > MAX_VEL) v.y = MAX_VEL;
        if (v.y < -MAX_VEL) v.y = -MAX_VEL;
        energy += Math.abs(v.x) + Math.abs(v.y);
      }
      // 应用速度
      for (const id of ids) {
        const p = pos.get(id); const v = vel.get(id); if (!p || !v) continue;
        p.x += v.x; p.y += v.y;
        // 边界
        p.x = Math.max(20, Math.min(w - 20, p.x));
        p.y = Math.max(20, Math.min(h - 20, p.y));
      }
      draw();
      if (st.tick < 360 && energy > 0.08) st.raf = requestAnimationFrame(tick);
    }

    function draw() {
      ctx.clearRect(0, 0, w, h);
      // 画 typed edge:颜色 + 箭头 + 关系标签
      ctx.lineWidth = 1.2;
      ctx.font = "10px JetBrains Mono, monospace";
      for (const e of cleanEdges) {
        const a = pos.get(e.source); const b = pos.get(e.target);
        if (!a || !b) continue;
        const rel = e.relation || e.relation_type || "related_to";
        const color = RELATION_COLORS[rel] || RELATION_COLORS.default;
        ctx.strokeStyle = color;
        ctx.fillStyle = color;
        ctx.beginPath(); ctx.moveTo(a.x, a.y); ctx.lineTo(b.x, b.y); ctx.stroke();
        const ang = Math.atan2(b.y - a.y, b.x - a.x);
        const ax = b.x - Math.cos(ang) * 14, ay = b.y - Math.sin(ang) * 14;
        ctx.beginPath();
        ctx.moveTo(ax, ay);
        ctx.lineTo(ax - Math.cos(ang - 0.45) * 7, ay - Math.sin(ang - 0.45) * 7);
        ctx.lineTo(ax - Math.cos(ang + 0.45) * 7, ay - Math.sin(ang + 0.45) * 7);
        ctx.closePath(); ctx.fill();
        if (rel !== "related_to" && rel !== "references") {
          const mx = (a.x + b.x) / 2, my = (a.y + b.y) / 2;
          ctx.save();
          ctx.globalAlpha = .92;
          ctx.fillStyle = "rgba(255,255,255,.82)";
          const label = rel.replace(/_/g, " ");
          const tw = ctx.measureText(label).width + 10;
          ctx.fillRect(mx - tw / 2, my - 8, tw, 15);
          ctx.fillStyle = color;
          ctx.textAlign = "center";
          ctx.fillText(label, mx, my + 3);
          ctx.restore();
        }
      }
      // 画节点
      for (const n of cleanNodes) {
        const id = n.entity_id || n.id;
        const p = pos.get(id); if (!p) continue;
        const color = TYPE_COLORS[n.type] || TYPE_COLORS.default;
        const deg = n.degree || 0;
        const radius = Math.max(3, Math.min(8, 3 + Math.sqrt(deg) * 1.2));
        const isHovered = st.hovered === id;

        ctx.beginPath();
        ctx.arc(p.x, p.y, radius, 0, Math.PI * 2);
        ctx.fillStyle = color;
        ctx.fill();
        if (isHovered) {
          ctx.strokeStyle = "#1F1E1D";
          ctx.lineWidth = 2;
          ctx.stroke();
        }
        // 名称(仅 hover 或高度数时)
        if (isHovered || deg >= 3) {
          ctx.fillStyle = "#1F1E1D";
          ctx.font = "11px Inter, sans-serif";
          ctx.textAlign = "center";
          ctx.fillText(n.name || id.slice(0, 10), p.x, p.y - radius - 4);
        }
      }
    }

    tick();
    return () => {
      running = false;
      if (st.raf) cancelAnimationFrame(st.raf);
    };
  }, [ready, cleanNodes, cleanEdges, w, h]);

  // 鼠标交互
  const handleMouseMove = useCallback((ev) => {
    const canvas = canvasRef.current; if (!canvas) return;
    const rect = canvas.getBoundingClientRect();
    const mx = ev.clientX - rect.left;
    const my = ev.clientY - rect.top;
    const st = stateRef.current;
    let found = null;
    for (const n of cleanNodes) {
      const id = n.entity_id || n.id;
      const p = st.positions.get(id); if (!p) continue;
      const dx = p.x - mx, dy = p.y - my;
      const r = Math.max(3, Math.min(8, 3 + Math.sqrt(n.degree || 0) * 1.2)) + 4;
      if (dx * dx + dy * dy < r * r) { found = n; break; }
    }
    st.hovered = found ? (found.entity_id || found.id) : null;
    canvas.style.cursor = found ? "pointer" : "default";
    if (onHover) onHover(found, ev);
  }, [cleanNodes, onHover]);

  const handleClick = useCallback((ev) => {
    const canvas = canvasRef.current; if (!canvas) return;
    const rect = canvas.getBoundingClientRect();
    const mx = ev.clientX - rect.left;
    const my = ev.clientY - rect.top;
    const st = stateRef.current;
    for (const n of cleanNodes) {
      const id = n.entity_id || n.id;
      const p = st.positions.get(id); if (!p) continue;
      const dx = p.x - mx, dy = p.y - my;
      const r = Math.max(3, Math.min(8, 3 + Math.sqrt(n.degree || 0) * 1.2)) + 4;
      if (dx * dx + dy * dy < r * r) { onSelect?.(n); break; }
    }
  }, [cleanNodes, onSelect]);

  if (!cleanNodes.length) {
    return (
      <div ref={containerRef} style={{
        width: "100%", height: h, display: "grid", placeItems: "center",
        color: "var(--ink-3)", fontSize: 13.5,
        background: "var(--surface)", border: "1px solid var(--line)", borderRadius: "var(--r-lg)",
      }}>
        图谱中无可见节点。尝试调整过滤条件或入库更多文档。
      </div>
    );
  }

  return (
    <div ref={containerRef} style={{ width: "100%", height: h, position: "relative" }}>
      <canvas
        ref={canvasRef}
        style={{ width: "100%", height: "100%", display: "block", borderRadius: "var(--r-lg)" }}
        onMouseMove={handleMouseMove}
        onMouseLeave={() => { stateRef.current.hovered = null; onHover?.(null); }}
        onClick={handleClick}
      />
    </div>
  );
}
