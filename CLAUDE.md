# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Build / Test / Run Commands

```bash
# 安装依赖
pip install -r novel-ai-assist/requirements.txt

# 运行全量测试
cd novel-ai-assist && python -m pytest -v --tb=short

# 运行单个测试文件
python -m pytest tests/test_config.py -v

# 运行单个测试用例
python -m pytest tests/test_api.py::TestStatusEndpoint::test_status_returns_ok -v

# 运行集成测试（需要 DEEPSEEK_API_KEY）
DEEPSEEK_API_KEY=sk-xxx python -m pytest tests/test_integration_parser.py -v

# 运行覆盖率
python -m pytest --cov=core --cov=watcher --cov=config --cov=main --cov=api

# 启动开发服务器
cd novel-ai-assist && uvicorn main:create_app --reload --port 8000

# 启动需要先用 proxy_on（访问 GitHub/DeepSeek 等外网）
# proxy_off（国内镜像/本地服务）
```

## Project Phases & Status

| Phase | 内容 | 状态 |
|-------|------|------|
| **1** | 项目骨架 + SQLite + config + 扫描模块 | ✅ 完成 |
| **2** | LLM 章节解析 → Pydantic 校验 → 数据库写入 | ✅ 完成 |
| **3** | REST API + 对话查询（三层查询引擎） | 🔄 Step 5 WebSocket 待做 |
| 4 | 矛盾检测 + WebSocket 推送 | ⏳ |
| 5 | Vue 前端悬浮窗 | ⏳ |

当前重点：Phase 3 Step 3（分页/排序增强）+ Step 5（WebSocket）

## Architecture Overview

```
用户保存 .md 文件
       ↓
[watcher/monitor.py] 扫描 chapters/ 目录 → status = 'pending'
       ↓
[POST /api/reparse/{num}] 手动触发解析
       ↓
[core/parser.py] → LLM 结构化提取 → Pydantic 校验 → 重试 1 次
       ↓
[core/knowledge.py] 事务写入 6 张表（chapters/characters/relations/timeline/foreshadowings/llm_parse_logs）
       ↓
[core/query.py] 对话查询：小模型拆句 → SQL 路由 → DeepSeek 兜底
       ↓
[api/routes.py] 9 个 REST 端点 + ok()/err() 统一信封
```

### Layer boundaries
- **api/**: HTTP 契约（schemas/routes/responses/deps），不写业务逻辑
- **core/**: 纯业务逻辑（models/models.py LLM 校验 / knowledge.py 数据访问 / parser.py 解析调度 / query.py 查询引擎）
- **watcher/**: 文件系统交互，只做扫描和状态标记
- **config.py**: Pydantic Settings + JSON 持久化

## Database Schema (6 tables)

- **chapters** — 章节索引、解析状态、文件哈希、raw_text
- **characters** — 人物名、别名、4 键位 status 快照、status_history 变更记录
- **relations** — char_a/char_b/relation 三元组，unique 约束
- **timeline_events** — 故事时间线，含 narrative_order / evidence / is_anomaly
- **foreshadowings** — 伏笔，status 分 unrecovered/recovered
- **llm_parse_logs** — LLM 调用日志（debug 用）

## Key Conventions

### LLM Integration
- **DeepSeek**（主模型 `deepseek-chat`），**qwen2.5:7b**（拆句模型，本地 Ollama）
- 所有 LLM 调用走 `openai` 兼容 SDK，由 `config.py` 控制 api_base/api_key/model
- Parser 重试 1 次 + 四层 JSON 兜底（直接解析 → 代码块提取 → Pydantic 校验）
- Query 引擎三级降级（qwen → 规则 → DeepSeek 强制拆句）

### Status Key
角色状态固定 4 键位：`physical / emotional / social / location`
不允许 LLM 自由发挥键名，确保跨章数据可比对。

### Write Strategy
全量覆盖写入：删除该章旧数据 → 插入新数据（非增量更新）
原理：以章为锚点，正文 `.md` 是唯一事实来源。

### Evidence
所有提取项（角色/关系/事件/伏笔）必须含 `evidence` 字段引用原文，供 Phase 4 矛盾检测溯源。

### API Response Format
```json
{"ok": true, "data": ..., "error": null}   // 成功
{"ok": false, "data": null, "error": "..."} // 失败
```
所有端点通过 `api/responses.py` 的 `ok()/err()` 返回。

## P0 Tech Debt (GPT Review)
1. qwen2.5:7b 同时做拆句+实体+意图+指代，职责过载（已加规则降级 + 质量检查但未完全解决）
2. 缺 episodic entity memory（"黑衣人"类描述性实体无法解析）
3. 意图类型不足：缺 event/organization/recent/causality
4. 答案合并缺冲突检测：SQL 与 LLM 答案矛盾时不报错

## Common Tasks

```bash
# 新配置（首次运行自动创建）
# 配置文件：agent_data/config.json

# FastAPI 自动文档
open http://localhost:8000/docs

# 健康检查
curl http://localhost:8000/api/status

# 对话查询
curl -X POST http://localhost:8000/api/query -H "Content-Type: application/json" -d '{"question":"林婉儿什么修为"}'
```
