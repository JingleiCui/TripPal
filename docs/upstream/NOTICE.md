# 来源与贡献边界

## JourneyPilot

- 仓库：https://github.com/Lagom-TA/JourneyPilot
- 固定提交：`0c9ca78960b754c7c65631726449c11b18cbd725`
- 许可证：MIT，完整保留于本目录 JourneyPilot-LICENSE。
- 检查内容：README、依赖、路线适配、行程修改和前端工作台结构。
- 实际复用：Amap 交通方式到官方端点的映射参考；来源快照、约束检查与工作台分区作为设计参考。没有整仓改名、没有引入其 PostgreSQL／pgvector 数据层。
- 验证：固定提交前端 `npm ci` 与 `npm run build` 通过；日志保存在 reports/upstream-build.log。未声称其全部后端测试在本项目环境通过。本项目独立接口和业务测试单独记录。

## 其他依赖

- LangGraph／LangChain 提供图运行时与工具／模型抽象，不能把框架底层能力描述为本人研发。
- `langgraph-checkpoint-mysql==3.0.0` 是社区 MySQL 实现；已用本地 MySQL 8.4 验证中断恢复、重放与新实例加载。
- 前端按钮采用 CVA＋Radix Slot 的组合方式，参考 shadcn/ui（MIT）的组件习惯；页面和业务交互为本项目实现。
- 美团采用官方 npm 包 `@meituan-travel/travel-cli@1.0.16`。只通过固定可执行文件调用，不执行模型提供的 Shell。
- Obytes 仅作为视觉／工程组织参考，没有引入 Expo／React Native 项目。

## 镜像

Docker Hub 直接拉取 Redis 时遇到 TLS 连接中断，通过镜像源取得同一镜像，并向 Docker 官方 Registry 校验了 manifest digest：`sha256:7f7d30b7fdd09467bac58198a1f166dd69789d348d4fe859cccb20e0cf287fbe`。校验后标记为本机 `redis:7.4-alpine`，未关闭 TLS 校验，未修改全局 Docker 镜像源。

本地 `.reference` 为只读参考与构建验证目录，不参与运行和发布；源码提交中通过来源文件而非嵌套 Git 仓库保存边界。
