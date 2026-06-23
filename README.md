# Novel AI Assist

> 一个基于 LLM 的长篇小说创作辅助工具。不生成正文，专注于结构化提取、逻辑校验与状态追踪，充当作者的「第二大脑」。

![Python](https://img.shields.io/badge/Python-3.13-blue)
![FastAPI](https://img.shields.io/badge/FastAPI-0.109-green)
![SQLite](https://img.shields.io/badge/SQLite-WAL%20mode-lightgrey)
![License](https://img.shields.io/badge/License-MIT-orange)

---

## 项目背景

写长篇小说时，作者面临一个核心痛点：**信息太多，记不住**。

几十万字的小说，几百个人物，错综复杂的关系网——单靠人脑很难追踪所有细节。传统的笔记软件需要手动整理，而现有的 AI 写作工具又偏向「生成内容」而非「管理内容」。

**Novel AI Assist** 的定位：一个纯粹的**分析工具**。

- 不生成任何小说正文
- 自动提取角色、关系、事件、伏笔
- 主动检测逻辑矛盾
- 支持自然语言查询小说设定

---

## 技术栈

| 层级 | 选型 | 理由 |
|------|------|------|
| Web 框架 | FastAPI | 原生异步，自动 OpenAPI 文档 |
| 数据库 | SQLite (WAL 模式) | 零配置，数据完全本地 |
| LLM 调用 | openai 兼容库 | 统一适配 DeepSeek / Ollama / 自定义 |
| 配置管理 | Pydantic | 类型安全，自动校验 |
| 测试 | pytest | Python 生态标准测试框架 |

---

## 功能

- [x] **定时扫描章节目录** —— 自动检测新增/变更文件，标记待解析
- [x] **LLM 章节解析** —— 结构化抽取（Pydantic 校验 + plot_flow + evidence, Phase 2 开发中）
- [ ] **对话查询** —— 三层策略：正则 → SQL → LLM 兜底（Phase 3）
- [ ] **矛盾检测** —— 规则引擎发现逻辑冲突（Phase 4）
- [ ] **WebSocket 实时推送** —— 解析结果主动通知（Phase 3~4）
- [ ] **前端悬浮窗** —— Vue 3 聊天 + 通知界面（Phase 5）

---

## 快速启动

```bash
# 1. 克隆
git clone https://github.com/zzj024/novel-ai-assist.git
cd novel-ai-assist

# 2. 安装依赖
pip install -r novel-ai-assist/requirements.txt

# 3. 启动
cd novel-ai-assist
uvicorn main:create_app --reload

# 4. 访问
open http://localhost:8000/docs      # Swagger UI
open http://localhost:8000/api/status # 健康检查
```

---

## 项目结构

```
novel-ai-assist/
├── main.py              # FastAPI 入口 + 生命周期
├── config.py            # 配置管理（Pydantic + JSON）
├── core/
│   └── knowledge.py     # SQLite 数据库连接 + 建表
├── watcher/
│   └── monitor.py       # 目录扫描 + 章序号提取
├── tests/
│   ├── test_config.py
│   ├── test_knowledge.py
│   ├── test_monitor.py
│   └── test_main.py
└── requirements.txt
```

---

## 核心架构

```
用户保存 .md 文件（或启动时）
       ↓
[watcher/monitor.py] 扫描 chapters/ 目录
       ↓
新文件 / 变更文件 → chapters 表 status → 'pending'
       ↓
用户通过 API 手动触发解析（POST /api/reparse/{num}）
       ↓
[core/parser.py] 调用 LLM 提取结构化数据
       ↓
[core/knowledge.py] 事务性写入 SQLite（5 张核心表）
       ↓
[core/conflict.py] 矛盾检测
       ↓
[api/ws.py] WebSocket 推送
```

### 数据库设计

| 表 | 用途 |
|------|--------|
| `chapters` | 章节索引、解析状态、文件哈希 |
| `characters` | 人物信息、别名、状态快照历史 |
| `relations` | 人物关系网 |
| `timeline_events` | 故事时间线事件 |
| `foreshadowings` | 伏笔埋设与回收追踪 |

---

## 开发路线图

| Phase | 内容 | 状态 |
|-------|------|------|
| **Phase 1** | 项目骨架 + SQLite + 配置 + 扫描模块 | ✅ **完成** |
| Phase 2 | LLM 章节解析 → Pydantic 校验 → 数据库写入 | ⏳ 进行中 |
| Phase 3 | REST API + 对话查询 | 📝 待开始 |
| Phase 4 | 矛盾检测 + WebSocket 推送 | 📝 待开始 |
| Phase 5 | Vue 前端悬浮窗 | 📝 待开始 |
| Phase 6 | 集成测试 + 边界打磨 | 📝 待开始 |

---

## License

[MIT](LICENSE)
