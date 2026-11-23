# 模型网关与 Provider 切换

本文说明项目里**哪些能力需要模型 API**、**配置怎么填**、**如何一键切换供应商（含 OpenRouter 免费模型）**，以及本轮为提升代码效率与复用性做的结构改造。

> 状态口径：`needs_key` / `ready` 只表示**配置齐备**，不代表已与真实服务联调成功。真实调用结果以 `scripts/check_providers.py --probe` 的输出为准。

---

## 一、项目需要配置的模型 API 接口（7 个能力槽位）

| 槽位 `slot` | 用途 | 默认供应商 / 模型 | 协议 | 需要 Key | 代码入口 |
|---|---|---|---|---|---|
| `chat` | 对话、主 Agent 分派、领域 Agent tool calling、narrate 流式答复 | 跟随 `model_provider` | LangChain（OpenAI-compatible / Ollama / Gemini SDK） | 是（本地 Ollama 除外） | `agent/harness.py::model()` |
| `structured` | `with_structured_output` 输出 `SlotUpdate` / `DelegateSelection` / `PlanSelection` | 同 `chat` | 同上 | 同 `chat` | `agent/structured.py::generate()` |
| `vision` | 旅行截图 → 结构化候选事实 | `dashscope` / `qwen-vl-max-latest` | OpenAI-compatible `/chat/completions` + `image_url` | 独立 `vision_api_key` | `vision.py::recognize()` |
| `asr` | 语音转写 | `dashscope_native` / `qwen3-asr-flash` | 百炼 `/compatible-mode/v1/chat/completions` + `input_audio` | 独立 `voice_api_key` | `voice.py::transcribe()` |
| `tts` | 文本朗读 | `dashscope_native` / `qwen3-tts-flash` | 百炼**原生** `multimodal-generation/generation` + 音频 URL 下载 | 同 `asr` | `voice.py::synthesize()` |
| `embedding` | 私有资料 RAG 向量化 | 本地 `BAAI/bge-small-zh-v1.5`（512 维） | 进程内 `sentence-transformers` | **否** | `knowledge.py::embed()` |
| `rerank` | 检索结果重排（默认关闭） | 本地 `BAAI/bge-reranker-base` | 进程内 `CrossEncoder` | **否** | `knowledge.py::rerank()` |

**关键点**：`structured` 默认跟随主模型，也可独立配置供应商与凭证；`vision` / 语音各自独立，避免把对话 Key 发到未授权域名；`embedding` / `rerank` 完全本地，不消耗任何 API 额度。

---

## 二、三层架构

```
config.local.json / TRAVEL_* 环境变量
        ↓
  models/specs.py     ProviderSpec：供应商静态连接信息（纯数据，不依赖 config）
        ↓
  models/registry.py  resolve(slot) → ResolvedSpec：按槽位合成最终 provider/key/model/协议
        ↓
  models/gateway.py   chat_model() 缓存 + client_for() 连接池 + post_chat/post_json 统一出口
        ↓
  agent/harness.py · agent/structured.py · vision.py · voice.py · api.py(/health, /models)
```

| 新增文件 | 职责 |
|---|---|
| `backend/travel_agent/models/specs.py` | 内置供应商预设（含本地语音）、自定义 Provider 构造与校验 |
| `backend/travel_agent/models/registry.py` | 槽位解析、凭证隔离、结构化方式决策、`status()` 脱敏视图 |
| `backend/travel_agent/models/gateway.py` | 实例/连接池缓存、统一鉴权、URL 拼接、响应解析、HTTP 错误映射 |
| `scripts/check_providers.py` | 配置自检 + 真实最小调用探测 + profile 批量检查 |
| `config.openrouter.example.json` | 复制即用的 OpenRouter 配置模板 |
| `backend/tests/unit/test_model_gateway.py` | 19 条离线单测 |

`models/__init__.py` 刻意保持为空，避免 `config.py` 引用 `specs` 时产生导入环。

---

## 三、接口配置项

### 3.1 `Settings` 新增字段（`backend/travel_agent/config.py`）

| 字段 | 类型 | 默认 | 说明 |
|---|---|---|---|
| `model_providers` | `dict[str, dict]` | `{}` | 自定义供应商，或覆盖内置预设的 `base_url` / `default_model` / `extra_headers` |
| `model_slots` | `dict[str, dict]` | `{}` | 按槽位覆盖供应商、模型、凭证、开关 |
| `vision_provider` | `str` | `""` | 视觉槽位供应商；留空跟随对话供应商 |
| `voice_provider` | `str` | `""` | 语音槽位供应商；默认 `dashscope_native` |

