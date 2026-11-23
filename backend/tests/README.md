# 测试组织

- `unit/`：141 项快速测试，使用纯业务逻辑、SDK/HTTP 替身和临时文件；无需运行真实模型或数据库服务。
- `integration/`：52 项 API、MySQL、Redis、Elasticsearch/BGE 集成检查，使用独立测试数据库和 Redis DB。
- `conftest.py`：集中隔离配置与账号/客户端 fixture；不继承用户当前启用的模型 profile。
- `frontend/e2e/`：浏览器测试，常规 13 项；另外 2 项专用 live 验收需要显式开关和准备数据。
- 真实模型验收在 `scripts/validation/`，不会混入普通单元测试或每次修改后反复推理。

```bash
.venv/bin/python -m pytest backend/tests/unit -q
.venv/bin/python -m pytest backend/tests/integration -q
.venv/bin/python -m pytest -q
```

本次合并了原 `test_constraints.py`、`test_model_configuration.py`、`test_place_photos.py`、`test_discovery_mcp_food.py` 和 `test_multi_and_cache.py`：独有断言分别进入规划、模型网关、发现和检索测试。没有因文件年代或名称相似而删除有效行为覆盖。整理前后均为 193 项用例。

测试库为 `travel_agent_test`，评测库为 `travel_agent_eval`，Redis DB 10/11 为专用测试库。测试会修改这些测试资源，请勿将其他业务数据放入其中。
