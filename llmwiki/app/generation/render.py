"""确定性渲染层:把生成模块产出的结构化内容渲染为真实文件。

模型只负责"内容/数据规范",文件生成是确定性的、与模型无关——
这样数字不会在渲染阶段被改动,且可单测。依赖按需 import(未装则报清晰错误)。

- report(markdown) → .docx / .md
- table(JSON)      → .xlsx
- chart(spec)      → .png(matplotlib)
- slides(JSON)     → .pptx
"""
from __future__ import annotations

import os


def render_report_md(content: str, out_path: str) -> str:
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(content)
    return out_path


def render_report_docx(content: str, out_path: str) -> str:
    try:
        from docx import Document
    except ImportError as e:
        raise RuntimeError("需要 python-docx: pip install python-docx") from e
    doc = Document()
    for line in content.splitlines():
        line = line.rstrip()
        if line.startswith("# "):
            doc.add_heading(line[2:], level=1)
        elif line.startswith("## "):
            doc.add_heading(line[3:], level=2)
        elif line.startswith("### "):
            doc.add_heading(line[4:], level=3)
        elif line.startswith(("- ", "* ")):
            doc.add_paragraph(line[2:], style="List Bullet")
        elif line:
            doc.add_paragraph(line)
    doc.save(out_path)
    return out_path


def render_table_xlsx(spec: dict, out_path: str) -> str:
    try:
        from openpyxl import Workbook
    except ImportError as e:
        raise RuntimeError("需要 openpyxl: pip install openpyxl") from e
    wb = Workbook()
    ws = wb.active
    ws.append(spec.get("columns", []))
    for row in spec.get("rows", []):
        ws.append(row)
    wb.save(out_path)
    return out_path


def render_chart_png(spec: dict, out_path: str) -> str:
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError as e:
        raise RuntimeError("需要 matplotlib: pip install matplotlib") from e
    # 中文字体:设 CHART_CJK_FONT 环境变量指向已安装字体(如 Noto Sans CJK SC / 思源黑体),
    # 否则中文会显示为方框。生产镜像应预装中文字体。
    cjk = os.getenv("CHART_CJK_FONT", "")
    if cjk:
        matplotlib.rcParams["font.sans-serif"] = [cjk]
        matplotlib.rcParams["axes.unicode_minus"] = False
    data = spec.get("data", [])
    xs = [d.get("x") for d in data]
    ys = [d.get("y", 0) for d in data]
    ctype = spec.get("chart_type", "bar")
    fig, ax = plt.subplots(figsize=(8, 4.5))
    if ctype == "line":
        ax.plot(xs, ys, marker="o")
    elif ctype == "pie":
        ax.pie(ys, labels=xs, autopct="%1.1f%%")
    else:
        ax.bar(xs, ys)
    ax.set_title(spec.get("title", ""))
    if ctype != "pie":
        ax.set_xlabel(spec.get("x_field", "")); ax.set_ylabel(spec.get("y_field", ""))
        plt.xticks(rotation=30, ha="right")
    fig.tight_layout()
    fig.savefig(out_path, dpi=120)
    plt.close(fig)
    return out_path


def render_slides_pptx(spec: dict, out_path: str) -> str:
    try:
        from pptx import Presentation
        from pptx.util import Inches, Pt
    except ImportError as e:
        raise RuntimeError("需要 python-pptx: pip install python-pptx") from e
    prs = Presentation()
    # 标题页
    title_layout = prs.slide_layouts[0]
    s = prs.slides.add_slide(title_layout)
    s.shapes.title.text = spec.get("title", "")
    # 内容页
    bullet_layout = prs.slide_layouts[1]
    for slide in spec.get("slides", []):
        sl = prs.slides.add_slide(bullet_layout)
        sl.shapes.title.text = slide.get("title", "")
        body = sl.placeholders[1].text_frame
        body.clear()
        for i, b in enumerate(slide.get("bullets", [])):
            p = body.paragraphs[0] if i == 0 else body.add_paragraph()
            p.text = b
            p.font.size = Pt(18)
    prs.save(out_path)
    return out_path


def render_report_html(content: str, out_path: str) -> str:
    """Markdown → HTML,带深色主题样式。"""
    import html as _html
    lines = content.splitlines()
    body_parts = []
    for line in lines:
        line = line.rstrip()
        if line.startswith("# "):
            body_parts.append(f"<h1>{_html.escape(line[2:])}</h1>")
        elif line.startswith("## "):
            body_parts.append(f"<h2>{_html.escape(line[3:])}</h2>")
        elif line.startswith("### "):
            body_parts.append(f"<h3>{_html.escape(line[4:])}</h3>")
        elif line.startswith(("- ", "* ")):
            body_parts.append(f"<li>{_html.escape(line[2:])}</li>")
        elif line.startswith("> "):
            body_parts.append(f"<blockquote>{_html.escape(line[2:])}</blockquote>")
        elif line == "---":
            body_parts.append("<hr/>")
        elif line == "":
            body_parts.append("<br/>")
        else:
            body_parts.append(f"<p>{_html.escape(line)}</p>")
    body = "\n".join(body_parts)
    html = f"""<!DOCTYPE html><html lang="zh-CN"><head><meta charset="utf-8"/>
<meta name="viewport" content="width=device-width,initial-scale=1"/>
<title>报告</title>
<style>
*{{margin:0;padding:0;box-sizing:border-box}}
body{{background:#0F0B1E;color:#F0EDE8;font-family:Inter,-apple-system,sans-serif;line-height:1.7;padding:40px 20px}}
.container{{max-width:800px;margin:0 auto;background:rgba(255,255,255,0.04);border:1px solid rgba(255,255,255,0.08);border-radius:12px;padding:36px 40px}}
h1{{font-size:24px;font-weight:650;margin-bottom:16px;color:#9178FF}}
h2{{font-size:18px;font-weight:600;margin-top:24px;margin-bottom:10px;color:#F0EDE8}}
h3{{font-size:15px;font-weight:600;margin-top:18px;margin-bottom:8px;color:#B0ABB8}}
p{{margin-bottom:10px;font-size:14px;color:#E0DDE6}}
li{{margin-left:20px;margin-bottom:6px;font-size:14px;color:#E0DDE6}}
blockquote{{border-left:3px solid #7C5CFC;padding:10px 16px;margin:12px 0;background:rgba(124,92,252,0.08);border-radius:0 6px 6px 0;color:#B0ABB8}}
hr{{border:none;border-top:1px solid rgba(255,255,255,0.08);margin:24px 0}}
.cite{{color:#60A5FA;font-family:monospace;font-size:12px}}
</style></head><body><div class="container">{body}</div></body></html>"""
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(html)
    return out_path


def render(artifact: dict, out_dir: str, name: str = "output") -> str:
    """按 artifact 类型分派到对应渲染器,返回文件路径。"""
    os.makedirs(out_dir, exist_ok=True)
    t = artifact["type"]
    if t == "report":
        # 同时输出 docx + html
        render_report_docx(artifact["content"], os.path.join(out_dir, f"{name}.docx"))
        return render_report_html(artifact["content"], os.path.join(out_dir, f"{name}.html"))
    if t == "table":
        return render_table_xlsx(artifact["spec"], os.path.join(out_dir, f"{name}.xlsx"))
    if t == "chart":
        return render_chart_png(artifact["spec"], os.path.join(out_dir, f"{name}.png"))
    if t == "slides":
        return render_slides_pptx(artifact["spec"], os.path.join(out_dir, f"{name}.pptx"))
    raise ValueError(f"unknown artifact type: {t}")
