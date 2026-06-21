# obsidian-wiki 对照反思:我们的方案缺了什么、借什么、不借什么

> 已核对真实仓库源码(README / releases / skill 描述),以下结论基于已验证的机制,不是文章转述。
> obsidian-wiki 是**单用户、本地、文件型、人在环路**的个人知识库框架(一组 markdown skill,任意 coding agent 执行)。
> 我们的目标是**多租户、高并发、服务化、合规级引用**的企业问答产品。所以它的设计有的直接可借、有的需改造、有的根本不适用。诚实区分这三类。

---

## 一、逐项比对(核对源码后的结论)

| obsidian-wiki 机制(已验证) | 我方现状 | 判定 |
|---|---|---|
| `.manifest.json` 用 SHA-256+时间戳跟踪每个**源文件**,并记录它产出了**哪些 wiki 页面** | 我有 chunk 级 `content_hash` + `unit_hash`,能跳过未变 chunk | **部分缺口**:我跟踪的是 chunk hash,没跟踪"源→派生产物(fact/entity/wiki 节点)"的依赖图。改一页时我能重抽 chunk,却不能精确失效它派生出的下游 KG 节点。 |
| **溯源三态** `extracted`(源文明说)/`inferred`(AI 跨源推理)/`ambiguous`(多源矛盾),每页 `provenance:` 块记录比例 | 我只有 `source_span_ids`(指针)+ `confidence`(标量) | **真缺口**。指针不等于认识论状态。我无法区分"文档明确说的"和"AI 推断的"和"多文档互相打架的"。企业 KB 里这是致命的——尤其 `ambiguous`(跨文档矛盾)和 `inferred`(无源臆测)。 |
| **wiki-lint 审计**:ambiguous>15% 报警;inferred>40% 且无 source 标"无源推测";**Hub 页(全库链接前 10)若 inferred>20% 加急**(错误传播模型:先修影响面最大的节点) | 我只有 `verify`(每次回答的 NLI 校验,在线) | **真缺口**。我缺**离线的知识体检**。而且"按 hub 度数加权优先修复"这个错误传播思想很聪明,正好映射到我的实体图高度数节点。 |
| **分层检索**:先读 title/tag/`summary:`(≤200 字符),**答得了就停**;答不了才 grep 段落;再不行才读全文。"quick answer/just scan" 强制只走索引层。**20 页到 2000 页查询开销基本不变** | 我有 navigation-first(KG 圈 scope)+ 混合检索,但**最便宜的"纯摘要扫描即答"那一层没有**。我的 Fast 路径仍然要做检索 | **部分缺口**。我缺真正的 tier-0(摘要/索引扫描),它是"开销随规模平坦"的关键。我的复杂度路由只分 simple/complex,simple 仍走检索。 |
| **重要度 tier**:页面带 `tier: core/supporting/peripheral`,wiki-query 据此排序、peripheral 除非唯一匹配否则不读 | 我只按检索分排序 | **缺口**。加重要度分层,检索可优先 core、跳过 peripheral,"只读 top-3"才有原则。 |
| **矛盾检测**:merge 时若新知识与已有冲突,标注矛盾 | 无显式机制 | **真缺口**。和 `ambiguous` 一体。多文档企业场景(合同 vs 邮件 vs 纪要 口径不一)极其需要。 |
| **Schema 涌现 + tag-taxonomy 规范化**:类目不预设、随源演化,有规范化 skill | 我实体类型是固定 enum | **小缺口**。受控但可演化的 taxonomy + 归一化 pass 比硬编码 enum 好。 |
| **Archive + rebuild**:wiki 漂移太远可快照归档、从源重建 | 无 | **缺口(易补)**。配合 prompt_version bump 的重编,做 KG/wiki 的租户级版本快照与重建。 |
| **cross-linker**:周期性发现未链接的提及并织入 wikilink | 我的 entity resolution 链接 mention,但没有周期性"全库找未链接提及"维护 pass | **部分缺口**。这正是 Karpathy 说的"记账成本——AI 来扛"。 |
| **daily-update 维护循环**:freshness/index/hot cache 定时维护 | 无 | **缺口**。"人类两周就放弃维护 Wiki,AI 不会"——这是 obsidian-wiki 的灵魂,我完全没体现。 |
| wiki-status 洞察(hubs/bridge/惊奇连接) | 无 | 锦上添花,非核心。 |
| graph 导出 Neo4j/graphml/html | 我可选 Neo4j | 不重要。 |
| **不需要向量库**(grep+frontmatter 扫描) | 我用 pgvector | **不照搬**:个人规模(千页)grep 够;obsidian-wiki 自己在大库时也加了可选 QMD 语义检索。我方目标是百万文档,grep 撑不住。**借"便宜层优先"原则,不借"扔掉向量库"。** |

