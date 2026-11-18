# Tripal 架构图选集

五张图依据 2026-11-18 当前代码绘制，参照课程文档中的工程架构图与流程图表达：虚线表示分区边界，浅蓝矩形表示模块，蓝色箭头表示调用或流转关系；工作流使用菱形判断和起止节点。分层图采用左侧层名与右侧模块矩阵。

[打开可缩放选图页](index.html)。每张图均提供可编辑的 draw.io 源文件、SVG 和 2 倍分辨率 PNG。旧版 Mermaid 仅保留为逻辑参考，不对应新版的固定布局。

| 编号 | 图 | 回答的问题 | 建议用途 |
|---|---|---|---|
| 01 | [整体架构](../../docs/assets/architecture/structured/01-overall.png) | 回答系统由哪些部分组成，以及一次规划如何形成反馈闭环。 | 适合 README 的第一张架构图。 |
| 02 | [分层架构](../../docs/assets/architecture/structured/02-layered.png) | 按职责划分交互、业务、编排、适配和数据层，突出模块边界。 | 适合工程设计说明；与整体图可二选一。 |
| 03 | [LangGraph 工作流](../../docs/assets/architecture/structured/03-langgraph.png) | 逐一对应实际节点、纯模型分支、约束回路和持久化中断。 | 适合突出 Agent 实现，与整体图搭配。 |
| 04 | [业务架构](../../docs/assets/architecture/structured/04-business.png) | 从需求、推荐、确认、调整到导出，说明产品闭环与支撑能力。 | 适合 README 项目简介之后。 |
| 05 | [技术架构](../../docs/assets/architecture/structured/05-technical.png) | 列出客户端、Python 服务、执行组件、基础服务和外部平台的技术组合。 | 适合技术栈说明，或与分层图二选一。 |

## README 已采用的图

- 当前中英文 README：**01 整体架构 + 03 LangGraph 工作流**。
- 面向使用者：**04 业务架构 + 01 整体架构**。
- 面向技术面试或设计评审：**02 分层架构 + 03 工作流 + 05 技术架构**。

README 已采用 01 与 03，英文版使用对应的英文标注图。其余三种视角保留在本图集中，供设计说明或技术交流引用。draw.io 源文件可在 diagrams.net 或 draw.io 桌面版打开，编辑模块、文字、连接点与折线。

## 绘图与导出

布局源码：[draw_architecture.py](../../scripts/draw_architecture.py)。颜色、字体、输出目录与英文图导出开关位于文件顶部 `CONFIG`，各图坐标与文案在对应绘图段落中编辑。运行后生成五种视角的 SVG 与未压缩 draw.io XML，以及供英文 README 使用的 01、03 英文版；随后可导出 PNG。所有图形均为原生节点和连接线，无需 Mermaid 或生成图片服务。

```bash
# 在项目根目录运行；Python 脚本仅依赖标准库
python3 scripts/draw_architecture.py

# 需先安装前端依赖与本机 Chrome；导出 2 倍 PNG 并检查文字边界
npm --prefix frontend ci
node scripts/export_architecture.mjs
```

draw.io 文件保留可编辑的模块、判断节点、存储符号与连接线。SVG 可直接用于 GitHub README；PNG 用于文档、演示或其他不支持 SVG 的场景。生成结果位于 `docs/assets/architecture/structured/`。

## 参考文档的借鉴方式

阅读了用户提供课程大纲的第 7、8、12、13 页，并渲染查看第 12 页。
介绍顺序借鉴“业务问题 → 能力拆解 → 技术模块 → 执行闭环”；绘图直接参考第 12 页“草本通 / SmartCloud”和第 13 页系统架构：虚线系统边界、浅蓝模块、居中文字、蓝色调用箭头，以及矩形处理、菱形判断和起止节点。去掉上一版大标题说明、卡片式排版和大段旁注。
没有把课程示例项目的能力移植成 Tripal 的功能声明：当前图不宣称已实现 A2A、Saga、Neo4j、Milvus、LangFuse 或容器化工具沙箱。

## 读图边界

- 整体图抽象了派发细节：SQL 是 queued 任务与版本的权威，派发器经 Redis/Celery 投递，Worker 执行。
- 分层图表达核心规划路径与职责边界；同步地点查询、收藏等业务可直接访问适配器或数据层。
- 技术图按技术分区聚合依赖，不是每次调用的时序。MCP stdio 可直接调用适配器/RAG，不要求经过 Celery 或 LangGraph。
- MySQL 检查点用于恢复图状态，不能代替最终行程保存时的权限、租约与基准版本复查。
- `research` 内领域按顺序执行；`single` 策略会合并调查工具。没有画成并行 fan-out。
- 工作流主干自上而下，中断恢复机制在右侧作为独立子流程；两个 `END` 表示同一结束节点，避免长距离回线。恢复使用同一任务 thread_id 与 `Command(resume=...)`，回到各自中断节点。
- `variants` 内部可再次调用编排与校验；不是另起一套调查流程。A/B 不同方案不保证总能生成。
- `END` 后，有候选时进入 `waiting_choice`，由业务 API 在用户选择后保存；无候选时 Worker 复查并保存版本。
- 纯模型基线没有外部事实核验；预订工具只记录意向，不代表下单或付款。

