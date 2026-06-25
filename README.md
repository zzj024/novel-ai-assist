# Novel AI Assist

> 一个基于 LLM 的长篇小说创作辅助工具。不生成正文，专注于结构化提取、逻辑校验与状态追踪，充当作者的「第二大脑」。

![Python](https://img.shields.io/badge/Python-3.13-blue)
![FastAPI](https://img.shields.io/badge/FastAPI-0.109-green)
![SQLite](https://img.shields.io/badge/SQLite-WAL%20mode-lightgrey)
![Vue](https://img.shields.io/badge/Vue-3.4-brightgreen)
![Tests](https://img.shields.io/badge/tests-303_passed-brightgreen)
![License](https://img.shields.io/badge/License-MIT-orange)

---

## 项目背景

写长篇小说时，作者面临一个核心痛点：**信息太多，记不住**。

几十万字的小说，几百个人物，错综复杂的关系网——单靠人脑很难追踪所有细节。传统的笔记软件需要手动整理，而现有的 AI 写作工具又偏向「生成内容」而非「管理内容」。

**Novel AI Assist** 的定位：一个**长篇小说创作辅助系统**。

v1.0 定位**分析工具**：
- 自动提取角色、关系、事件、伏笔
- 主动检测逻辑矛盾
- 支持自然语言查询小说设定

v2.0 扩展到**创作辅助**：
- 基于已有设定的智能续写
- 大纲和剧情引导
- 逻辑一致性校验（生成后自动检测矛盾）

---

## 功能

- [x] **定时扫描章节目录** —— 自动检测新增/变更文件，标记待解析
- [x] **LLM 章节解析** —— 结构化抽取（Pydantic 校验 + plot_flow + evidence）
- [x] **对话查询** —— 三层策略：正则 → SQL → LLM 兜底
- [x] **矛盾检测** —— 12 条规则（A 状态变化 / B 时间线 / C 关系 / D 伏笔 / E 完整性）
- [x] **WebSocket 实时推送** —— 解析结果主动通知 + 重解析触发
- [x] **审查持久化** —— 矛盾结果 dismiss/confirm/review API
- [x] **缓存失效** —— 基于 digest SHA256 自动失效
- [x] **规则版本号** —— 语义化版本比较，minor/patch 变化不触发 reset
- [x] **描述性实体记忆** —— "黑衣人""白衣女子"类实体入库识别
- [x] **查询路由解释** —— debug 模式输出意图得分明细
- [ ] **Vue 前端** —— 聊天 + 章节管理 + 矛盾管理（Phase 5，进行中）

> 下一阶段（v1.0 后）：剧情续写 + Agent + RAG + Multi-Agent 辩论系统 → 见 `docs/`

---

## 快速启动

### 方式一：双击 exe（推荐）

从 Releases 下载 `novel-ai-assist.exe`，双击启动。
浏览器自动打开 http://localhost:8000

### 方式二：源码运行

```bash
# 1. 安装依赖
pip install -r novel-ai-assist/requirements.txt

# 2. 启动
cd novel-ai-assist
uvicorn main:create_app --reload --port 8000

# 3. 访问
open http://localhost:8000      # Vue 前端
open http://localhost:8000/docs # Swagger UI
```

### 前提条件

- **章节解析**：需配置 DeepSeek API Key（首次启动自动创建配置文件）
- **拆句模型**：可选安装本地 Ollama + qwen2.5:7b（无则自动降级为规则拆句）
- 详见 `新手引导.md`

---

## 项目结构

```
novel-ai-assist/
├── main.py                  # FastAPI 入口 + 生命周期
├── config.py                # 配置管理（Pydantic + JSON）
├── core/                    # 纯业务逻辑层
│   ├── knowledge.py         # SQLite 数据访问层（7 张表）
│   ├── query.py             # 三层查询引擎（规则→SQL→LLM）
│   ├── models.py            # Pydantic 校验模型（含 EpisodicEntity）
│   ├── parser.py            # LLM 章节解析调度器
│   ├── extract_prompt.py    # LLM Prompt 模板
│   └── contradiction/       # 矛盾检测引擎（12 条规则）
├── api/                     # HTTP 契约层
│   ├── routes.py            # 17 个 REST 端点 + WebSocket
│   ├── schemas.py           # 请求/响应模型
│   ├── responses.py         # ok()/err() 统一信封
│   ├── deps.py              # 依赖注入
│   └── ws_manager.py        # WebSocket 连接池
├── watcher/                 # 文件系统交互
│   └── monitor.py           # 目录扫描 + 章序号提取
├── agent/                   # Agent 层（v1.0 后实现）
│   ├── tools.py             # 工具定义
│   ├── planner.py           # 问题拆解
│   └── graph.py             # LangGraph 编排
├── frontend/                # Vue 3 前端（Phase 5）
├── tests/                   # 303 个测试
│   ├── test_query_split_rules.py    # 查询引擎规则层（90 测试）
│   ├── test_contradiction_*.py      # 矛盾检测（各规则独立测试）
│   ├── test_api.py / test_schemas.py# API 集成测试
│   └── ...
└── requirements.txt
```

---

## 核心架构

### 当前（v1.0）

```
用户 .md 文件 → watcher → parser (LLM) → SQLite
                                              ↓
Vue 前端 → REST API → QueryEngine (规则→SQL→LLM)
                              ↓
                        矛盾检测引擎 (12 规则)
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
  调 QueryEngine     Multi-Agent 辩论
     ↓               (LangGraph + RAG)
     └─────────┬─────────┘
               ↓
          Reviewer (质量检查 × 最多 3 次)
               ↓
          Integrator (合并 → 去重 → 消矛盾)
```

详情见 `docs/` 目录。

### 数据库（7 张表）

| 表 | 用途 | 状态 |
|------|------|------|
| `chapters` | 章节索引、解析状态、文件哈希 | ✅ |
| `characters` | 人物信息、别名、4 键位状态快照 | ✅ |
| `relations` | 人物关系网（char_a/char_b/relation） | ✅ |
| `timeline_events` | 故事时间线事件 | ✅ |
| `foreshadowings` | 伏笔埋设与回收追踪 | ✅ |
| `llm_parse_logs` | LLM 调用日志 | ✅ |
| `contradiction_reviews` | 矛盾检测审查记录 | ✅ |
| `episodic_entities` | 描述性实体（"黑衣人"等） | ✅ |

---

## 开发路线图

### 已完成

| Phase | 内容 | 状态 |
|-------|------|------|
| 1 | 项目骨架 + SQLite + 配置 + 扫描模块 | ✅ |
| 2 | LLM 章节解析 → Pydantic 校验 → 数据库写入 | ✅ |
| 3 | REST API + 对话查询（三层查询引擎） | ✅ |
| 4 | 矛盾检测 + 审查持久化 + 缓存失效 + 版本号 | ✅ |
| — | 查询引擎工程化（规则层 / 质量检查 / trace） | ✅ |
| — | 语义版本 / 描述性实体记忆 / Explain API | ✅ |

### 进行中

| Phase | 内容 | 进度 |
|-------|------|------|
| **5** | **Vue 前端** — 聊天 + 章节列表 + 矛盾管理 | 🔄 **当前** |
| **6** | **PyInstaller 打包** — 单 exe 分发 | ⏳ |

### v1.0 后规划

| Phase | 内容 | 说明 |
|-------|------|------|
| **7** | Agent + RAG 基础设施 | LangChain tool 定义 + Chroma 向量库 |
| **8** | Multi-Agent 辩论系统 | LangGraph 状态图 + 多 Agent 论证 |
| — | 前端悬浮窗 | Tauri 桌面窗口（可选） |

---

## 文档

- `docs/决策记录/adr-002-agent-architecture.md` — Agent 模块架构设计
- `docs/4-规划/roadmap.md` — 完整路线图
- `docs/tech-debt/agent-module-reservations.md` — 技术债记录

---

## License

[MIT](LICENSE)
