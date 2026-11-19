# TripPal 项目长期约定

## 界面视觉偏好（用户明确）
- 整体走 **Tripal 品牌奶油可爱风**：奶油底 + 珊瑚 + 薄荷 + 奶油黄，与全站一致。
- **卡片不要过度圆润**：中等圆角、克制，不要胶囊/大圆角满屏；层级清晰优先。
- 选中态用**淡珊瑚**，不要深珊瑚、不要黑色；背景存在感要弱，不要抢眼。
- 允许并鼓励**适度的动态、光影、立体等高级结构**（柔和过渡/悬停/层次阴影），但动画要自然克制，不花哨。
- 文案与视觉需全文保持一致。
- 一切视觉改动**保持原有功能与 DOM 结构不变**（优先只改 CSS）。
- 用户默认中文回复。

## README / 素材发布口径
- README 中**只允许出现真实运行界面截图**；AI 生成的概念图（`*-concept.png`）是假图，必须删除、不得出现在 README。
- 品牌 Banner（`tripal-banner.png`）是设计稿，不是界面图，不应作为 README 首图。
- demo.gif 要求清晰（旧版 860×597 模糊），更新时用高分辨率录制 + ffmpeg 导出。

## PyCharm 环境约定
- 真实项目路径始终是 `TripPal`；`travel_agent` 只是历史遗留软链，仅用于兼容旧 IDE 工作区，不再写入任何新配置。
- PyCharm 2026.1 全局 SDK 名称固定为 `Python 3.11 (TripPal)`，homePath 为
  `$USER_HOME$/PycharmProjects/TripPal/.venv/bin/python`；`.idea/tripal.iml` 的 `jdkName` 与
  `.idea/misc.xml` 的 Black `sdkName` 必须与之一致，否则 run configuration 会报找不到解释器。
- 修改全局 SDK 配置前必须先完全退出 PyCharm（Cmd+Q），否则运行中的 IDE 会用内存状态覆盖文件。