## 五张图与源码

### 01 · 整体架构

回答系统由哪些部分组成，以及一次规划如何形成反馈闭环。

![整体架构](../assets/architecture/structured/01-overall.png)

[SVG](../assets/architecture/structured/01-overall.svg) · [PNG](../assets/architecture/structured/01-overall.png) · [可编辑 draw.io](../assets/architecture/structured/01-overall.drawio) · [旧版 Mermaid 逻辑参考](diagrams/01-overall.mmd) · [English SVG](../assets/architecture/structured/01-overall.en.svg) · [English draw.io](../assets/architecture/structured/01-overall.en.drawio)

核对入口：`api.py / social_api.py / worker.py / agent/graph.py`。

<details>
<summary>展开旧版 Mermaid 逻辑参考（布局与新版不同）</summary>

```mermaid
flowchart TB
  WEB["旅行工作台 · React<br/>描述需求 / 探索地点 / 调整行程 / 查看依据"]
  API["FastAPI 接口<br/>身份认证 / 行程权限 / REST / SSE"]
  BIZ["旅行业务服务<br/>确定性访谈 / 吃住行 / 收藏 / 资料与导出"]
  RUN["异步规划引擎<br/>Celery Worker + LangGraph + Harness<br/>调查 → 编排 → 约束校验 → 审阅"]
  MODEL["可切换模型网关"]
  TOOLS["旅行事实工具<br/>高德 / 美团"]
  KB["私人资料检索<br/>解析 / BGE / 混合召回"]
  SQL[("MySQL<br/>任务 / 行程版本 / 图检查点 / 事件")]
  REDIS[("Redis<br/>Celery broker / 临时缓存")]
  ES[("Elasticsearch<br/>全文与向量派生索引")]
  WEB -->|HTTP 请求| API --> BIZ
  BIZ -->|生成 / 调整任务| RUN
  BIZ -->|查询与写入业务状态| SQL
  RUN --> MODEL & TOOLS & KB
  RUN <-->|队列投递 / 消息消费| REDIS
  RUN <-->|读取任务 / 恢复检查点 / 保存结果| SQL
  KB --> ES
  SQL -.->|读取消息与执行事件| API
  API -.->|SSE 持续反馈| WEB
  classDef default fill:#ffffff,stroke:#9aa9b4,color:#263743,stroke-width:1px
  classDef accent fill:#eaf1f6,stroke:#426b86,color:#203b4d,stroke-width:1.5px
  classDef store fill:#f0f2f4,stroke:#889aa7,color:#263743
  class RUN accent
  class SQL,REDIS,ES store
```

</details>

### 02 · 分层架构

按职责划分交互、业务、编排、适配和数据层，突出模块边界。

![分层架构](../assets/architecture/structured/02-layered.png)

[SVG](../assets/architecture/structured/02-layered.svg) · [PNG](../assets/architecture/structured/02-layered.png) · [可编辑 draw.io](../assets/architecture/structured/02-layered.drawio) · [旧版 Mermaid 逻辑参考](diagrams/02-layered.mmd)

核对入口：`frontend/src / *_api.py / agent / providers / knowledge.py`。

<details>
<summary>展开旧版 Mermaid 逻辑参考（布局与新版不同）</summary>

```mermaid
flowchart TB
  L1["交互层 · React 旅行工作台<br/>对话规划 / 地点探索与地图 / 每日行程与路书"]
  L2["接入与业务层 · FastAPI<br/>认证与成员权限 / 确定性访谈 / 行程版本 / 吃住行与导出"]
  L3["异步编排层 · Celery Worker + LangGraph<br/>任务派发与租约 / 领域调查 / 行程编排 / 约束校验与恢复"]
  L4["能力适配层 · 可替换能力<br/>模型网关与结构化输出 / 高德与美团 / 文档解析与混合检索"]
  L5["数据基础层 · 职责分离<br/>MySQL：业务事实与检查点 / Redis：消息与缓存 / ES：派生索引"]
  L1 --> L2 --> L3 --> L4 --> L5
  G["横切关注点<br/>用户隔离 / 来源与未知信息 / 事件记录<br/>执行阶段：Harness 调用预算与能力授权"]
  G -.-> L2
  G -.-> L3
  class L3,G accent
  class L5 store

classDef default fill:#ffffff,stroke:#9aa9b4,color:#263743,stroke-width:1px
classDef accent fill:#eaf1f6,stroke:#426b86,color:#203b4d,stroke-width:1.5px
classDef store fill:#f0f2f4,stroke:#889aa7,color:#263743
classDef note fill:#fbf5e9,stroke:#b39660,color:#594a32,stroke-dasharray:4 3
```

