# 脚本入口

日常启动使用根目录 `run_project.py` / `stop_project.py`。首次准备和完整验收使用 `scripts/setup_local.py`；常用参数在脚本顶部修改，可直接在 IDE 运行。

| 位置 | 用途 |
|---|---|
| `setup_local.py` | 本地模型、服务、配置与完整验收的统一入口 |
| `bootstrap.py` | 安装项目独立 Python/Node 环境 |
| `check_providers.py` | 模型配置检查；真实探测需要显式 `--probe` |
| `local/check_model.py` | 真实本地对话、JSON Schema、工具调用及上下文检查 |
| `local/download_qwen.py` | 官方 Qwen 权重下载、续传和 SHA256 校验 |
| `validation/notes.py` | 攻略导入、本地转写、纯图/水印跳过及独立后台队列验收 |
| `validation/local_channels.py` | 实际 BGE、重排、离线语音和截图验证 |
| `validation/evaluate.py` | 60 例工程回归；另有真实本地模型三策略冒烟模式 |
| `validation/plan.py` | 真实旅行数据规划，必须 completed 才通过 |
| `validation/scenarios.py` | 单城、多城、锁定地点修改；检查天数、城市和锁定项 |
| `validation/stream.py` | 真实本地模型流式分块与持久化 |
| `validation/platforms.py` / `benchmark.py` | 可选平台连通与 API 基线 |
| `models/` | Ollama 参数模板 |
| `backup.py` / `server.py` | 备份与服务器容器入口 |
| 绘图、导出和演示脚本 | 文档资产的可维护源码，继续保留；详见 `docs/architecture/README.md` |

已移除旧的 `upgrade_qwen35.py`：它同时修改另一个项目并删除旧模型，已被只操作本项目的 setup 流程替代。原散落在脚本根目录的模型/验收辅助脚本已迁移到上述目录，项目内引用同步更新。
