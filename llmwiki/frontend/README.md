# LLM-Wiki 前端设计与实现

> 风格:Claude 亮色科技。技术栈:React 18 + Vite,零重型依赖(图谱用原生 canvas)。
> 全部 11 个 JSX 文件已通过 esbuild 编译校验。

---

## 一、设计系统(`src/styles.css`)

**取向**:忠于 Claude 亮色品牌(暖白 `#F0EEE6` + 珊瑚 `#D97757`),但避免"暖白+衬线+陶土色"这一 AI 默认套路。区分点是**双语义强调色 + 等宽数据层**:

- **表面**:暖白底 `#F0EEE6`,卡片 `#FCFBF7`,描边 `#E3DFD3`。
- **双语义强调**(签名):珊瑚 `#D97757` = 动作(按钮/激活);证据蓝 `#4A6FA5` = **仅用于引用/溯源**——颜色本身编码语义,不是装饰。
- **溯源三态**:绿(extracted)/黄(inferred)/红(ambiguous),与后端 `Provenance` 一一对应。
- **等宽数据层**:span ID、溯源标签、JSON、租户标识全用 monospace——这是"科技感"的来源,而非靠深色背景或霓虹色。
- **排版**:Inter/系统无衬线为主,中文 PingFang/雅黑;紧凑字号(14px 基准)、克制留白。
- **动效克制**:仅加载点、hover 微交互;尊重 `prefers-reduced-motion`。

**签名元素**:回答里的 `[doc:span]` 渲染成可点开的证据 chip(蓝),展开显示原文——把"引用必须落到原文 span"这一产品内核做成可见的交互。这是别的知识库工具没有的。

---

## 二、视图(7 个,映射后端能力)

| 视图 | 文件 | 后端端点 | 说明 |
|---|---|---|---|
| 登录 | `views/Login` | `POST /auth/login` | 邮箱密码 → JWT |
| 问答 | `views/Ask` | `POST /ask` | 对话 + 引用 chip + 证据校验% + 升级标记 + 会话记忆 |
| 文档 | `views/Documents` | `POST /ingest`、`GET /documents/{id}/status` | 入库 + 深度选择(D0/D1/D2)+ 编译状态 |
| 知识图谱 | `views/Graph` + `components/GraphCanvas` | `GET /graph` | 力导向图(canvas)+ 实体详情;实时数据,失败回退演示 |
| 生成 | `views/Generate` | `POST /generate`、`/generate/file` | 报告/图表/表格/PPT,内容或文件 |
| 健康 | `views/Health` | `GET /status` | 规模/hubs/orphans/矛盾比例 + 溯源图例 |
| 管理 | `views/Admin` | `/admin/tenants`、`/admin/users` | 平台管理员建租户/用户/角色 |

外加签名组件 `components/Citation`(引用 chip + 溯源点)。App shell(`App.jsx`)做鉴权门、侧栏导航、视图切换。

---

## 三、与后端的连接

- 开发期 `vite.config.js` 把 `/api/{query,admin,ingest,gen,evidence}` 代理到对应端口(8000/8002/8003/8004/8001),免 CORS。
- 生产由 Ingress/网关统一路由这些前缀。
- 图谱/健康经 **查询网关透传**(`query/gateway.py` 新增 `GET /graph`、`GET /status`,内部带 HMAC 签名调 evidence)——前端不直接碰需要内部签名的 evidence 服务。
- token 存 localStorage,所有请求带 `Authorization: Bearer`;tenant/user 由登录响应得来,前端从不自己设 tenant。

---

## 四、运行

```bash
cd frontend
npm install
npm run dev          # http://localhost:5173,需后端各服务在 8000-8004 运行
# 生产
npm run build        # 产物在 dist/,交给任意静态服务器 / Nginx / 网关
```

后端起法见根 README(`docker compose up`)。先用 Admin 视图(需平台 admin key)建租户+用户,再登录使用。

---

## 五、质量基线

- 响应式 grid 布局,移动端侧栏可收窄(媒体查询点已留);
- 键盘可达(input 回车提交,focus 有 2px 珊瑚描边);
- `prefers-reduced-motion` 关闭动效;
- 空状态有引导文案(问答/文档列表),错误以界面口吻给出而非堆栈。
- 11 个 JSX 全部通过 esbuild 编译;无 localStorage 之外的浏览器存储依赖。

> 一句话:前端把后端的"证据落地 + 溯源 + 多跳 + 隔离"做成可见、可点、可隔离的体验——
> 引用能点开看原文、溯源用颜色编码、图谱能走关系、会话按用户隔离,且全程 Claude 亮色科技风格。
