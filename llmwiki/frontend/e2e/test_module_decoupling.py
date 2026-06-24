"""
严格的模块解耦 E2E 测试 — 验证问答/生成/知识图谱三个模块:
  A. 各自独立加载 0 错误
  B. 崩溃隔离: 一个模块出错不影响其他模块(ErrorBoundary)
  C. 状态隔离: 模块间反复切换状态不串
  D. 资源清理: 图谱卸载后无悬挂 animation 错误
"""
from playwright.sync_api import sync_playwright
import time, os, json

SHOT = "/tmp/llmwiki_decouple"; os.makedirs(SHOT, exist_ok=True)
results = []  # (测试名, 通过?, 详情)

def login(page):
    page.goto("http://localhost:5173/")
    page.wait_for_load_state("networkidle"); time.sleep(1)
    page.locator('input[type="email"]').fill("u@t1.test")
    page.locator('input[type="password"]').fill("demo")
    page.locator('button:has-text("登录")').click()
    page.wait_for_load_state("networkidle"); time.sleep(2)

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page(viewport={"width": 1440, "height": 900}, device_scale_factor=2)

    errors = []
    page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
    page.on("pageerror", lambda e: errors.append(f"PAGEERROR: {e}"))

    login(page)

    # ───── A. 三模块独立加载 ─────
    def visit(label, btn_text, settle=3):
        before = len(errors)
        page.locator(f'button:has-text("{btn_text}")').first.click()
        time.sleep(settle)
        new_errs = errors[before:]
        tick_errs = [e for e in new_errs if "tick" in e.lower()]
        ok = len(new_errs) == 0
        results.append((f"A. {label} 独立加载", ok, f"{len(new_errs)} 错误, tick={len(tick_errs)}"))
        return ok

    visit("知识图谱", "知识图谱", 5)
    visit("问答", "问答", 2)
    visit("生成", "生成", 2)

    # ───── B. 崩溃隔离测试 ─────
    # 通过 Graph 视图的"导入图数据"注入恶意数据(边引用不存在的节点 + 循环引用)
    page.locator('button:has-text("知识图谱")').first.click(); time.sleep(2)
    before = len(errors)
    # 注入异常数据: 边指向 undefined 节点、节点缺 entity_id
    bad = json.dumps({
        "nodes": [{"name": "孤儿", "type": "concept"}],  # 缺 entity_id
        "edges": [{"source": "ghost1", "target": "ghost2", "relation": "x"}],  # 引用不存在节点
    })
    ta = page.locator('textarea.input')
    if ta.count():
        ta.fill(bad)
        page.locator('button:has-text("载入")').click()
        time.sleep(3)
    crash_errs = errors[before:]
    # 关键: 即使数据异常,页面不应整体白屏 —— 验证还能切到其他模块
    page.locator('button:has-text("问答")').first.click(); time.sleep(2)
    ask_alive = page.locator('.composer input, button:has-text("载入演示对话")').count() > 0
    results.append(("B. 注入异常图数据后 Ask 仍可用", ask_alive, f"崩溃错误={len(crash_errs)}, Ask存活={ask_alive}"))

    page.locator('button:has-text("生成")').first.click(); time.sleep(2)
    gen_alive = page.locator('button:has-text("生成内容")').count() > 0
    results.append(("B. 注入异常图数据后 Generate 仍可用", gen_alive, f"Generate存活={gen_alive}"))

    # ───── C. 状态隔离: 问答输入不影响其他模块 ─────
    page.locator('button:has-text("问答")').first.click(); time.sleep(1)
    inp = page.locator('.composer input')
    if inp.count():
        inp.fill("状态隔离测试问题XYZ")
        time.sleep(0.5)
    # 切到生成再切回,问答输入框应已清空(独立组件重新挂载)
    page.locator('button:has-text("生成")').first.click(); time.sleep(1)
    page.locator('button:has-text("问答")').first.click(); time.sleep(1)
    inp2 = page.locator('.composer input')
    val = inp2.input_value() if inp2.count() else ""
    state_isolated = (val == "")  # 切走再回,状态重置 = 隔离正常
    results.append(("C. 模块切换状态隔离", state_isolated, f"切回后输入框='{val}'"))

    # ───── D. 资源清理: 反复进出图谱无悬挂动画错误 ─────
    before = len(errors)
    for _ in range(4):
        page.locator('button:has-text("知识图谱")').first.click(); time.sleep(1.5)
        page.locator('button:has-text("健康")').first.click(); time.sleep(1)
    cleanup_errs = errors[before:]
    tick_cleanup = [e for e in cleanup_errs if "tick" in e.lower() or "animation" in e.lower()]
    results.append(("D. 反复进出图谱无悬挂动画", len(tick_cleanup) == 0, f"动画/tick错误={len(tick_cleanup)}, 总={len(cleanup_errs)}"))

    page.locator('button:has-text("知识图谱")').first.click(); time.sleep(3)
    page.screenshot(path=f"{SHOT}/final_graph.png", full_page=False)

    browser.close()

# ───── 汇总 ─────
print("\n" + "=" * 60)
print("模块解耦 E2E 测试报告")
print("=" * 60)
passed = sum(1 for _, ok, _ in results if ok)
for name, ok, detail in results:
    print(f"  [{'✅' if ok else '❌'}] {name}")
    print(f"       {detail}")
print("=" * 60)
print(f"通过: {passed}/{len(results)}")
print(f"全部 console 错误数: {len(errors)}")
if errors:
    print("错误样本:")
    for e in errors[:5]: print(f"  - {e[:90]}")
print(f"截图: {SHOT}/final_graph.png")
