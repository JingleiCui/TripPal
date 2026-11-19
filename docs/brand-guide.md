# TripPal 旅伴 · 品牌与界面规范

定位：**AI 旅行规划智能体助手**。主流程是「描述需求 → 比较方案 → 确认并调整行程」。
角色的亲和感用于降低规划门槛；产品内容围绕地点、路线、时间、预算与来源组织。

## 名称与语言

| 项目 | 规范 |
|---|---|
| 英文名称 | **TripPal**，由 Trip + Pal 组成，T 与 P 大写，与仓库名保持一致 |
| 中文名称 | **旅伴**，和英文名称一起展示 |
| 首次出现 | **TripPal 旅伴 · AI 旅行规划智能体助手** |
| 主标语 | **一句话，安排好下一程。** |
| 英文标语 | **Say it. Plan it. Go.** |
| 核心动词 | 描述、生成、推荐、比较、确认、调整、导出 |
| 推荐产品介绍 | 将目的地、日期、预算与偏好，整理为可调整、保留来源的每日行程。 |
| 文案原则 | 说清操作与结果；未知票价、天气和开放信息标注待核实；示例内容明确标注 |

## 保留现有 Logo

![正式 Logo](assets/brand/tripal-mark.png)

笑脸旅行箱的箱身代表旅行；笑脸和腮红代表轻松；头顶**黄色四角星光**代表智能辅助。
形状、五官位置、提手与星光全部沿用现有版本，无新增角色或重绘替换。

- 单一源码：[TripalLogo.tsx](../frontend/src/components/TripalLogo.tsx)。
- [独立 SVG](assets/brand/tripal-mark.svg) / [透明 PNG](assets/brand/tripal-mark.png)。
- README 顶部使用正式 Logo、原生文字标题 **TripPal 旅伴** 和 slogan。旧版 `tripal-banner.png` 及既有录屏、截图作为历史素材保留；不通过修改录屏或验证截图来追溯改名。
- 页面 favicon：[正式 SVG 副本](../frontend/public/tripal-mark.svg)。
- 浅底正常展示，珊瑚色或深底使用白色底托；保持原始比例，四周至少留出 1/8 图形宽度。
- 界面图中的 AI 渲染角色只是概念表现，正式应用与 README 使用源码导出的 SVG/PNG。
- 更新正式组件后运行 `node scripts/export_brand_assets.mjs`，同步导出素材。

## 视觉规范

设计依据为 `frontend-design` 的主题聚焦、留白与视觉复查流程，以及 `ui-ux-pro-max`
的层级、对比度、图标和响应式规则。技能检索中的极简几何布局用于收敛装饰，颜色保留旅行品牌的柔和感。
**12px 圆角是用户指定方向下的本项目决策，不是技能的通用默认值。**

| 令牌 | 值 | 用途 |
|---|---|---|
| Cream | `#FFF7F1` | 页面底色 |
| Coral | `#FF8A6B` | Logo、插画与辅助强调 |
| Action coral | `#B84830` | 主按钮、可操作文本；白字按钮 |
| Mint | `#5FC9AC` | 分类辅助色；正文用更深的 `#24745D` |
| Butter | `#FFCE73` | 智能星光、轻提示 |
| Ink | `#3B3432` | 标题与主要正文 |
| Muted | `#716762` | 浅底上的辅助正文 |
| Surface | `#FFFFFF` | 内容卡片 |
| Radius | **`12px`** | 卡片、输入框、按钮、标签、导航、搜索条与路书容器 |
| Space | `8 / 16 / 24 / 32 / 48px` | 主要版面节奏；4px 用于图标与细小间距 |

头像、地图定位符和吉祥物自身的曲线保留其形义。其余界面避免胶囊形、全圆按钮、大圆角框和多种圆角混搭。
运行时规范位于 [tripal.css](../frontend/src/tripal.css)，从 `--tp-radius` 同步组件几何。

