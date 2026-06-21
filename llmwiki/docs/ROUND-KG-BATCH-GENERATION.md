# 本轮新增三项能力(KG 邻域导航 / Batch 抽取 / 生成模块)

> 按既定顺序逐个补成完整代码,全部通过离线冒烟测试(11 组)与 import 解析(38 模块)。

---

## ① navigate 的 KG 邻域扩展 + /neighbors 关系子图(第 2、3 题精度核心)

**变更:**
- `store.link_entities`:实体链接从字符串 ILIKE 升级为 **embedding 相似检索**(query 向量在 entities 上 ANN),叠加名字模糊召回兜底。
- `store.neighbors`:从种子实体沿 `relations` 做 **BFS 多跳扩展**(hops 可配),返回 `{nodes, edges}` 子图。
- `store.export_graph`:导出全租户 KG。
- `evidence/service.py`:
  - `/navigate` 重写——实体链接 → KG 邻域扩展(默认 1 跳,多跳问答调大)→ 聚合邻域文档为 scope → **返回 `edges` 关系边**(第 3 题:关系现在被展示/消费了)。
  - 新增 `/neighbors`(实体子图)与 `/graph/export`(json/graphml/cypher)。
- `evidence/graph_export.py`:KG → JSON / GraphML(Gephi/yEd)/ Cypher(Neo4j)导出。
- `query/tools.py`:新增 `neighbors` agent 工具 + navigate 支持 `hops`,agentic 循环可主动做多跳。

**解决了什么:** "项目为什么超预算"这类多文档问题,现在 navigate 能经由 `项目X --has_budget--> 预算 / 实际成本 / 变更说明` 把关联文档全拉进 scope,而不再是单实体名匹配。关系数据之前只存不展示,现在 `/navigate`、`/neighbors`、`/graph/export` 三个出口都暴露了。

**验证:** graphml 结构良好、cypher 含 MERGE 节点+关系(smoke `test_graph_export`)。

---

## ② L2 抽取 Batch 化(第 1 题最大收益)

**变更:**
- `l2_extract.py`:抽出 `_build_extract_messages` / `parse_extract_result` 纯函数(实时与 Batch 共用),新增 `batch_extract_document`——把一个文档所有变化 chunk 组成**单个 Batch job** 提交,异步轮询,解析回 `{chunk_id: (facts, entities)}`。
- `orchestrator.py`:L2 加阈值开关——变化 chunk ≥30 走 **Batch API**(成本减半、不占交互配额);小文档保持实时低延迟。

**解决了什么:** 300 页 ≈250 chunk 原来是 250 次实时往返;现在一个 Batch job 搞定,**成本再降约一半**,且后台编译不再挤占交互问答的限流配额。渐进编译的 D0 已先让文档可问,Batch 的分钟级延迟可接受。

**验证:** 共用解析器正确把 `source_span_index` 映射回 span_id、保留 qualifiers、实体 mention(smoke `test_extract_parse`)。

---

## ③ 生成模块(报告/图表/表格/PPT,Messages API + 确定性渲染)

**架构原则:模型只产"内容/数据规范",文件由确定性渲染层生成。** 数字不会在渲染阶段被改,可单测。

**变更:**
- `generation/generate.py`:基于指令(+可选 document_ids / 直接复用问答证据)走 **Messages API** 产出结构化产物——report(markdown,含 [doc:span] 引用)、chart(Vega-Lite 风格 spec)、table(JSON)、slides(大纲 JSON)。证据仍走只读 Evidence API 取证。
- `generation/render.py`:确定性渲染——report→docx、table→xlsx、chart→png(matplotlib,CJK 字体可配 `CHART_CJK_FONT`)、slides→pptx。依赖按需 import,缺失给清晰错误。
- `generation/service.py`:`/generate`(返回 spec)与 `/generate/file`(渲染为文件,按租户隔离输出目录)。viewer 角色禁止生成。

**为什么不升级 Agent SDK:** 这类"基于证据生成报告/图表"是少轮结构化生成,Messages API + 确定性渲染完全够,且复用了鉴权/取证/隔离。只有"agent 自主跑代码生成文件"的高级场景才需要 Agent SDK,届时放进 gVisor 隔离的执行 worker,工具仍指向同一组只读 Evidence API。

**验证:** chart→png、table→xlsx 真实渲染成功(smoke `test_render_specs`)。

**端到端示例(给齐 API Key 后):**
```bash
# 基于问答证据生成预算分析报告(docx)
curl -X POST localhost:8004/generate/file -H "Authorization: Bearer $TOKEN" \
     -H 'Content-Type: application/json' \
     -d '{"instruction":"生成项目预算超支分析报告","artifact_type":"report"}'
# 生成图表数据(png)
curl -X POST localhost:8004/generate/file -H "Authorization: Bearer $TOKEN" \
     -H 'Content-Type: application/json' \
     -d '{"instruction":"按类别画预算金额柱状图","artifact_type":"chart"}'
```

---

## 统计

- 新增/改动:`store.py`(+3 KG 方法)、`evidence/service.py`(navigate 重写 + /neighbors + /graph/export)、`evidence/graph_export.py`(新)、`query/tools.py`(+neighbors 工具)、`l2_extract.py`(+batch)、`orchestrator.py`(batch 开关)、`generation/{generate,render,service}.py`(新)、compose(+generation 服务)。
- 全仓:70 文件 / ~3766 行 Python;52 源文件语法零错误;38 模块 import 全解析;离线冒烟 11 组全 PASS;compose 9 服务合法。
- 生成模块用的是 **Claude Messages API(`@anthropic-ai/sdk` / Python `anthropic`)**,不是 Agent SDK(`@anthropic-ai/claude-agent-sdk`)。