**原有字段全部保留且语义不变**：`model_provider` / `model_name` / `model_api_key` / `model_base_url` / `model_enabled` / `model_timeout` / `structured_output_method` / `active_model_profile` / `model_profiles` / `vision_*` / `voice_*`。

### 3.2 `ProviderSpec` 字段（`model_providers.<name>` 可填）

| 字段 | 说明 |
|---|---|
| `protocol` | `openai` / `ollama` / `gemini` / `dashscope_native` / `local` |
| `base_url` | 服务根地址 |
| `default_model` | 该供应商默认模型 |
| `chat_path` | chat 端点路径，默认 `/chat/completions` |
| `key_env` | 可选的凭证环境变量名（最低优先级兜底） |
| `structured_method` | `auto` / `json_schema` / `function_calling` |
| `capabilities` | 支持的槽位集合 |
| `extra_headers` | 附加请求头（OpenRouter 可放 `HTTP-Referer` / `X-Title`） |
| `extra_body` | 附加**请求体**参数，例如 `{"reasoning": {"enabled": false}}` |
| `requires_key` | 是否需要凭证（Ollama / local 为 false） |

### 3.3 `model_slots.<slot>` 可填

`provider` / `model` / `api_key` / `base_url` / `enabled` / `use_main_key` / `extra_headers` / `extra_body` / `structured_method` / `timeout`。
出现未列出的字段会直接抛 `ConfigurationError`，不会静默忽略。

`extra_body` 对两类调用都生效：LangChain 通道注入 `ChatOpenAI(extra_body=...)`，裸 HTTP 通道（vision / asr / tts）合并进 `POST` 的 JSON body；同时参与 `ResolvedSpec.fingerprint`，改参数会自动换实例。

### 3.4 配置优先级（低 → 高）

```
类默认值  <  config.local.json 平铺字段  <  model_profiles[active_model_profile]
        <  model_slots[slot]  <  TRAVEL_* 环境变量  <  ProviderSpec.key_env 环境变量兜底
```

`apply_model_profile()` 在切换 profile 时**先清空**上一个供应商的 `model_api_key` / `gemini_base_url` / `model_reasoning_effort`，凭证不会跨供应商继承。

`model_slots` 可以**写在 profile 里**（`MODEL_PROFILE_FIELDS` 已放行）。这是推荐的按用途分配方式：切到 `openrouter_free` 时用它的三槽位分配，切回本地 `current` 时顶层 `model_slots` 为空，自动还原，不会污染其它 profile。反过来，写在顶层的 `model_slots` 是全局的，会作用到所有 profile。

### 3.5 内置供应商

`openrouter`、`dashscope`、`openai`（泛指 OpenAI-compatible）、`siliconflow`、`deepseek`、`gemini`（官方 SDK）、`ollama`（本地）、`local_speech`（离线 Whisper/macOS 朗读）、`dashscope_native`（ASR/TTS 专用）、`local`（embedding/rerank）。

---

## 四、切换机制（4 种，任选其一）

**① 改一行（推荐）**：编辑 `config.local.json` 的 `active_model_profile`，默认在下次模型入口解析时热加载。首次部署本次代码仍需重启 API 与 worker。详见 [模型接入审计与热切换](模型接入审计与热切换.md)。

**② 环境变量临时切换，不改文件**：

```sh
TRAVEL_ACTIVE_MODEL_PROFILE=openrouter_free .venv/bin/python scripts/check_providers.py --probe
```

**③ 按槽位混搭**：`chat`（对话 + tool calling）、`structured`（JSON 抽取）、`vision`（截图识别）各用不同模型。下面这段写在 `model_profiles.openrouter_free` 内部：

```json
"model_slots": {
  "chat": {
    "provider": "openrouter", "model": "inclusionai/ling-3.2-flash:free",
    "extra_body": {"reasoning": {"enabled": false}}
  },
  "structured": {
    "provider": "openrouter", "model": "inclusionai/ling-3.2-flash:free",
    "use_main_key": true, "structured_method": "json_schema",
    "extra_body": {"reasoning": {"enabled": false}}
  },
  "vision": {
    "provider": "openrouter", "model": "nvidia/nemotron-3.5-super-vl:free",
    "use_main_key": true, "enabled": true,
    "extra_body": {"reasoning": {"enabled": false}}
  }
}
```

`chat` 与 `structured` 的**模型可以不同**（`harness.model("structured")` 走独立实例），但要先用 `--probe` 验证候选模型；`asr` / `tts` 仍可单独指向 `dashscope_native` 并配独立 `api_key`。

