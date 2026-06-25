# Agent 模块技术债记录

> 当前 Phase 5~6（v1.0）**不做** Agent 模块。
> 以下记录保持原文档，供 Phase 7+ 实现时使用。

## 架构原则（已批准 ADR-002）

见 `docs/决策记录/adr-002-agent-architecture.md`

## v1.0 中需注意的预留设计

### 1. API 路由前缀

前端请求后端时，统一走 `GET /api/*`。
Agent 模块未来可以挂 `POST /api/agent/query`，与现有端点不冲突。

当前状态：✅ 已满足，无需修改

### 2. 工具层接口稳定

现有 QueryEngine 的方法是 Agent 工具的候选包装目标：

| 方法 | 用途 | 稳定性 |
|------|------|--------|
| `kb.get_character(name)` | 查角色信息 | ✅ 稳定 |
| `kb.list_relations(char_a, char_b)` | 查关系 | ✅ 稳定 |
| `kb.list_timeline()` | 查时间线 | ✅ 稳定 |
| `kb.list_foreshadowings()` | 查伏笔 | ✅ 稳定 |
| `kb.list_chapters()` | 查章节列表 | ✅ 稳定 |
| `query_engine._extract_entities()` | 实体提取 | ✅ 已增强 |
| `query_engine._classify_intent()` | 意图分类 | ✅ 已增强 |

不需要在 v1.0 做任何包装，Phase 7 时直接加 `agent/tools.py`。

### 3. 向量数据库同步点

SQLite → Chroma 同步需要这些数据：

| 表 | 同步时机 | 建议 |
|------|---------|------|
| characters | 每次解析后 | Phase 7 在 parser 完成回调处加 |
| relations | 每次解析后 | 同上 |
| timeline_events | 每次解析后 | 同上 |
| chapters.raw_text | 每次解析后 | 需要分块策略 |

v1.0 不需要做任何同步，Phase 7 时在 `core/parser.py` 的解析完成点加回调即可。

### 4. 配置预留

`config.py` 需要新增字段（Phase 7 时加）：

```python
# Agent 配置
agent_enabled: bool = False
agent_provider: str = "deepseek"       # Agent LLM 使用哪个模型
embedding_model: str = "BAAI/bge-small-zh-v1.5"
vector_db_path: str = "agent_data/vector_db"
```

v1.0 不需要加这些配置，不影响现有功能。
