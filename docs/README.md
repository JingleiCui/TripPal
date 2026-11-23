# 项目文档导航

当前代码按职责组织：

```text
TripPal/
├── run_project.py / stop_project.py  # 日常启动和停止
├── backend/travel_agent/
│   ├── api.py / *_api.py             # 接口、账号及业务入口
│   ├── agent/                       # 有界编排、结构化生成和执行约束
│   ├── models/                      # 模型注册、路由、网关与本地语音
│   ├── providers/                   # 地图、美团、预订与显式合成资料
│   ├── parsers/ / mcp/              # 附件解析与受控工具接口
│   └── db.py / worker.py / ...       # 持久化、任务和领域服务
├── backend/tests/unit/              # 快速单元回归
├── backend/tests/integration/       # 服务和 API 集成回归
├── frontend/src/                    # React 页面和组件
├── frontend/e2e/                    # 浏览器流程
├── scripts/setup_local.py           # 本地一键准备与验收
├── scripts/local/                   # 权重与模型检查
├── scripts/validation/              # 真实模型和工程验收
├── migrations/ / eval/              # 数据迁移与回归用例
└── docs/                            # 使用、架构、运维与证据
```

常用文档：

- [小红书攻略导入与图片过滤](小红书攻略导入.md)

- [本地一键准备与验收](本地模型一键准备与验收.md)
- [模型接入与热切换](模型接入审计与热切换.md)
- [模型配置参考](模型网关与Provider切换.md)
- [平台配置](平台申请与配置.md)
- [功能与工程验证](功能与工程验证.md)
- [架构图与可编辑源码](architecture/README.md)
- [部署与运维](部署与运维.md)
- [脚本索引](../scripts/README.md)
- [测试分层与隔离说明](../backend/tests/README.md)

`data/`、`reports/`、本机配置和权重缓存属于运行数据，默认不提交。保留当前验收报告、私密配置备份及业务文件；不将它们当成“过时源码”清除。架构图、品牌素材与演示资产仍被 README 引用，因此保留生成源码及发布资产。

性能与可选升级：[本地与云端分工建议](本地与云端分工建议.md)。建议依据本机实际耗时和官方能力说明，当前未启用云端推理。
