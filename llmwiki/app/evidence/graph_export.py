"""KG 导出(借自 obsidian-wiki 的 wiki-export):JSON / GraphML / Cypher。

把 entities + relations 导成可视化/可查询格式。有 Neo4j 时用 Cypher 导入,
用现成图可视化;轻量场景用 JSON 喂前端力导向图。
"""
from __future__ import annotations

import json
import xml.sax.saxutils as sax


def to_json(graph: dict) -> str:
    return json.dumps(graph, ensure_ascii=False)


def to_graphml(graph: dict) -> str:
    """GraphML(Gephi/yEd 可读)。"""
    out = ['<?xml version="1.0" encoding="UTF-8"?>',
           '<graphml xmlns="http://graphml.graphdrawing.org/xmlns">',
           '<key id="name" for="node" attr.name="name" attr.type="string"/>',
           '<key id="type" for="node" attr.name="type" attr.type="string"/>',
           '<key id="rel" for="edge" attr.name="relation" attr.type="string"/>',
           '<graph edgedefault="directed">']
    for n in graph["nodes"]:
        nid = sax.quoteattr(n["entity_id"])
        out.append(f'<node id={nid}>'
                   f'<data key="name">{sax.escape(n.get("name",""))}</data>'
                   f'<data key="type">{sax.escape(n.get("type",""))}</data></node>')
    for i, e in enumerate(graph["edges"]):
        out.append(f'<edge id="e{i}" source={sax.quoteattr(e["source"])} '
                   f'target={sax.quoteattr(e["target"])}>'
                   f'<data key="rel">{sax.escape(e.get("relation",""))}</data></edge>')
    out += ['</graph>', '</graphml>']
    return "\n".join(out)


def to_cypher(graph: dict) -> str:
    """Cypher 脚本(导入 Neo4j)。"""
    lines = []
    for n in graph["nodes"]:
        name = n.get("name", "").replace("'", "\\'")
        etype = n.get("type", "Entity").replace("'", "\\'")
        lines.append(
            f"MERGE (e:Entity {{id:'{n['entity_id']}'}}) "
            f"SET e.name='{name}', e.type='{etype}';")
    for e in graph["edges"]:
        rel = "".join(c for c in e.get("relation", "REL").upper() if c.isalnum() or c == "_") or "REL"
        lines.append(
            f"MATCH (a:Entity {{id:'{e['source']}'}}),(b:Entity {{id:'{e['target']}'}}) "
            f"MERGE (a)-[:{rel}]->(b);")
    return "\n".join(lines)


def to_html(graph: dict) -> str:
    """自包含 HTML(力导向图,无外部依赖,内联极简物理布局)。供快速预览/嵌入。"""
    data = json.dumps(graph, ensure_ascii=False)
    return (
        '<!doctype html><html><head><meta charset="utf-8">'
        '<style>body{margin:0;background:#F0EEE6;font-family:sans-serif}'
        'canvas{display:block}</style></head><body><canvas id="c"></canvas>'
        '<script>const G=' + data + ';'
        'const cv=document.getElementById("c"),x=cv.getContext("2d");'
        'cv.width=innerWidth;cv.height=innerHeight;'
        'const N=G.nodes.map((n,i)=>({...n,px:Math.random()*cv.width,py:Math.random()*cv.height,vx:0,vy:0}));'
        'const idx={};N.forEach((n,i)=>idx[n.entity_id]=i);'
        'const E=G.edges.filter(e=>idx[e.source]!=null&&idx[e.target]!=null);'
        'function step(){for(const a of N){a.vx*=.9;a.vy*=.9;for(const b of N){if(a==b)continue;'
        'let dx=a.px-b.px,dy=a.py-b.py,d=Math.hypot(dx,dy)||1;let f=400/(d*d);a.vx+=dx/d*f;a.vy+=dy/d*f;}}'
        'for(const e of E){let a=N[idx[e.source]],b=N[idx[e.target]],dx=b.px-a.px,dy=b.py-a.py,d=Math.hypot(dx,dy)||1,f=(d-120)*.01;'
        'a.vx+=dx/d*f;a.vy+=dy/d*f;b.vx-=dx/d*f;b.vy-=dy/d*f;}'
        'for(const n of N){n.px+=n.vx;n.py+=n.vy;}'
        'x.clearRect(0,0,cv.width,cv.height);x.strokeStyle="#cdc9bd";'
        'for(const e of E){let a=N[idx[e.source]],b=N[idx[e.target]];x.beginPath();x.moveTo(a.px,a.py);x.lineTo(b.px,b.py);x.stroke();}'
        'x.fillStyle="#D97757";for(const n of N){x.beginPath();x.arc(n.px,n.py,6,0,7);x.fill();'
        'x.fillStyle="#3d3d3a";x.fillText(n.name||"",n.px+8,n.py+3);x.fillStyle="#D97757";}'
        'requestAnimationFrame(step);}step();</script></body></html>')


def export(graph: dict, fmt: str = "json") -> str:
    return {"json": to_json, "graphml": to_graphml,
            "cypher": to_cypher, "html": to_html}[fmt](graph)
