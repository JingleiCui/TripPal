# travel_agent

中国旅行规划与行程协同助手。Python／LangGraph 后端，React 地图工作台，MySQL 持久化，Redis／Celery 异步执行，Elasticsearch 私人资料检索。

## 在 PyCharm 运行

1. Open 此项目目录。解释器选择本项目 `.venv/bin/python`（Python 3.11）。不要选系统默认 Python 3.15。
2. 启动 Docker Desktop。
3. Run 根目录 `run_project.py`，打开 http://127.0.0.1:8808/ ，注册自己的本机账户。
4. 真实规划需按 [平台申请手册](docs/平台申请与配置.md) 填写 `config.local.json` 并重启。没有密钥时可以勾选“合成流程体验”学习界面和工程流程；它没有调用模型或真实平台，不能据此出游。

首次迁移到另一台电脑：用 Python 3.11 运行 `scripts/bootstrap.py`，再运行启动脚本。依赖已锁定。常用默认配置在 `backend/travel_agent/config.py`；本机私密文件覆盖默认，`TRAVEL_` 环境变量可选覆盖。

正常停止在 PyCharm 点 Stop 或 Ctrl+C，也可以运行 `stop_project.py`；它核对本项目进程身份后只停止启动器及其 API／worker。数据库容器保留数据。改完密钥要先停止再启动；重复运行已有实例不会自动加载新配置或杀掉其他进程。

已按你的选择增加 Google 官方 Gemini 原生支持。填写方式见 `config.gemini.example.json`；当前本机配置已切换 Gemini，密钥留空等待你自行填写，不需要申请百炼。

## 真实实现

- 注册、密码哈希、持久会话、CSRF、按用户隔离的行程和资料。
- 主 Agent 选择调查职责，领域 Agent 通过 LangChain Tool Calling 获取事实，LangGraph 保存中断与检查点。
- 工具预算、超时、只读重试、结构化返回、任务租约、过期接管、SQL 回执与行程乐观锁。
- 高德地点／路线／天气适配，官方美团 CLI 适配。缺少配置不自动切换成伪造旅行数据。
- 地点列表、每日安排、路线、来源、锁定、修改、版本恢复、PDF／Markdown 导出、只读分享与撤销。
- TXT／MD／文字 PDF／DOCX 解析，BGE 512 维向量、ES 全文／向量检索和 RRF；用户／有效版本在召回前过滤。
- 来源不足时保留未知费用、开放预约、内部步行及接驳缺口；当前时间约束检查不是全局最优路径求解器。

## 尚需真实凭证完成的验收

真实地图渲染、高德查询、云端模型规划、美团价格及外部链接需要你的账号。配置存在和夹具通过均不能证明这些服务已联调。语音、图片 OCR、实时预约库存和支付不在已验收能力中。具体结果查看 `docs/验收结果.md`，不把未运行的项目写成通过。

## 项目结构

```
backend/travel_agent/  API、业务数据、工具、LangGraph、worker、知识检索
frontend/             React 工作台及浏览器验收
migrations/           Alembic 数据库迁移
scripts/              首次安装、评测和运维工具
eval/                 标注案例和评测说明
docs/                 设计、申请、运行、讲解与证据
data/                 私人上传文件（不入 Git）
```

默认端口：API 8808，前端开发 8809，MySQL 13316，Redis 16389，ES 19220。API 文档：http://127.0.0.1:8808/docs 。容器使用专用卷，不共享其他项目的数据。

## 检查命令

```sh
.venv/bin/python -m pytest -q
.venv/bin/ruff check backend migrations
npm run build --prefix frontend
npm run test:e2e --prefix frontend
```

测试前创建独立 `travel_agent_test` 数据库并授权本机开发账号；测试配置使用 Redis 10／11、独立 ES 索引，不重置业务库。浏览器测试使用已安装的 Chrome。`reports/` 保存原始报告和截图，不入 Git。

## 开源边界

JourneyPilot 固定参考提交 `0c9ca78960b754c7c65631726449c11b18cbd725`；复用及验证说明见 `docs/upstream/NOTICE.md`。本项目不是 JourneyPilot 整仓改名，MySQL、ES、业务版本、权限和任务执行为本项目实现。MySQL 检查点使用社区库，非 LangGraph 官方内置 MySQL 支持。


## Atlas 功能融合（2026-11-13）

新增对话规划、确定性提问门控、A/B 候选选择、成员协作、邮件验证与密码重置、JWT 与登录撤销、偏好画像、隐私导出与注销、ES 语义研究缓存、多城市画布和酒店标记。使用方式及验证边界见 [Atlas融合与使用](docs/Atlas融合与使用.md)；实际复用代码和 MIT 归属见 [Atlas-NOTICE](docs/upstream/Atlas-NOTICE.md)。

本机邮件收件箱：http://127.0.0.1:18026/ 。仅本地投递，不发送给真实邮箱。

配置状态与调用成功不同：当前高德地点／天气和美团查询已通过连通检查；Google Gemini 返回当前地区不支持 API 的错误，需要解决平台可用性后验证完整真实模型链路。页面仍可使用标注清楚的合成流程；不会偷偷以合成结果替代真实查询。

模型切换及本轮 schema 错误修复说明：[模型切换与结构化输出修复](docs/模型切换与结构化输出修复.md)。编辑 `config.local.json` 的 `active_model_profile` 即可切换，修改后重启 API 和 worker。