上面是**额度充足时的推荐组合**（也是 `config.openrouter.example.json` 的写法）。当前 `config.local.json` 的 `vision` 槽位因 `free-models-per-day` 限流降级为 `inclusionai/ling-3.2-flash:free`，额度恢复后改回 Nemotron 即可。

`use_main_key` 只在**同源**（chat 与 vision 的 base_url 同 host）时才生效；把 OpenRouter 的 Key 发到 `dashscope.aliyuncs.com` 会被显式拒绝。

**④ 新增供应商**：在 `model_providers` 里声明，无需改任何 Python 代码：

```json
"model_providers": {
  "my_gateway": {
    "protocol": "openai", "base_url": "https://llm.internal/v1",
    "default_model": "internal-chat", "structured_method": "json_schema",
    "capabilities": ["chat", "structured", "vision"]
  }
}
```

切换后可用 `GET /api/v1/models` 或自检脚本确认生效；返回体**不含任何凭证明文**。

---

## 五、调用逻辑

**对话 / 结构化（LangChain）**

```
build_graph → harness.invoke / stream_reply
   → chat_ready() 门控（registry.resolve("chat")）
   → harness.model() → gateway.chat_model(drivers={"openai": ChatOpenAI})
        → 按 ResolvedSpec.fingerprint 命中缓存则复用，否则按 protocol 构造 ChatOpenAI/ChatOllama/ChatGoogleGenerativeAI
   → .invoke / .stream / .bind_tools / .with_structured_output
   → 异常经 model_errors.classify 归一为 credentials / quota / model_region / model_not_found
```

**HTTP 槽位（vision / asr / tts）**

```
vision.recognize / voice.transcribe / voice.synthesize
   → registry.resolve(slot)（凭证、base_url、model、chat_path）
   → gateway.post_chat / post_json
        → client_for(spec) 共享连接池
        → 统一 Bearer + extra_headers + URL 拼接 + follow_redirects=False
        → 状态映射（401 凭证 / 429 额度 / 404 模型 / 其它统一 failure_code）
        → chat_content() 统一解析 choices[0].message.content
   → 业务层 normalize_fields / 结构化 envelope（status: ok|unavailable|error|synthetic）
```

**凭证隔离规则**：`chat` 的 Key 只有在目标槽位与 chat **同 host** 且显式 `use_main_key`（或旧版 `voice_key()` 兼容条件）时才复用；不同 host 一律返回空并标 `needs_key`。

---

## 六、代码效率与复用性改造

| 改造前 | 改造后 |
|---|---|
| `harness.model()` 每次新建 `ChatOpenAI`/`ChatOllama`/`ChatGoogleGenerativeAI`，一次任务可建十几个 SDK client | `gateway.chat_model()` 按配置指纹缓存；配置变更 / 驱动替换自动失效 |
| 三处分支重复拼 `api_key=... or "not-configured"`、两套 base_url 归一化 | 集中在 `chat_model()` 一处 |
| `voice.py` / `vision.py` 各建 `httpx.Client`（无连接池复用） | `client_for()` 按 `(base_url, timeout, Client 类)` 共享 keep-alive 连接池 |
| `"Authorization: Bearer " + key`、URL 拼接在 3 处重复 | `gateway._post()` 唯一出口 |
| `choices[0].message.content` 解析与异常包装重复两份 | `gateway.chat_content()` 一份 |
| 凭证可用性判断散落在 `harness` / `graph` / `conversation` / `api` / `voice` / `vision` 6 处，各读 `settings.model_enabled and settings.model_api_key` | 统一 `registry.chat_ready()` / `ready(slot)`；支持本地模型无 Key、环境变量 Key、槽位独立 Key |
| `structured.is_ollama()` 直接解析 URL，与 harness 分支重复 | 统一由 `registry.resolve("chat").protocol` 判定 |
| 新增供应商需改 `harness.model()` 分支 + 白名单 + URL | 只加一条 `ProviderSpec` 或一段 `model_providers` JSON |

另外保留了 `follow_redirects=False`、`trust_env=False` 的 SSRF 与代理纪律；TTS 音频下载仍校验 `.aliyuncs.com` 域名与 10 MB 上限；结构化输出的「1 次有界修正 + 业务 validator」和 POI 必须经 `search_places` 的收口逻辑完全未动。

---

## 七、填入 API Key 并自动测试全流程

### 7.1 最小操作（OpenRouter 免费模型）