- 字体：`Avenir Next / PingFang SC / Microsoft YaHei / sans-serif`，随操作系统回退，无远程字体请求。
- 层级：桌面主标题 44px，上下文标题 28px，区块 20–24px，正文 14–16px，辅助 12px；移动主标题 28px。
- 图标：统一 Lucide 线性图标；图标按钮有可访问名称，交互区域至少 44px。
- 正文与背景对比度目标 4.5:1；浅珊瑚和薄荷只作装饰底色，不能直接承担浅底正文。
- 动效只解释状态或操作反馈；尊重 `prefers-reduced-motion`，不自动轮播目的地卡片。
- 页面内卡片按内容分组，不给每个文本片段再套一层卡片；同屏主操作突出，来源信息保留。

## 三个核心页面

| 页面 | 布局与重点 |
|---|---|
| 首页 | 左对齐的规划标语与需求输入；单一开始规划动作；地点灵感放在输入之后 |
| 搜索 / 推荐 | 城市与分类筛选在上；左侧卡片随滚动真实分页追加，右侧地图约占桌面 58%，位置保持可见 |
| 行程详情 | 左侧在对话/行程之间切换，按天查看时间线；右侧大地图单独占列；天气、花费与来源可查 |

布局示意：

```text
首页                  推荐                     详情
品牌 / 导航           品牌 / 导航              品牌 / 导航
标语 + 角色           城市 / 条件 / 筛选       标题 / 日期 / 导出
旅行需求输入          推荐卡片 | 地点地图      按天时间线 | 路线图
偏好 / 操作           推荐卡片 | 地点列表      当日花费   | 来源说明
目的地灵感            加入行程                 调整行程输入
```

真实运行界面（本地截图，非概念稿）：

- [首页](assets/ui/home.png)
- [候选方案比较](assets/ui/recommendations.png)
- [行程详情](assets/ui/itinerary.png)

以上均为本地运行截图；行程内容可能使用合成资料，仅用于说明布局与交互，不代表真实出行数据。
源码中的正式 Logo、可操作组件与真实服务状态为实现依据。

实现入口：[HomeDiscovery.tsx](../frontend/src/HomeDiscovery.tsx)、[Discovery.tsx](../frontend/src/Discovery.tsx)、
[HotelSelector.tsx](../frontend/src/HotelSelector.tsx)、[travel-workspace.css](../frontend/src/travel-workspace.css)。
探索分页使用 `useInfiniteQuery` 与滚动哨兵；手动加载按钮作为键盘操作与自动加载不可用时的入口。
失败保留已有卡片并停止自动重试，换筛选条件后使用新的查询，地图在追加时保留用户视角。
住宿选择采用同样的分页模式，选择仍校验服务端候选与行程版本。
[本轮验证范围](assets/demo/core-ui-checks.json)与[真实探索截图](assets/ui/explore-live.png)随项目提供。

## README 组织依据

README 采用品牌标题、状态徽章、简短介绍与清晰上手路径的组织方式，
技术说明按主题分层并链接到 `docs/`。文案、架构与功能声明均按本仓库内容重写。

首页顶部放短介绍与实际流程 GIF；长篇技术说明链接到 `docs/`。
概念稿、运行截图和真实检索结果分开展示；徽章取自项目版本声明或锁定文件。
许可证徽章取自根目录 `LICENSE`，与维护者选定的授权条款保持一致，不代替维护者选择。

## Demo reproduction

```bash
# 应用与容器已启动，frontend npm 依赖和 Chrome 已安装。
node scripts/export_brand_assets.mjs
node scripts/capture_brand_demo.mjs

# 从真实浏览器录制生成适合 GitHub 首屏的 GIF。
ffmpeg -y -ss 0.7 -i docs/assets/demo/tripal-demo.webm \
  -filter_complex "fps=6,scale=860:-1:flags=lanczos,split[a][b];[a]palettegen=max_colors=96[p];[b][p]paletteuse=dither=bayer" \
  -loop 0 docs/assets/demo/tripal-demo.gif
```

脚本的地址、超时、画布尺寸、输出目录和示例文本均可直接在顶部 `CONFIG` 修改。
录制创建独立本地 QA 账户，行程明确选择合成资料；自编示例 Markdown 的上传、索引与检索真实执行。
不会修改已有账户、行程或本地密钥。录制不包含注册密码界面。

验证范围见 [verification.json](assets/demo/verification.json)：桌面与移动端宽度、横向溢出、
组件计算圆角、JavaScript 页面异常与减少动态效果偏好。截图保留实际服务提示。
