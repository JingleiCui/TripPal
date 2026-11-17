# 本地 Qwen3.5-9B

旅行项目使用本机 Ollama 的 OpenAI 兼容接口，不调用 OpenAI 云端，不需要购买 API Key。

## 自动升级（无需持续调用 Codex）

直接在 PyCharm 运行 `scripts/upgrade_qwen35.py`，或者在项目根目录执行：

```bash
.venv/bin/python -u scripts/upgrade_qwen35.py
```

脚本会接着已有分块下载并校验官方文件，保存 8K 参数、备份并更新两个项目的配置、验证问答/结构化/工具/流式调用、记录规划冒烟结果、重启 API 和 worker，最后删除三个旧 Qwen 模型。下载失败自动重试；关键验证失败会保留旧模型并恢复本轮配置备份。规划质量失败单独记录，不伪装为成功。

后台运行的日志为 `data/upgrade-qwen35/upgrade.log`，状态为 `data/upgrade-qwen35/status.json`。`stage=completed` 才表示流程完成，`failed` 表示停止并保留错误类型。下载进度写在日志中。脚本使用文件锁，重复启动不会产生两个升级进程。关闭电脑或终止脚本后，重新运行同一文件即可继续下载。

## 模型和上下文

```bash
ollama pull qwen3.5:9b
ollama create qwen3.5:9b -f scripts/models/qwen3.5-9b.Modelfile
```

第二条命令在本机同名模型上保存 `num_ctx=8192`，不会重新训练或复制权重。重新从仓库 pull 同名标签后，需要重新执行它。OpenAI 兼容接口不支持直接设置上下文大小，因此在 Ollama 模型参数层设置；使用 `ollama show qwen3.5:9b --parameters` 检查。

## 项目配置

`config.ollama.example.json` 给出模型字段示例。将这些字段合并进 `config.local.json`，保留原高德、美团等配置。`model_api_key` 的 `ollama` 是本地占位值，不是真实云端密钥。Gemini 的原配置备份位于忽略提交的 `data/private-backups/`，请勿分享其中的密钥。

`model_reasoning_effort="none"` 初始关闭思考，以减少等待，并避免思考耗尽 1600 token 输出预算。这不是模型能力的最高分配置；需要比较思考模式时，可按模型支持情况调整，随后重新验证输出、超时和工具行为。`model_timeout=120` 表示单次模型请求超时。

改完配置后先运行 `stop_project.py`，再运行 `run_project.py`，后端与 worker 都会重新读取配置。重复运行启动入口不会热更新已运行的服务。

## 检查

在项目根目录执行：

```bash
.venv/bin/python scripts/check_local_model.py
.venv/bin/python scripts/stream_smoke.py
.venv/bin/python scripts/evaluate.py --mode local-model-smoke
```

第一项只允许调用指定的本机模型，检查问答、JSON Schema、函数形式结构化输出、工具调用与工具结果回传，以及实际运行的 8K 上下文。报告为 `reports/qwen35-readiness.json`。

后两项使用独立评测数据库。流式报告只验证真实分块和持久化；规划冒烟使用合成平台数据和真实模型，保留失败或人工取舍状态，不代表完整真实旅行验收。它们的本地模型默认值已更新到 Qwen3.5-9B。

medicalProject 的 `llm_config.py` 使用 `ollama_qwen35_9b` 配置名，原生 Ollama 调用每次显式传入 `num_ctx=8192`。这两个项目共享同一个 Ollama 模型。