1. 打开 `config.local.json`，找到已预置的 `model_profiles.openrouter_free`，把 `model_api_key` 填成你的 `sk-or-v1-...`。
2. 把顶层 `active_model_profile` 从 `current` 改成 `openrouter_free`（或只设环境变量，不改文件）。
3. 首次部署代码后重启 API 与 worker；后续模型配置保存后在各进程下次模型入口解析时热加载。

**不要写 `model_name: "openrouter/free"` 当默认**。`openrouter_free` 只是**本机 profile 的名字**；`openrouter/free` 是 OpenRouter 真实存在的一个「免费模型自动路由器」，但它每次请求可能落到不同模型（本机实测同一轮三次调用分别落到 `particle-1` / `nemotron-3.5-lightning` / `nemotron-3-ultra`），`json_schema` 与 tool calling 的行为不可复现。项目默认已改成具体的 `inclusionai/ling-3.2-flash:free`，完整分配见第 3.3 / 四③ 节与 `config.openrouter.example.json`。

### 7.2 自检命令

```sh
# 只查配置，不联网
.venv/bin/python scripts/check_providers.py --all-profiles

# 切换 + 真实调用 chat / structured / tool calling（会产生少量额度消耗）
TRAVEL_ACTIVE_MODEL_PROFILE=openrouter_free .venv/bin/python scripts/check_providers.py --profile openrouter_free --probe

# 额外探测视觉槽位（需先设置 vision_enabled 与 model_slots.vision.model）
TRAVEL_ACTIVE_MODEL_PROFILE=openrouter_free .venv/bin/python scripts/check_providers.py --probe --probe-vision

# 机器可读输出，便于自动化
.venv/bin/python scripts/check_providers.py --json --probe

# 运行时查看（服务已启动）
curl -s http://127.0.0.1:8808/api/v1/models | python -m json.tool
```

### 7.3 回归测试（不需要 Key，离线）

```sh
.venv/bin/python -m pytest -q --basetemp=/tmp/travel-pytest-gw
.venv/bin/ruff check backend migrations
npm --prefix frontend run build
```

### 7.4 完整真实规划链路（一键）

模型探测通过后，跑一次非 fixture 的真实规划任务（在**独立测试库**执行，不触碰业务数据；需要 `amap_key` 与本地 MySQL / Redis / ES）：

```sh
.venv/bin/python scripts/validation/plan.py
TRAVEL_ACTIVE_MODEL_PROFILE=openrouter_free .venv/bin/python scripts/validation/plan.py
```

脚本会注册临时账户、创建任务、同步执行 worker、自动推进 LangGraph 的 `waiting_input` interrupt（最多 3 轮），并打印最终状态与行程版本。退出码 0 = `completed` 或到达正常的人工确认点；1 = 失败。

本机 2026-11-14 的两次实测：

| 供应商 | 结果 |
|---|---|
| 本地 Ollama（无需 key） | `chat OK` / `structured OK (json_schema)` / `tools OK (1 tool call)` / `smoke_plan completed, version 1, 北京 · 1 日城市行程` |
| OpenRouter 免费模型（已填 key） | `chat OK` / `structured OK (json_schema)` / `tools OK (1 tool call)` / `vision OK (cities=[], unknowns=6)` / `smoke_plan completed, version 1, 北京 · 1 日城市行程`，经过一次 `waiting_input` interrupt + 自动 resume |

视觉槽位最初配 `nvidia/nemotron-3.5-super-vl:free` 时单独探测成功过，后续因账户日额度耗尽返回 429，最终降级为 `inclusionai/ling-3.2-flash:free` 后 `--probe --probe-vision` 四项全绿。

期间 ES 语义缓存索引报过非致命的 400 警告（测试索引既有问题，不影响规划结果）。OpenRouter 免费额度较紧，密集探测会触发 429 / 连接抖动，遇到时隔几分钟重跑即可，不要把一次限流误判为配置错误。

未通过 `--probe` 时不要据此宣称完整规划链路已验收；换供应商或换模型后都要重新跑上述命令。

---

## 八、OpenRouter 免费模型：按用途选型与实测坑

### 8.1 实测过的 `:free` 模型（2026-11-14，以 `/api/v1/models` 实时目录为准）

