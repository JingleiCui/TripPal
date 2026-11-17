# 旅行规划 Agent 项目分析报告（对标 TREK）

> 目的：梳理第三方服务接入现状（是否接入 / 角色 / 调用深度），并对照 [liketrek/TREK](https://github.com/liketrek/TREK)
> 梳理我们的优势与不足。聚焦 **Agent 能力**——因为本项目定位是 AI 智能体应用开发的作品集。

---

## 一、第三方服务接入现状

### 1.1 高德地图（Amap）——已深度接入，是事实上的"空间事实源"

- **接入代码**：`backend/travel_agent/providers/amap.py`
- **角色**：地点、路线、天气、地理编码的**唯一权威来源**；前端 JS API（`amap_js_key`）提供底图（默认显示）。
- **实际调用深度**：

| 高德能力 | 接口 | 是否已用 |
|---|---|---|
| 关键字 POI 搜索 | `/v3/place/text` | ✅ `search_places` |
| 周边搜索 | `/v3/place/around` | ✅ `search_nearby`（含餐饮门店过滤） |
| 路线规划（步行/公交/驾车） | `/v3/direction/*` | ✅ `route_between` |
| 天气 | `/v3/weather/weatherInfo` | ✅ `weather` |
| 地理编码 | `/v3/geocode/geo` | ✅ `resolve_origin` / 天气前置 |
| 前端 JS 地图 | JS API | ✅ 旅程页默认常驻面板 |
| POI 详情 / 距离矩阵 / 实时路况 / 行政区 / 输入提示 / 室内景区图 | — | ❌ 未用 |

- **充分度评估**：对我们"地点→路线→天气"主链路已够用（**中高**）；但潜力只挖了约一半，且**单一来源、无交叉验证**（如评分/点评）。坐标全程 GCJ-02，未与外部 WGS-84 混用（工程正确性已保证）。

### 1.2 美团（Meituan）——已接入但很浅，仅"酒旅商品查询"

- **接入代码**：`backend/travel_agent/providers/meituan.py`
- **接入方式**：调用官方 CLI 子进程 `mttravel`（**非直连 API**），`subprocess.run(..., shell=False)`。
- **角色**：酒店 / 门票 / 交通商品的**原文价格与链接**检索（只读信息服务），供"住宿与商品"领域 Agent 使用。
- **关键事实**：**美食 / 餐厅检索不走美团**，用的是高德 POI 文本搜索。所以你之前反馈的"餐饮管理公司 / 股份公司"问题根源在高德，与美团无关——现已用"分类路径 + 名称"双重信号在 `amap.py` 的 `_is_dining_outlet` 剔除。
- **未使用**：结构化商品 API、点评/评分、下单/支付回调、预订库存。
- **充分度评估（2026-11 已深化）**：从"浅"提升到"中"。新增 `food_recommend`（本地人气餐厅 / 特色菜 / 团购套餐）与 `deal_search`（酒店 / 门票 / 交通优惠与团购），并在 `discovery_api._merge_meituan_food` 中把美团美食结果**合并进"餐厅美食"检索**（8s 短超时优雅降级，不影响高德兜底）。前端 `Discovery.tsx` 已为美团卡片渲染"美团"徽标、价格与"在美团查看"外链，且不进入收藏/地图（实时团购不落为固定地点）。`meituan_enabled` 仍默认 `False`，且**绝不假装已下单/已预订**（只返回原文价格与链接）。

### 1.3 模型 / LLM —— 已抽象但未默认开启

- 支持 OpenAI 兼容（百炼 Qwen）/ Gemini / Ollama 三套 provider（`model_enabled` 默认 `False`）。
- 默认走**合成夹具**（fixture）流程：**不调真实模型、不调真实平台**，仅用于学习界面与工程链路。

### 1.4 其他

- **Elasticsearch**：仅用于**用户私有资料 RAG**（BGE-zh 512 维 + ES 全文/kNN + RRF），不是第三方业务服务。
- **无** Google、无 booking、无支付、**无 MCP server**。

### 1.5 接入矩阵速览

| 服务 | 是否接入 | 角色定位 | 调用深度 | 默认开启 |
|---|---|---|---|---|
| 高德 | ✅ 是 | 空间事实源（地点/路线/天气/地理编码/底图） | 中高（约 9/11 主能力，已补 POI 详情/距离矩阵/实时路况） | 是（需 key） |
| 美团 | ⚠️ 中（已深化） | 酒旅/门票/交通商品 + 美食/团购/优惠原文检索 | 中（3 个 CLI 文本查询，美食合并进发现页） | 否 |
| 云端模型 | ✅ 抽象 | 调查/编排/结构化输出 | 中（结构化+1 次修正+业务校验） | 否（fixture） |
| ES | ✅ 是 | 私有资料 RAG | 中（切分+向量+融合） | 是 |
| MCP server（自研） | ✅ 已实现 | 受治理、可审计、可组合的工具层（10 工具 + scopes + 审计日志） | 中（JSON-RPC over stdio，可被外部系统调用） | 否（开关 `mcp_enabled`） |
| 外部 MCP 桥接 | 🔶 脚手架 | 经子进程 stdio 接入第三方 MCP（如高德官方 MCP） | 骨架（未默认接入） | 否 |

---

## 二、对标 TREK：优势与不足（聚焦 Agent 能力）

### 2.1 TREK 的 Agent 相关设计（提炼，来自其 README）

- **AI 助手（默认关闭）**：聊天式规划，跨行程/日志/Studio 工作；**"你说了算"**——每次改动先生成一张**卡片**，由用户应用或丢弃，**15 分钟内可撤销**；附件（订单确认 / GPX / 照片）会让助手**主动建议动作**。
- **MCP server（默认关闭）**：OAuth 2.1 + PKCE、动态客户端注册、**410 工具 / 30 资源 / 4 prompts / 35 scopes（17 组）**、审计日志；**12 个 addon 门控**决定一个会话能看到哪些工具，且可热更新重新注册。
- **地点 / 路线 / 天气**：TREK 自有索引 + OpenStreetMap（免 key）或 Google/Amap（带 key）；描述/营业时间/照片来自 Wikipedia/Wikidata/Commons；路线用最近邻 + 2-opt 自动排序，逐段交通方式（OSRM/Valhalla），可推送到 7 个导航 App；天气用 Open-Meteo。

### 2.2 我们的优势（Agent 能力视角）

| 维度 | 我们的做法 | 为什么是优势 |
|---|---|---|
| **可验证、有来源** | 模型只能从工具返回的候选 ID 中选；`validate_selection` 拒绝幻觉 ID、遗漏锁定项、跨城混入、日期冲突 | Agent **不会编造业务状态**——可靠性是智能体的核心能力 |
| **硬约束由代码强制** | 锁定地点、日期、时间窗由 `planning.py` 校验，冲突不静默覆盖 | 把"必须正确"的事交给确定性代码，模型只做开放权衡 |
| **多 Agent 编排** | LangGraph：supervisor（领域选择）→ domain 调查员（有界工具集、≤3 轮）；显式声明"多 Agent 用于隔离而非提速" | 工具/上下文隔离清晰，且**诚实标注**非并行 |
| **可靠性工程** | 任务回执幂等键、租约 + fencing token + 心跳、版本事务、重放保护 | Agent **能在故障/并发下存活**——可运营性 |
| **认知诚实** | 未知费用≠0、未核实路线不展示为"已确认"、工具失败不返回猜测值 | 校准（calibration）是成熟 Agent 的标志 |
| **结构化输出治理** | `with_structured_output` + 1 次有界修正 + 业务校验，绝不编造兜底 | 输出可控、可测 |
| **模型可插拔** | 百炼 / Gemini / Ollama 三选一 | 不被单一厂商锁定 |

### 2.3 我们的不足（Agent 能力视角）

| 维度 | 现状 | 差距 |
|---|---|---|
| **无 MCP server** | 工具全部内部调用，对外不可组合/不可审计 | TREK 有 410 工具 + OAuth + scopes + 审计。**这是作品集里最该补的"智能体可治理/可组合"信号** |
| **人机协同偏粗** | 仅 `interrupt()` 做需求确认与冲突取舍 | TREK 是**逐变更卡片 + 15 分钟撤销**，更细粒度、更安全 |
| **无附件驱动的工具触发** | RAG 仅文本，未与 Agent 动作挂钩 | TREK 丢入订单/GPX/照片即触发助手建议动作 |
| **工具面太窄** | 实际工具约 6 个（search_places/weather/meituan/knowledge/route/resolve_origin） | TREK 暴露 410 工具；我们缺少 POI 详情、距离矩阵、路况、预订意图等 |
| **无法闭环执行** | 仅信息服务，无预订/支付/库存 | Agent 只能"规划"不能"办成" |
| **长程记忆未验证** | 上下文确定性裁剪，无 20+ 轮语义不丢失的证明 | 不能声称已解决长期记忆 |
| **美食数据质量依赖单源** | 仅靠高德 POI，无点评/评分交叉 | TREK 从 Wikidata/Commons 补描述与评分 |

> **2026-11 落地状态**：表中前 4 项（无 MCP server、人机协同偏粗、无附件驱动、工具面太窄）与"美食单源"已在本项目实现，详见**第六节**。`无法闭环执行` 与 `长程记忆未验证` 仍属诚实边界——我们只生成"去平台下单/预订"的链接与意图，**绝不假装已订/已付**，也绝不声称已解决 20+ 轮长期记忆。

---

## 三、可借鉴的具体设计点（只取 Agent 能力相关，不照搬产品功能）

> 原则：TREK 的"协作/打包/日记/离线 PWA"等产品功能不必学；只学它**强化 Agent 能力**的机制。

### 3.1 【最高优先级】把工具暴露成受治理的 MCP server（对标 410 工具 + MCP）
- **做法**：用 FastMCP 把现有工具包一层，定义 **scopes**：`read_places` / `read_routes` / `read_weather` / `query_lodging` / `edit_plan`，并写**审计日志**（谁、何时、调了什么工具、返回是否成功）。
- **为什么强化 Agent 能力**：把"一个内部脚本"升级为"可被外部系统调用、可授权、可审计的智能体服务"——这正是 AI Agent 应用开发的标杆能力。我们的工具已天然类型化（Pydantic/LangChain），改造成本低。

### 3.2 【次高】逐变更的"卡片确认 + 撤销窗口"（对标 apply/discard card + undo 15min）
- **做法**：在现有"版本系统"之上，新增**待应用变更卡片** + **时间盒撤销**。Agent 每次想改行程先生成预览，用户一键应用或丢弃；15 分钟内可回退。
- **为什么强化 Agent 能力**：把"粗粒度 interrupt 阻塞"升级为"细粒度、可逆的协同"——让 Agent 持续行动的同时，用户始终保有控制权（delegation without loss of agency）。这比我们的 `interrupt` 更顺滑、更 Agent-native。

### 3.3 【中】附件驱动的工具触发（对标 booking/GPX/photo → 助手建议动作）
- **做法**：复用现有文件解析（TXT/PDF/DOCX），但把"上传"和"Agent 动作"打通——用户丢入订单确认 → Agent 建议"导入为住宿/票务卡片"；丢入 GPX → 建议"加入当天路线"。
- **为什么强化 Agent 能力**：让 Agent **作用于真实工件**（grounding in artifacts），而不是只在对话里推理。

### 3.4 【中】能力门控（对标 12 addon gates 热更新可见工具）
- **做法**：用"能力开关"动态决定一个会话能看到的工具（如未配美团则隐藏 `query_lodging`，未配地图则隐藏路线工具），且与我们的**工具预算/租约**互补——一个在"能力层"、一个在"调用层"做权限收敛。
- **为什么强化 Agent 能力**：防止"过度授权会话"，是 Agent 安全治理的进阶实践。

### 3.5 【低，按需】丰富工具面（对标"410 工具"的设计原则而非数量）
- 不必追数量，但可补几个**高价值**动作：POI 详情（补营业时间/照片/评分）、距离矩阵（批量路线优化）、实时路况（路线可信度）、预订意图（生成下单链接而非假装已订）。

---

## 四、这些差异如何体现并强化 Agent 能力（重点）

1. **可信赖性（Reliability）**
   - 我们的"来源约束 + 硬约束代码强制 + 认知诚实"意味着 Agent **不会把没查到的东西说成已确认**。`validate_selection` 拒绝无来源 ID、遗漏锁定项、跨城混入——这是 Agent 在"事实正确性"上的能力体现。
   - 对照：TREK 的卡片确认更偏"用户兜底"，我们的"代码在落库前强制校验"更能从系统层面杜绝幻觉。

2. **可运营性（Operability）**
   - 任务回执幂等键 + 租约 + fencing token + 版本事务，让 Agent **在崩溃、重放、并发修改下仍能给出一致结果**。这是把 Agent 从"演示脚本"提升到"可部署服务"的能力差距所在。

3. **可治理 / 可组合（Governance & Composability）**
   - 引入 MCP + scopes + 审计后，Agent 从"封闭内部逻辑"变为"对外可授权、可审计、可组合的智能体服务"。**这是当前作品集最缺、也最能打动面试官的一环**——它直接回答"你的 Agent 怎么融入更大系统"。

4. **可控协同（Human-in-the-loop）**
   - 把粗粒度 interrupt 升级为"逐变更卡片 + 撤销窗口"，体现 Agent **懂得把控制权交还人类而不阻断自身推进**。这是现代 Agent 设计（如 Claude Computer Use、各种 agentic workflows）的共同范式。

5. **认知校准（Calibration）**
   - "未知≠0、未核实≠已确认"贯穿全栈，说明 Agent **知道自己的能力边界**——比"看起来成功"更重要，也是评测里最容易区分初级与成熟 Agent 的标尺。

---

## 五、给求职材料的落点建议

- **一句话定位**：一个"以有版本、可溯源、硬约束受代码保障的行程"为核心对象的旅行规划智能体，把开放调查交给 Agent、把日期/费用/权限/版本交给代码。
- **必讲三点**：① 为什么多 Agent（按领域隔离工具与上下文，非为提速）；② 为什么工具必须受约束（候选 ID 来自工具、模型不能越权查网络/账号）；③ 可靠性四件套（幂等/租约/版本/重放）。
- **加分路线图**（已落地，见第六节）：MCP 受治理工具层 + 逐变更卡片撤销 + 附件驱动动作 + 能力门控 + 工具面扩展 + 美团深化。面试里可讲"这些从设计点变成了可运行代码"。
- **诚实边界**（已在 `docs/面试讲解与学习任务.md` 固化）：本地工程验收 ≠ 生产效果；合成夹具 ≠ 真实模型；未配置 key 时不会偷偷以合成替代真实。

---

## 六、已落地实现（2026-11）：把"路线图"变成代码

> 上文第三节的 5 个优先级 + 美团深化 + 外部 MCP 探索，已全部落地为可运行代码与前端呈现。以下按能力逐条给出**文件清单、设计要点与验证方式**。测试：`.venv/bin/python -m pytest` 全绿（115 passed）；后端 46 条路由；新端点已注册并受 `401` 鉴权保护。

### 6.1 【最高优先级】受治理的 MCP server（scopes + 审计日志）
- **新增**：`backend/travel_agent/mcp/server.py`（`TravelMCPServer`，自研 JSON-RPC over stdio，不依赖未安装的 `fastmcp`，scopes/审计完全可控）。
- **10 个工具** + 每个工具的 `scope`：`amap_search_places / amap_poi_detail / amap_route / amap_distance_matrix / amap_traffic_route / amap_weather / meituan_query / meituan_food / knowledge_search / booking_intent`。
- **授权**：`_permitted(scope)` 校验调用方授予的 scopes，含通配 `travel_agent:tools`；越权调用被拒并记录。
- **审计**：每次工具调用写 `AuditLog`（owner / actor / scope / tool / arguments / success / error / detail）。
- **配置**：`config.py` 新增 `mcp_enabled / mcp_transport / mcp_scopes / mcp_bind / mcp_port`。
- **运行**：`PYTHONPATH=backend .venv/bin/python -m travel_agent.mcp.server`（stdio 模式，可由任意 MCP 客户端以子进程拉起）。
- **强化点**：把"内部脚本"升级为"对外可授权、可审计、可组合"的智能体服务——直接回答"你的 Agent 怎么融入更大系统"。

### 6.2 【次高】逐变更"卡片确认 + 撤销窗口"（对标 apply/discard + undo 15min）
- **后端**：`pending_api.py`（`GET /trips/{ident}/pending-changes`、`POST .../undo`、`POST .../dismiss`）；`worker.py` 在每次规划落地后写一张 `PendingChange`（diff 摘要 + 15 分钟 `expires_at`）；DB 新增 `PendingChange` 模型，`undo` 通过 `Revision` 回到上一版本。
- **前端**：`TripExperience.tsx` 在行程顶部渲染"撤销窗口"卡片条，带**实时倒计时**；超时后显示"已超出撤销窗口 · 改动已保留"，历史仍可恢复（比 `interrupt` 阻塞更顺滑、更 Agent-native）。
- **强化点**：Agent 提交改动后不阻断自身，控制权交还用户——delegation without loss of agency。

### 6.3 【中】附件驱动的工具触发（对标 booking/GPX/photo → 助手建议动作）
- **后端**：`attachments_api.py`（`POST /attachments` 解析并生成建议、`GET /attachments`）；`parsers/`（GPX 用 `xml.etree` + haversine 算里程/起终点；订单文本用正则抽城市/日期/金额/场次，含直辖市白名单）。
- **前端**：`ConversationWorkspace.tsx` 对话输入框新增"添加附件"控件，上传后在卡片里展示**解析结果与建议**，一键"把建议交给助手"发起规划。
- **强化点**：让 Agent 作用于真实工件（grounding in artifacts），而非只在对话里推理。

### 6.4 【中】能力门控（对标 12 addon gates 热更新可见工具）
- **新增**：`capabilities.py`（`TOOL_CAPABILITIES` 工具→能力、`CAPABILITY_TOOLS` 反向映射、`resolve_enabled_tools`、`capability_scope`）；`harness.filter_tools(tools)` 按会话 `capabilities` 收敛可见工具。
- **接线**：`RunRequest.capabilities`、`worker.Harness(..., capabilities=...)`；与既有**工具预算/租约**互补（能力层收敛"看得到什么"，调用层收敛"调多少次"）。
- **强化点**：防止"过度授权会话"，是 Agent 安全治理的进阶实践。

### 6.5 【低，按需】高价值工具面（对标 410 工具的设计原则）
- **高德适配器** `providers/amap.py` 新增：`poi_detail`（营业时间/照片/评分）、`distance_matrix`（批量路线优化）、`traffic_route`（路线可信度）。
- **预订意图** `providers/booking.py`：`build_intent` 生成酒店/门票/交通/餐饮的下单意图，**只给链接、不假装已订**。
- **图编排** `agent/graph.py`：domain agent 新增内联工具 `poi_detail / search_dining（美团美食）/ plan_booking（预订意图）`。

### 6.6 美团深度利用（见 §1.2）
- `meituan.food_recommend` + `meituan.deal_search`；发现页"餐厅美食"合并美团结果（短超时降级）；前端"美团"徽标 + 价格 + 外链。

### 6.7 外部 MCP 接入探索（与合规/数据主权权衡）
- **新增**：`adapters/external_mcp.py`（`ExternalMCPBridge`，子进程 stdio MCP 客户端骨架）+ `KNOWN_EXTERNAL_MCPS`（含高德官方 MCP 经 `npx` 的占位）。
- **可接入候选**（仅作架构示意，默认不接，需评估数据出境与授权）：高德官方 MCP、12306/飞常准（车次航班）、Booking.com / 携程（`amap` 已覆盖地点，外部更适合库存与下单）、天气类 MCP。**原则**：地图与美食以自有 `amap`/`meituan` provider 为主（数据主权在己、可控降级），外部 MCP 只在"补齐自有缺失能力"时才引入，且一律走 scope 授权 + 审计。
- **未做**：未把外部 MCP 默认接入图编排——保持"自有 provider 为主、外部为补充"的边界，避免把核心链路外包给不可控第三方。

### 6.8 验证清单
- 单元测试：`.venv/bin/python -m pytest -q` → **115 passed**（新增 `test_capabilities / test_mcp_server / test_attachments / test_providers_tools / test_discovery_mcp_food` 等）。
- 后端路由：health 200，mysql/redis/elasticsearch ready；`/api/v1/attachments`、`/api/v1/trips/{id}/pending-changes(-/{id}/undo|dismiss)` 注册并 `401` 鉴权。
- 前端：`tsc --noEmit` 通过；新组件（`agent-capabilities.css`）已接入 `main.tsx`。
- 诚实边界：美团 `configured_not_verified`（CLI 未配置），`food_recommend` 在未配置时**优雅降级为空**，不影响高德结果——不假装已联网。

---

*生成依据：阅读了 `backend/travel_agent/{agent/*,providers/*,config.py,planning.py,conversation.py,discovery_api.py,mcp/*,parsers/*,adapters/*,capabilities.py,pending_api.py,attachments_api.py}`、`frontend/src/{TripExperience.tsx,ConversationWorkspace.tsx,Discovery.tsx,api.ts,types.ts,agent-capabilities.css}`、`docs/架构与设计取舍.md`、`docs/面试讲解与学习任务.md`，以及 TREK 仓库 README。*