---

## 二、三条诚实的反思

### 反思 1:obsidian-wiki 其实**印证**了我方案的中心修正,而不是推翻它

它的分层检索在摘要答不了时**仍然回退到 grep 段落、读页面全文**——也就是说**它始终保留 raw 层并去读它**。而且 tier-1 的摘要级回答会被显式标注"这是索引级回答,没读正文"。这正是我坚持的:**wiki/摘要只做导航,最终要落到原文证据;不确定就要诚实标注。** 区别在于我把 span 作为强制的一等引用单元、做服务端 ACL,它是松散的本地文件。所以——不要因为它"简洁优雅"就去模仿它的松散;它的严肃机制(溯源、lint)才是该借的。

### 反思 2:我**低估了认识论透明度和离线知识体检**

我的强项(多租户隔离、span 引用、并发、在线 verify)恰恰是 obsidian-wiki 没有的。但它有两样我只做了一半甚至没做的东西,而且对企业 KB 价值极高:
- **每条知识的认识论状态**(extracted/inferred/ambiguous)——不只是"有没有出处指针",而是"这是事实、推断、还是矛盾"。
- **离线的知识健康审计 + 按 hub 加权的错误传播优先级**——我只有逐答案在线校验,缺整库的体检和"先修影响面最大节点"。

这两点是这次对照最该吸收的教训。下面补成代码。

### 反思 3:有些东西**不能照搬**,照搬反而是退步

- 它是单用户人在环路;企业产品必须自动化 + 隔离 + 并发,不能把"让用户自己读 wiki、自己确认 lint 结果"当默认。借它的机制,但把"人确认"改成"高风险才人审、低风险自动门控(gated promotion)"。
- 它"不要向量库"在百万文档规模不成立——保留 pgvector,只借"便宜层优先、贵层兜底"的成本曲线思想。
- 它的 wiki 页常常**就是答案**(可接受有损,因为是个人召回);企业问答里数值/条款/附录细节必须无损——所以我保留 span 强制引用,不接受"wiki 页即答案"。

---

## 三、要补进方案的(已实现为代码,见下)

按价值排序,本轮补齐 6 项里最高价值的 4 项为可运行代码,其余 2 项给接口位:

| 借鉴 | 落地 | 代码 |
|---|---|---|
| **溯源三态 + 矛盾检测** | Fact/WikiNode 带 `provenance`;merge 时跨源比对同 (subject,predicate) 冲突 → `ambiguous` | `models/schema.py` 扩展 + `compile/contradiction.py` |
| **知识健康审计(hub 加权错误传播)** | 离线扫 KG:ambiguous 比例、无源 inferred、按实体度数加权排序待修节点 | `maintain/lint.py` |
| **分层检索 tier-0 + 重要度 tier** | 先摘要/索引扫描(index-only 可强制),答不了才落 span 检索;chunk/entity 带 `tier`,排序优先 core | `evidence/tiered.py` + 模型 `tier`/`summary` 字段 |
| **源→派生产物依赖 manifest** | 记录每个 source/chunk 产出了哪些 fact/entity/wiki 节点,改动时精确失效下游 | `compile/manifest.py` |
| 归档+重建 | 接口位(KG/wiki 租户级快照) | `maintain/archive.py`(桩) |
| 定时维护循环 | 接口位(freshness/hub 重算/再 lint) | `maintain/daily.py`(桩) |

> 一句话:obsidian-wiki 教给我的不是"换架构",而是**给知识对象加认识论标签(extracted/inferred/ambiguous)、做离线的 hub 加权知识体检、用便宜层优先压平查询成本**——这三样嫁接到我已有的 span 证据层 + 多租户骨架上,才是企业级的完整形态。