| 模型 ID | 输入模态 | 适合用途 | 实测结论 |
|---|---|---|---|
| `inclusionai/ling-3.2-flash:free` | text + image，1M ctx | **chat / structured / tool calling** | 三项均通过；关闭 reasoning 后稳定 |
| `nvidia/nemotron-3.5-super-vl:free` | text + image + video，1M ctx | **vision（截图识别）** | 图片输入通过；json_schema 下会耗尽输出预算，不适合作 structured。额度紧张时易先触发日限额 |
| `inclusionai/ling-3.2-flash:free`（兼视觉） | text + image | 视觉降级备选 | 实测图片输入可用；`config.local.json` 当前用它，因为 Nemotron 在本机触发 `free-models-per-day` |
| `baidu/ernie-5.5-flash-preview:free` | text，1M ctx | 中文文本备选 | 短 prompt 的 json_schema 通过，但**强制开启 reasoning**（关闭会被 400 拒绝），长链路出现 `LengthFinishReasonError`，本项目不用 |
| `openrouter/free` | text + image | 对比试验 / 临时兜底 | 真实存在的自动路由器，但三次请求落到三个不同模型，行为不可复现，**不作默认** |
| `google/gemma-4-31b-it:free` | image + text | 视觉备选 | 探测时上游 429，未验证 |

目录里还有 `liquid/lfm-3-1.7b:free`、`particle-ai/particle-1:free`、`dots-studio/dots-3-note-preview:free` 等，可按同样方法用 `--probe` 验证后再换。

### 8.2 最关键的一个坑：reasoning 会吃光输出预算

这些免费模型大多默认开 reasoning。本机实测：不关闭时 Ling 用 88 秒才吐 512 tokens 且 `finish_reason=length`、`content` 为空；完整规划链路报 `LengthFinishReasonError` / `OpenAITimeoutError`。解决办法是在 `model_slots.<slot>.extra_body` 里加：

```json
"extra_body": { "reasoning": { "enabled": false } }
```

注意这是**厂商相关参数，不是通用能力**：Ling 与 Nemotron 接受，ERNIE preview 明确返回 400 "Reasoning is mandatory for this endpoint and cannot be disabled."。所以只给实际选用的槽位配。

### 8.3 其它约束

- Base URL `https://openrouter.ai/api/v1`，OpenAI-compatible；免费模型 ID 一般带 `:free`。额度约 20 RPM / 50~200 RPD（以官网实时说明为准），密集自检容易 429。
- `model_output_tokens` 不要盲目调大：reasoning 模型会给足额度就一直生成，反而拖慢并超时。当前 profile 用 4096。
- **结构化输出与 tool calling 支持因模型而异**：`--probe` 会实测这两项；失败时先用 `extra_body` 关 reasoning，再考虑换 `structured_output_method: "function_calling"` 或换模型。
- `--probe-vision` 的测试图必须是有效尺寸的 PNG；1×1 占位图会被 provider 以 "media could not be screened" 拒绝，造成与模型能力无关的假失败（脚本已修）。
- `free-models-per-day` 是**账户级**日额度：本机在密集自检后耗尽，报错原文为 `Rate limit exceeded: free-models-per-day. Add 10 credits to unlock 1000 free model requests per day`。此时只有部分模型桶仍可用。`config.openrouter.example.json` 给出按用途分配的推荐组合（视觉用 Nemotron），`config.local.json` 则把视觉降级为 Ling 以保证当天可用；额度恢复后把 `model_slots.vision.model` 换回 `nvidia/nemotron-3.5-super-vl:free` 即可。
- 免费模型列表经常变化，`model_name` 请按官网当前列表调整，不要写死当作长期事实。可先跑 `GET https://openrouter.ai/api/v1/models` 拉取实时目录。

---

## 九、诚实边界

- 网关、切换、缓存、测试、自检脚本均已在本机验证；**OpenRouter 已用真实 key 联调**：chat / structured(json_schema) / tool calling / vision 的最小调用通过，非 fixture 完整规划 `completed`。
- 这不等于「所有 `:free` 模型都可用」：它们的 reasoning、json_schema、tool calling 行为差异很大，换模型必须重跑 `--probe` 与 `smoke_plan`。Nemotron 视觉模型在账户日额度耗尽后返回 429（`free-models-per-day`），属额度限制而非功能缺陷，已降级到 Ling 并复测通过。
- `configured_not_verified` / `ready` 只表示配置齐备，不是调用成功证据。
- 本地 Ollama（`current`）仍是当前默认 profile；填入的 OpenRouter key 只影响 `openrouter_free`，切换 profile 不会自动迁移 `amap_key` 等无关配置。
- `embedding` / `rerank` 仍是本地模型，不受本网关的供应商切换影响；`asr` / `tts` 仍需百炼凭证，OpenRouter 免费模型不提供这两项。


本地完整配置与语音补齐见 [本地模型一键准备与验收](本地模型一键准备与验收.md)。