</details>

### 03 · LangGraph 工作流

逐一对应实际节点、纯模型分支、约束回路和持久化中断。

![LangGraph 工作流](../assets/architecture/structured/03-langgraph.png)

[SVG](../assets/architecture/structured/03-langgraph.svg) · [PNG](../assets/architecture/structured/03-langgraph.png) · [可编辑 draw.io](../assets/architecture/structured/03-langgraph.drawio) · [旧版 Mermaid 逻辑参考](diagrams/03-langgraph.mmd) · [English SVG](../assets/architecture/structured/03-langgraph.en.svg) · [English draw.io](../assets/architecture/structured/03-langgraph.en.drawio)

核对入口：`agent/graph.py:build_graph / worker.py:execute / social_api.py:choose_variant`。

<details>
<summary>展开旧版 Mermaid 逻辑参考（布局与新版不同）</summary>

```mermaid
flowchart TB
  START(["START"]) --> REQ["requirements · 需求确认<br/>日期 / 出发地；允许无日期草案时可跳过"]
  REQ --> STRATEGY{"strategy = pure<br/>且满足纯模型条件？"}
  STRATEGY -->|是| PURE["pure · 无工具模型草案<br/>明确标记未经事实核验"] --> END(["END"])
  STRATEGY -->|否| DEL["delegate · 选择必要调查领域"]
  DEL --> DEST["destination · 检索候选地点<br/>保留已锁定地点与来源"]
  DEST --> RES["research · 按需顺序调查<br/>天气 / 住宿商品 / 私人资料"]
  RES --> ARR["arrange · 按日编排候选地点 ID"]
  ARR --> VAL["validate · 查询实际路线并校验约束"]
  VAL --> REV["review · 审阅冲突与警告"]
  REV --> CHANGE{"需求是否不同于<br/>当前 plan.requirements？"}
  CHANGE -->|已改变| ARR
  CHANGE -->|未改变| VAR["variants · 按需生成 A/B<br/>复用研究结果；内部再次编排与校验"]
  VAR --> NAR["narrate · 生成说明 / 流式输出"] --> END
  REQ -.->|必要信息缺失时 interrupt| WAIT["图暂停 · MySQL checkpoint<br/>等待补充 / 取舍<br/>Command resume 在原中断节点恢复"]
  REV -.->|首次发现相关冲突时 interrupt| WAIT
  END -.-> POST["图外业务处理 · Worker / API<br/>有候选：waiting_choice → 用户选择后保存<br/>无候选：版本复查 → 保存 Revision"]
  class REQ,ARR,VAL,REV accent
  class WAIT,POST note

  classDef default fill:#ffffff,stroke:#9aa9b4,color:#263743,stroke-width:1px
  classDef accent fill:#eaf1f6,stroke:#426b86,color:#203b4d,stroke-width:1.5px
  classDef store fill:#f0f2f4,stroke:#889aa7,color:#263743
  classDef note fill:#fbf5e9,stroke:#b39660,color:#594a32,stroke-dasharray:4 3
```

</details>

### 04 · 业务架构

从需求、推荐、确认、调整到导出，说明产品闭环与支撑能力。

![业务架构](../assets/architecture/structured/04-business.png)

[SVG](../assets/architecture/structured/04-business.svg) · [PNG](../assets/architecture/structured/04-business.png) · [可编辑 draw.io](../assets/architecture/structured/04-business.drawio) · [旧版 Mermaid 逻辑参考](diagrams/04-business.mmd)

核对入口：`conversation.py / discovery_api.py / services_api.py / social_api.py / exports.py`。

<details>
<summary>展开旧版 Mermaid 逻辑参考（布局与新版不同）</summary>

