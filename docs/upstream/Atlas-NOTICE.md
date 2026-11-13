# Atlas 源码复用与改造记录

上游：[dejan3dejan/langgraph-travel-agent](https://github.com/dejan3dejan/langgraph-travel-agent)，项目名 Atlas。

固定提交：`efebcd9371b2b66ed538f2e57d0b8fb17d388a15`。许可证：MIT，Copyright 2026 Dejan Žegarac；完整许可随项目保留于 `Atlas-LICENSE`。参考仓库在本机 `.reference/Atlas`，不参与应用启动。以下仅说明确实复用的源码，不代表完整上游在本机通过验收。

## 实际源码复用

| 上游 | 本项目 | 使用方式 |
|---|---|---|
| `core/nodes/interviewer.py` | `backend/travel_agent/vendor/atlas/interview.py` | 提取槽位合并、空值判断、确定性提问门控等纯函数；保留 False 与未知的区别，额外适配中文出发地跳过条件 |
| `api/authz.py` | `backend/travel_agent/vendor/atlas/authz.py` | 使用 owner/editor/viewer 的权限判定函数，成员信息由本项目 MySQL 提供 |
| `core/orchestrator.py` | `backend/travel_agent/vendor/atlas/variants.py` | 复用是否开启对比和事件标记的纯函数；本项目另行实现研究复用、候选校验及选择事务 |
| `core/signals.py` | `backend/travel_agent/vendor/atlas/signals.py` | 保留有界词汇、信任权重、时间衰减和画像渲染算法；中文行为映射由 `personalization.py` 实现 |

## 重新实现和适配

- 中文对话提取、FastAPI 会话接口、MySQL 记录与迁移、持久 SSE 事件均为当前项目的适配实现。
- 保留中国地图路线与 GCJ-02 坐标，使用高德，不引入上游 Leaflet／海外地图数据。
- ES＋BGE 取代上游 pgvector／OpenAI Embedding。仅复用研究缓存设计，缓存权限、硬条件、有效期及失败降级另行实现。
- 邮箱流程、JWT、会话撤销、文件导出、删除补偿队列、成员校验、乐观锁、Celery 租约接入现有工程，不复制上游整套数据库。
- React 页面独立适配现有工作台，保留中文信息架构和移动端对话／画布切换。
- 不复用上游账号、密钥、生产数据或部署配置，不将上游能力写为独立研发成果。

本项目各文件顶部保留来源标识；再次分发这些文件时应同时分发本记录和原 MIT 许可证。
