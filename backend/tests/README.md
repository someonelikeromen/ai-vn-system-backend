# 测试目录说明

## 测试模块一览

| 文件 | 覆盖范围 |
|------|----------|
| `test_01_db.py` | 数据库层 · Schema 完整性 · CRUD · 乐观锁 |
| `test_02_utils.py` | 工具函数 · tag_parser · 纯度检查 · var_engine |
| `test_03_agents.py` | Agent 单元测试 · state · DM · Chronicler |
| `test_04_api.py` | API 端点 · /novels · /protagonist · /config |
| `test_05_exchange.py` | 兑换系统 · 定价评估 · 购买流程 |
| `test_06_agents_advanced.py` | Agent 高级 · NPC 漂移检测 · Planner 字数规划 |
| `test_07_api_integration.py` | 全栈集成 · SSE 回合 · 回滚快照 |
| `test_08_growth.py` | 成长系统 · XP 结算 · CAS 并发 |
| `test_09_schema_contract.py` | Schema 契约 · TypedDict 字段 · API 响应格式 |

## 运行方式

### 命令行
```bash
# 全部
python run_tests.py

# 快速（跳过集成）
python run_tests.py --fast

# 单模块
python run_tests.py --module 01

# 详细输出
python run_tests.py --verbose
```

### 前端控制台
启动开发服务器后访问：
```
http://localhost:5173/test.html
```

## Fixtures（conftest.py）

| Fixture | 作用 |
|---------|------|
| `fresh_db` | 每个测试用独立临时 SQLite |
| `db` | Session 级共享数据库 |
| `mock_llm` | Mock LLM 客户端 |
| `app_client` | 完整 FastAPI 异步客户端 |
| `sync_client` | 同步 TestClient |

## 测试标记

```python
@pytest.mark.slow    # 耗时测试，fast 模式跳过
@pytest.mark.asyncio # 异步测试（自动应用，asyncio_mode=auto）
```