```mermaid
flowchart TB
  USER["旅行者的目标：把需求变成可调整的每日行程"]
  subgraph PLAN["规划主闭环"]
    direction LR
    NEED["描述需求<br/>城市 / 日期 / 预算 / 偏好"] --> CAND["调查与推荐<br/>有来源的候选与方案"]
    CAND --> CONF["确认方案<br/>需要比较时先选 A/B"]
    CONF --> TRIP["管理行程<br/>按天查看 / 锁定 / 调整"]
    TRIP --> BOOK["带走路书<br/>分享 / PDF / Markdown"]
    TRIP -->|提出新要求| NEED
  end
  USER --> PLAN
  subgraph SUPPORT["支撑旅行规划的业务能力"]
    direction LR
    EXP["地点探索与收藏<br/>景点 / 餐饮 / 住宿"]
    DAILY["每日吃住行与预算<br/>替换餐厅 / 住宿 / 交通方式"]
    DOC["私人资料<br/>导入攻略 / 检索原文位置"]
    COL["账户与行程协作<br/>owner / editor / viewer"]
  end
  SUPPORT -.->|候选 / 证据 / 吃住行 / 协作授权| PLAN
  RULE["业务底线：未知信息待核实 · 修改保留版本 · 来源可以检查<br/>预订只记录意向，不执行付款"] -.-> PLAN
  class CAND,TRIP accent
  class RULE note

  classDef default fill:#ffffff,stroke:#9aa9b4,color:#263743,stroke-width:1px
  classDef accent fill:#eaf1f6,stroke:#426b86,color:#203b4d,stroke-width:1.5px
  classDef store fill:#f0f2f4,stroke:#889aa7,color:#263743
  classDef note fill:#fbf5e9,stroke:#b39660,color:#594a32,stroke-dasharray:4 3
```

</details>

### 05 · 技术架构

列出客户端、Python 服务、执行组件、基础服务和外部平台的技术组合。

![技术架构](../assets/architecture/structured/05-technical.png)

[SVG](../assets/architecture/structured/05-technical.svg) · [PNG](../assets/architecture/structured/05-technical.png) · [可编辑 draw.io](../assets/architecture/structured/05-technical.drawio) · [旧版 Mermaid 逻辑参考](diagrams/05-technical.mmd)

核对入口：`compose.yaml / requirements.lock.txt / frontend/package.json / models / mcp/server.py`。

<details>
<summary>展开旧版 Mermaid 逻辑参考（布局与新版不同）</summary>

```mermaid
flowchart TB
  subgraph CLIENT["客户端技术"]
    direction LR
    C1["React 18 / TypeScript / Vite<br/>Router / TanStack Query"] ~~~ C2["AMap JS SDK<br/>真实地图与路线"] ~~~ C3["外部 MCP 客户端<br/>可选入口"]
  end
  subgraph ACCESS["应用接入 · Python 3.11"]
    direction LR
    A1["FastAPI + Uvicorn<br/>REST / SSE / 认证授权"] ~~~ A2["自实现 MCP stdio 服务<br/>JSON-RPC / scope / AuditLog"]
  end
  subgraph EXEC["异步执行与能力组件"]
    direction LR
    E1["Celery + LangGraph<br/>任务 / 检查点 / 中断恢复"] ~~~ E2["模型网关 + Provider 适配器<br/>LangChain / 结构化输出 / 高德 / 美团 CLI"] ~~~ E3["文档 RAG<br/>解析 / BGE / BM25 + kNN / RRF"]
  end
  subgraph DATA["本地基础服务与文件"]
    direction LR
    D1[("MySQL 8.4<br/>SQLAlchemy / Alembic")] ~~~ D2[("Redis 7.4<br/>broker / 临时缓存")] ~~~ D3[("Elasticsearch 8.17<br/>全文 / 512 维向量")] ~~~ D4["本地 data 文件 / Mailpit<br/>原文附件 / 测试邮件"]
  end
  subgraph EXT["外部平台 · 按凭证与配置启用"]
    direction LR
    X1["模型提供者<br/>OpenAI 兼容 / Gemini / Ollama 等"] ~~~ X2["高德地图服务<br/>POI / 路线 / 天气 / 底图"] ~~~ X3["美团官方 CLI<br/>酒旅 / 美食信息查询"]
  end
  CLIENT -->|HTTP / SSE 或 stdio| ACCESS
  ACCESS -->|业务请求与工具调用| EXEC
  EXEC -->|状态 / 检索 / 队列与缓存| DATA
  EXEC -->|模型推理与平台查询| EXT
  class E1,E2 accent
  class D1,D2,D3 store

classDef default fill:#ffffff,stroke:#9aa9b4,color:#263743,stroke-width:1px
classDef accent fill:#eaf1f6,stroke:#426b86,color:#203b4d,stroke-width:1.5px
classDef store fill:#f0f2f4,stroke:#889aa7,color:#263743
classDef note fill:#fbf5e9,stroke:#b39660,color:#594a32,stroke-dasharray:4 3
```

</details>

## 重新渲染

```bash
# 仅安装到被忽略的 reports 目录，不改应用依赖。
npm install --prefix reports/architecture-tools --no-save --package-lock=false --ignore-scripts mermaid@11
node scripts/render_architecture.mjs
```

输出位置、渲染比例与浏览器配置在脚本顶部 `CONFIG`。源码在 `docs/architecture/diagrams/`，输出在 `docs/assets/architecture/structured/`。
GitHub 使用 Mermaid 代码块时采用自身主题；SVG/PNG 保留本次导出样式。图均已解析并导出，不需要联网查看图片或选图页。
