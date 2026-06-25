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

# 编译前端（需要 Node.js）
cd novel-ai-assist/frontend && npm install && npm run build

# 启动需要先用 proxy_on（访问 GitHub/DeepSeek 等外网）
# proxy_off（国内镜像/本地服务）
```

## Project Phases & Status

| Phase | 内容 | 状态 |
|-------|------|------|
| 1 | 项目骨架 + SQLite + config + 扫描模块 | ✅ 完成 |
| 2 | LLM 章节解析 → Pydantic 校验 → 数据库写入 | ✅ 完成 |
| 3 | REST API + 对话查询（三层查询引擎） | ✅ 完成 |
| 4 | 矛盾检测 + 审查持久化 + 缓存失效 + 语义版本号 | ✅ 完成 |
| — | 查询引擎工程化（规则层/质量检查/trace/Explain API） | ✅ 完成 |
| — | 描述性实体记忆（Episodic Entity Memory） | ✅ 完成 |
| **5** | **Vue 前端** — 聊天 + 章节列表 + 矛盾管理 | 🔄 **当前** |
| **6** | **PyInstaller 打包** — 单 exe 分发 | ⏳ |
| 7 | Agent + RAG 基础设施（LangChain + Chroma） | v1.0 后 |
| 8 | Multi-Agent 辩论系统（LangGraph） | v1.0 后 |

当前重点：Phase 5 Vue 前端 + Phase 6 打包
远期目标：v2.0 加入剧情续写 + Agent 智能编排

## Architecture Overview

### 当前（v1.0）

```
用户保存 .md 文件
       ↓
[watcher/monitor.py] 扫描 chapters/ 目录 → status = 'pending'
       ↓
[POST /api/reparse/{num}] 手动触发解析
       ↓
[core/parser.py] → LLM 结构化提取 → Pydantic 校验 → 重试 1 次
       ↓
[core/knowledge.py] 事务写入 7 张表
       ↓
[core/query.py] 三层查询引擎：LLM拆句 → 规则 enrich → SQL路由 → DeepSeek兜底
       ↓
[api/routes.py] 17 个 REST 端点 + WebSocket
       ↓
[frontend/] Vue 3 前端（聊天 / 章节管理 / 矛盾管理）
```

### 未来（v1.0 后 + Agent 层）

```
Vue 前端 → Agent 层 (LangChain + LangGraph)
               ↓
          ┌────┴────┐
          │ Planner │ → 拆解为子任务
          └────┬────┘
               ↓
     ┌─────────┴─────────┐
     ↓                    ↓
  简单子任务           复杂子任务
     ↓                    ↓
  QueryEngine        Multi-Agent 辩论
  (现有规则层)        (LangGraph + RAG)
     └─────────┬─────────┘
               ↓
          Reviewer (质量检查 × 最多 3 次)
               ↓
          Integrator (合并 → 去重 → 消矛盾)
