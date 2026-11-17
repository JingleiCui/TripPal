# 配套架构图呈现方案

面向 GitHub README 的架构图设计说明。目标：在 GitHub 原生渲染环境（不支持自定义 CSS、
不支持外链 JS）里，达到课程项目资料中「分层清晰、职责可读、数据流向可追」的专业观感，
同时保证**图中每个节点都能在仓库源码里找到对应实现**。

---

## 1. 参照资料里提炼出的画法要素

对课程大纲中 AI 智能体项目的架构图逐个分析后，可迁移的专业度要素如下（只提炼画法，
不复用任何原文与业务内容）：

| 要素 | 资料里的做法 | 迁移到本项目的做法 |
|---|---|---|
| **分层** | 自上而下按「用户接入 → 网关/编排 → Agent 执行 → 工具/MCP → 存储/可观测」分层 | Mermaid `subgraph` 分 5 层，每层一个容器 |
| **分组框** | 虚线大框圈住同职责的组件，框顶标注层名 | Mermaid `subgraph` 天然带标题框，用 `classDef` 给容器上浅色 |
| **主色带** | 深蓝色横带承载阶段/总线名，下面挂浅蓝并列盒 | 用 `classDef accent` 给入口、编排、写入节点上深蓝；其余浅蓝 |
| **箭头语义** | 连线上标注协议或动作（HTTP / WebSocket / Pull / Manage） | 边上写 `-->|HTTP|` 等标签，区分「调用」与「数据写入」 |
| **编号与图例** | 关键路径带序号或阶段名 | 在节点名前加 `1.`…`7.`，并在图下配一行文字图例 |
| **图文互证** | 每张架构图前后必有「项目介绍 / 能力目标 / 解决方案」文字块 | 架构图前后各一段说明，图下附「读图顺序」 |
| **两侧留白** | 可观测、外部服务置于主链路左右两侧，不挤占主干 | 用 `direction` 与并列 subgraph 把可观测/外部依赖放侧列 |

关键取舍：资料中的图多为位图，GitHub 上无法按主题切换、无法版本 diff、链接不可点。
本方案改用 **Mermaid**——纯文本、可 diff、GitHub 与 VS Code 均原生渲染、支持深色主题，
且节点名可直接对应源码符号，避免「图与代码不一致」。

---

## 2. 本项目的图形体系（共 4 张，职责不重叠）

| # | 图 | 类型 | 回答的问题 | 放置位置 |
|---|---|---|---|---|
| A | 系统分层架构 | `flowchart TB` + `subgraph` | 有哪些层、各层组件、依赖方向 | README §🏗️ 主图 |
| B | LangGraph 控制流 | `flowchart TD` + 条件分支/回边 | 图怎么跑、哪里分支、哪里循环、哪里终止 | README §🏗️ 副图 |
| C | 一次任务的执行时序 | `sequenceDiagram` | 从一句话到行程落库，跨进程怎么协作 | README §🏗️ 第三图 |
| D | RAG 检索溯源链路 | `flowchart LR` | 文档怎么变成可溯源证据 | README §🧪 效果示例 |

设计原则：**一张图只回答一个问题**。A 讲静态结构，B 讲控制逻辑，C 讲运行时序，
D 讲数据流；四张图不重复画同一批节点，避免读者在冗余里迷路。

---

## 3. 配色与语义约定（对应课程资料的深蓝/浅蓝体系）

```
classDef accent   深蓝底白字  → 入口 / 编排中枢 / 最终写入（视觉锚点，全图 ≤ 3 个）
classDef storage  灰底深字    → 存储节点（表示「被动」）
classDef human    暖色        → 需要人工确认 / 中断点

README 的 A 图使用 `accent` + `storage`，B 图使用 `human`，D 图使用 `accent`；
默认节点由 Mermaid 主题自动着色，因此不额外定义 `layer`，把颜色组控制在 3 组。
```

- 实线箭头 `-->`：同步调用或数据读取。
- 虚线箭头 `-.->`：异步、审计、可降级或人工介入。
- 边标签写在 `|...|` 内，只写协议/动作，不写解释性长句。
- 节点文字用仓库里的真实模块名或真实端点（如 `social_api.py`、`/conversations/{id}/turns`），
  便于读者用搜索直接定位源码。

> 注意：Mermaid 的 `classDef` 在 GitHub 深色/浅色主题下都会渲染。不要用纯白或纯黑底色，
> 也不要依赖 `style` 之外的自定义 CSS；颜色数控制在 4 组以内。

---

## 4. 读图顺序（写进 README 图下的说明）

1. 先看 A：找出请求从哪一层进来、结果落在哪一层。
2. 再看 B：确认 Agent 不是无限循环（有 `recursion_limit`、预算、租约三类终止条件）。
3. 再看 C：理解「接口返回」与「异步执行」分离，任务由 Celery worker 领取。
4. 最后看 D：确认每个事实都带来源，检索结果在召回前按用户与版本过滤。

---

## 5. 可追溯性检查清单（发布前逐条对照源码）

| 图中节点 | 源码位置 |
|---|---|
| 确定性访谈门控 | `backend/travel_agent/conversation.py`、`backend/travel_agent/interview.py` |
| FastAPI 路由 | `backend/travel_agent/api.py`、`social_api.py` |
| Celery 任务领取 | `backend/travel_agent/worker.py` |
| LangGraph 节点与边 | `backend/travel_agent/agent/graph.py` |
| 工具预算/审计事件 | `backend/travel_agent/agent/harness.py` |
| 结构化输出与一次纠正 | `backend/travel_agent/agent/structured.py` |
| 模型网关 | `backend/travel_agent/models/{specs,registry,gateway}.py` |
| 高德/美团适配 | `backend/travel_agent/providers/{amap,meituan}.py` |
| MCP server（10 工具 + scope + AuditLog） | `backend/travel_agent/mcp/server.py` |
| 能力门控 | `backend/travel_agent/capabilities.py` |
| 文档切块/混合检索/RRF | `backend/travel_agent/knowledge.py` |
| 版本与撤销 | `backend/travel_agent/{db,pending_api}.py` |
| 前端地图与工作台 | `frontend/src/{App,ConversationWorkspace,TripExperience}.tsx` |

---

## 6. 若后续要升级为位图/动画

当前仓库中 `reports/` 下的截图被 `.gitignore` 排除，且 `git ls-files` 中不含任何
Demo GIF、Logo 或检索溯源截图。若要把 A 图升级为 `<picture>` 明暗双版本位图、
或补一张首屏 Demo GIF，需要先准备素材再替换；**不要把未制作的素材写成图片链接**。
推荐做法：位图放 `docs/assets/`，用相对路径引用，并在明暗两版 `<source>` 中切换。