```

详见 `docs/决策记录/adr-002-agent-architecture.md`

### Layer boundaries
- **api/**: HTTP 契约（schemas/routes/responses/deps），不写业务逻辑
- **core/**: 纯业务逻辑（models/knowledge/parser/query/contradiction）
- **watcher/**: 文件系统交互，只做扫描和状态标记
- **agent/**: Agent 编排层（v1.0 后，包装现有 QueryEngine）

## Database Schema (8 tables)

- **chapters** — 章节索引、解析状态、文件哈希、raw_text
- **characters** — 人物名、别名、4 键位 status 快照、status_history 变更记录
- **relations** — char_a/char_b/relation 三元组，unique 约束
- **timeline_events** — 故事时间线，含 narrative_order / evidence / is_anomaly
- **foreshadowings** — 伏笔，status 分 unrecovered/recovered
- **llm_parse_logs** — LLM 调用日志（debug 用）
- **contradiction_reviews** — 矛盾检测审查记录（fingerprint + status）
- **episodic_entities** — 描述性实体（"黑衣人"等）

## Key Conventions

### LLM Integration
- **DeepSeek**（主模型 `deepseek-chat`），**qwen2.5:7b**（拆句模型，本地 Ollama）
- 所有 LLM 调用走 `openai` 兼容 SDK，由 `config.py` 控制 api_base/api_key/model
- Parser 重试 1 次 + 四层 JSON 兜底（直接解析 → 代码块提取 → Pydantic 校验）
- Query 引擎三级降级（qwen → 规则 → DeepSeek 强制拆句）
- **职责分离**：LLM 只做拆句+指代消解，entities/intent 由规则层补齐

### Query Engine 改造（已完成）
- LLM prompt 从"四合一"轻量化 → 只做拆句 + 指代消解
- 实体提取：数据库角色 → 描述性实体 → 引号 → 姓氏正则
- 意图分类：加权打分 + INTENT_PRIORITY 优先级消解
- 质量检查：硬检查（结构）→ 软检查（内容）→ enrich 修复
- Debug trace：debug 模式输出 entities/intent/scores 变化

### Status Key
角色状态固定 4 键位：`physical / emotional / social / location`
不允许 LLM 自由发挥键名，确保跨章数据可比对。

### Write Strategy
全量覆盖写入：删除该章旧数据 → 插入新数据（非增量更新）
原理：以章为锚点，正文 `.md` 是唯一事实来源。

### Evidence
所有提取项（角色/关系/事件/伏笔/描述性实体）必须含 `evidence` 字段引用原文，供矛盾检测溯源。

### API Response Format
```json
{"ok": true, "data": ..., "error": null}   // 成功
{"ok": false, "data": null, "error": "..."} // 失败
```
所有端点通过 `api/responses.py` 的 `ok()/err()` 返回。

## 已解决的技术债务

| 原问题 | 状态 | 方案 |
|--------|------|------|
| qwen 职责过载 | ✅ 已解决 | LLM 只做拆句，实体/意图下沉到规则层 |
| 缺规则降级 | ✅ 已解决 | `_rule_split()` + `_enrich_split_items()` + `_split_quality_ok()` |
| 缺拆句质量检查 | ✅ 已解决 | 硬检查 + 软检查两阶段，软失败走 enrich 修复 |
| 缺 episodic entity memory | ✅ 已解决 | 新增 `episodic_entities` 表 + 查询集成 |
| 规则版本号全量 reset | ✅ 已解决 | 语义化版本比较，仅 major 变更触发 |

## 待办技术债务

| 问题 | 优先级 | 说明 |
|------|--------|------|
| 意图类型不足 | P1 | 缺 event/organization/causality 路由 |
| 答案合并缺冲突检测 | P2 | SQL 与 LLM 答案矛盾时不报错 |
| KB 返回格式不统一 | P2 | dict/list/string 混用 |
| Agent 模块 | 未来 | Phase 7: LangChain + RAG; Phase 8: Multi-Agent |

## 设计文档

- `docs/决策记录/adr-002-agent-architecture.md` — Agent + RAG + Multi-Agent 架构
- `docs/4-规划/roadmap.md` — 完整开发路线图
- `docs/tech-debt/agent-module-reservations.md` — Agent 模块技术债记录

## Common Tasks

```bash
# 新配置（首次运行自动创建）
# 配置文件：agent_data/config.json

# FastAPI 自动文档
open http://localhost:8000/docs

# 健康检查
curl http://localhost:8000/api/status

# 对话查询（普通模式）
curl -X POST http://localhost:8000/api/query \
  -H "Content-Type: application/json" \
  -d '{"question":"林婉儿什么修为"}'

# 对话查询（debug 模式，返回 intent_scores）
curl -X POST http://localhost:8000/api/query \
  -H "Content-Type: application/json" \
  -d '{"question":"林婉儿什么修为", "debug": true}'

# 查询路由解释
curl -X POST http://localhost:8000/api/query/debug \
  -H "Content-Type: application/json" \
  -d '{"question":"林婉儿和萧炎什么关系"}'
```
