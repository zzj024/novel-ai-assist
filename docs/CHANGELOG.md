# 开发日志

## 2026-06-25 — Phase 3 Step 4 query 引擎 + GPT 架构 Review

### 完成

- **core/query.py** — 三层查询引擎完整实现
  - _split() → qwen2.5:7b 拆句 + 实体提取 + 意图分类
  - _route() → 8 种意图路由到 KnowledgeBase SQL 查询
  - _fallback_llm() → DeepSeek 带精简上下文兜底
  - _merge() → 全 SQL 代码模板合并 / 混 LLM 可选润色
  - FocusTracker → 当前讨论角色追踪（5 轮无实体自动清空）
  - ConversationHistory → 最近 3 轮对话记忆

- **api/routes.py** — POST /api/query 端点
- **api/schemas.py** — QueryRequest + QueryResponse 模型
- **config.py** — 新增 query_cheap_base / query_cheap_model 字段

### GPT 架构 Review 结论

提交 GPT 评审 query 引擎设计，核心发现：

| 级别 | 问题 | 说明 |
|------|------|------|
| P0 | 小模型职责过载 | 7B 模型同时做拆句+实体+意图+指代，单点语义瓶颈 |
| P0 | 缺规则降级 | 小模型挂了目前全瘫，需要 heuristic 兜底 |
| P0 | 缺拆句质量检查 | 返回 JSON 后应验证字段完整性，不合格自动降级 |
| P1 | 缺 episodic memory | "黑衣人"类描述性实体无法解析，Phase 4 一起做 |
| P1 | 意图类型不足 | 缺 event / organization / causality |
| P2 | 答案合并缺冲突检测 | SQL 与 LLM 答案矛盾时不报错 |

详见 `.claude/memory/tech-debt-review-20260625.md`

### 待办

- P0: 加规则降级 + 质量检查（heuristic_intent + extract_regex_entities）
- P0: 拆句质量验证函数
- P1: Phase 4 加 episodic entity memory
- P1: 扩意图类型（event/organization/recent/causality）

---

## 2026-06-24 — Phase 3 Step 2 api/ 基础设施完成

### 完成

- **P3-01 KnowledgeBase 查询方法扩展**
  - count_chapters() — 按状态统计章节数
  - list_characters() — 角色列表 + 模糊搜索
  - list_relations() — 关系列表 + 双端筛选
  - list_timeline() — 时间线事件 + 按章节筛选
  - list_foreshadowings() — 伏笔列表 + 按状态筛选

- **P3-02 api/ 基础设施（4 个文件）**
  - schemas.py — 14 个 Pydantic 请求/响应模型
  - responses.py — ok()/err() 统一信封 + jsonable_encoder 序列化
  - deps.py — get_db() yield generator 注入（留事务扩展点）
  - routes.py — 8 个 REST 端点（含 /api/status 从 main.py 迁入）

- **测试覆盖**
  - test_schemas.py — 17 个 Schema 验证
  - test_api.py — 15 个 API 集成测试（TestClient + dependency_overrides）
  - 全量 70 passed, 1 skipped（集成测试因缺 API key 跳过）

### 修复

- watcher/monitor.py — 重复 import re + logging 变量名冲突
- core/knowledge.py — get_character() 缩进位错
- api/deps.py — get_config() 调用 load_config() 缺参数（已替换为直接创建 KB）
- api/routes.py — error_msg 来自 DB 可能为 None，需 or "" 处理
- api/responses.py — 缺少 jsonable_encoder，Pydantic 模型无法 JSON 序列化

### 关键决策

| 决策 | 结论 | 理由 |
|------|------|------|
| deps.py get_config | 暂时移除 | Settings 模型当前不含 db_path |
| 依赖覆盖方式 | generator function | get_db 是 yield generator，覆盖必须对等 |
| 测试隔离 | dependency_overrides | 每个测试用独立 tmp_path 数据库 |

### 待办

- Phase 3 Step 3：确定性 REST 端点增强（分页/排序）
- Phase 3 Step 4：core/query.py 三层查询引擎（正则 → SQL → LLM）
- Phase 3 Step 5：WebSocket /ws 推送

---

## 2026-06-24 — Phase 3 规划设计 + 全文档同步

### 完成

- **P3-00 Phase 3 架构设计决策（GPT 讨论 + 定案）**
  - 路由组织：APIRouter，端点统一放 `api/routes.py`
  - 响应格式：Pydantic 模型 + ok()/err() helper 结合
  - 三层查询：新建 `core/query.py`，knowledge.py 只做数据访问
  - LLM 兜底策略：精简检索式上下文，不喂全量库
  - CORS：现在就加，通过 `Settings.cors_origins` 配置控制
  - `/api/status` 迁入 routes.py，避免端点散落两地

### 关键决策

| 决策 | 结论 | 理由 |
|------|------|------|
| API 层结构 | `routes.py` + `schemas.py` + `responses.py` + `deps.py` | 边界清晰，每层单一职责 |
| 落地顺序 | 读方法 → 确定性REST → 正则+SQL → LLM兜底 → WebSocket | 每步可验收 |
| knowledge.py 定位 | 纯数据访问层，不做推理 | 避免 Phase 4 时变成一锅粥 |
| LLM fallback 上下文 | 只放相关角色/事件/最近摘要，不放 raw_text 和配置 | 结构化记忆是核心价值 |

### 文档同步

- `project-foundation.md`：目录结构、API 契约、分层边界、CORS 配置全量更新
- `phase-roadmap.md`：Phase 3 从"待规划"升级为完整实施计划（5 步落地）
- `README.md`：项目结构图、数据流图、路线图同步更新
- `docs/CHANGELOG.md`：本条记录

### 待办

- Phase 3 Step 1：KnowledgeBase 补读方法 + 测试
- Phase 3 Step 2：搭建 api/ 基础设施（schemas/responses/deps + 迁 status）

---

## 2026-06-24 — Phase 2 核心实现 + 企业级五大标准同步

### 完成

- **P2-02 core/models.py** — 9 个 Pydantic 模型，类型安全校验
- **P2-03 core/extract_prompt.py** — SYSTEM_PROMPT + OUTPUT_SCHEMA + build_extract_messages()
- **P2-04 core/parser.py** — ChapterParser：四层 JSON 兜底 + 重试 + 事务写入
- **P2-05 core/knowledge.py 扩展** — 第 6 张表 llm_parse_logs + Schema 迁移 + 事务覆盖写入
- **企业级标准全量同步** — 大厂 Agent 五维标准写入 6 份文档
- **测试覆盖** — parser 单元测试 3 路径 + 集成测试框架，全量 30 passed

### 关键决策
- PROMPT_VERSION 走 git 版本管理，不留注释旧代码
- status 固定 4 键位（physical/emotional/social/location）防 LLM 自由发挥
- 全量覆盖写入而非增量更新
- 集成测试用 @pytest.mark.integration 标记，默认跳过

### 待办
- 实际跑通集成测试（需 DEEPSEEK_API_KEY 环境变量）
- Phase 3：REST API + 对话查询（三层路由）

## 2026-06-23 — Phase 2 规划设计 + GitHub 仓库初始化

### 完成

- **P2-01 Phase 2 规划设计**
  - 明确 Phase 2 范围："够支撑后续分析的结构化抽取"，不做一步到位
  - GPT 5.5 Thinking 深度分析，确认架构方向

### 关键决策

| 决策 | 选定方案 | 拒绝方案 | 理由 |
|------|---------|---------|------|
| 输出架构 | 保留 summary + 新增 plot_flow + unresolved_questions | 只保留 summary 或全部结构化 | summary 给人看，plot_flow 给系统分析用 |
| evidence | 所有模块加 evidence 字段 | 只放原文 hash | 矛盾检测需要可追溯原文依据 |
| 大章节策略 | head-middle-tail 抽样（35%/30%/35%） | 中间截断 / 全量分段合并 | 中间截断丢关键转折；分段合并成本高，Phase 2 不做 |
| status 结构 | 固定键位 physical/emotional/social/location | 自由 JSON | 防止模型乱填 |
| 校验层 | 现在加 Pydantic model_validate | 后面再加 | LLM 输出稳定性差，校验必须前置 |
| 解析日志 | 轻量 llm_parse_logs 表 | parse_run_id 完整归档 | 先做 debug 日志，历史归档 Phase 4 再做 |
| status_changes | Phase 4 再做 | 现在做 | 跨章节分析时更稳 |
| relation.change | Phase 4 再做 | 现在做 | 防止模型跨章脑补 |

### Phase 2 MVP Schema（定案）

```json
{
  "title", "summary",
  "plot_flow": [{order, stage, description, characters, location, evidence}],
  "characters": [{name, aliases, status:{p/e/s/l}, description, evidence}],
  "relations": [{char_a, char_b, relation, detail, evidence}],
  "timeline_events": [{event, story_time, narrative_order, characters, location, evidence}],
  "foreshadowings": [{description, related_chars, evidence, confidence, confidence_label}],
  "unresolved_questions": [{question, related_chars, evidence}],
  "meta": {truncated, truncation_strategy, warnings}
}
```

### 待办

- Phase 2 实现：models.py → extract_prompt.py → parser.py → knowledge.py 扩展

---

## 2026-06-22~23 — Phase 1 项目骨架搭建

### 完成

- **P1-01 项目地基设计**
  - 目录结构、SQLite 5 张核心表 Schema、API 契约、配置系统
  - 技术栈：FastAPI + SQLite + Pydantic + pytest
  - 制定 Phase 1~6 完整路线图

- **P1-02 配置管理系统（config.py）**
  - Pydantic `Settings` 模型，所有字段含默认值
  - `load_config()` / `save_config()` JSON 持久化
  - `init_default_config()` 首次启动自动创建
  - `masked_api_key` 属性：保留前6后2，如 `sk-abc****op`
  - 6 个测试用例全部通过

- **P1-03 SQLite 数据库层（core/knowledge.py）**
  - `KnowledgeBase` 类：`threading.local()` 线程隔离
  - WAL 模式 + 外键约束 + busy_timeout 5000ms
  - 5 张核心表（chapters, characters, relations, timeline_events, foreshadowings）
  - 幂等建表（`CREATE TABLE IF NOT EXISTS`）
  - 6 个测试用例全部通过

- **P1-04 目录扫描模块（watcher/monitor.py）**
  - `extract_chapter_num()` 正则提取章序号（支持中文/英文/纯数字）
  - `scan_chapters()` 扫描目录，通过文件大小 + MD5 哈希检测变更
  - 7 个测试用例全部通过

- **P1-05 应用入口（main.py）**
  - `create_app()` FastAPI 应用工厂
  - lifespan 生命周期：加载配置 → 初始化数据库 → 首次扫描 → 定时扫描
  - `GET /api/status` 健康检查端点
  - 3 个测试用例全部通过

- **P1-06 GitHub 仓库初始化**
  - README.md（项目介绍、技术栈、快速启动、架构图）
  - MIT License
  - .gitignore 配置
  - CHANGELOG.md 开发日志

### 关键决策记录

| 决策 | 方案 | 替代方案 | 理由 |
|------|------|---------|------|
| 文件检测 | 定时扫描 + 手动触发 | watchdog 实时监听 | 降低复杂度，避免不必要的 LLM 调用 |
| 扫描变更检测 | 文件大小 + MD5 哈希 | 仅比对修改时间 | 更精准地检测内容变化 |
| 数据库更新 | 全量覆盖写入 | 增量更新 | 以章为锚点，避免碎片残留 |
| 数据库配置 | `auto_scan_interval` | 固定间隔 | 用户可在前端调整 |
| 测试方案 | pytest + tmp_path + TestClient | 集成测试 | 快速、隔离、不依赖真实文件系统 |

### 遇到的问题

#### 1. SQLite 外键约束默认关闭

**问题**：SQLite 默认 `PRAGMA foreign_keys = OFF`，即使写了 `REFERENCES` 也不会校验。
**解决**：在 `get_conn()` 中显式执行 `PRAGMA foreign_keys = ON`。

#### 2. VSCode 测试运行器配置

**问题**：点运行按钮 pytest 不启动，测试文件无响应。
**解决**：安装 Python 扩展 → Ctrl+Shift+P → Python: Configure Tests → 选择 pytest。

#### 3. threading.local() 属性访问

**问题**：`hasattr(self._local, "conn")` 检查与 `self._local.conn` 不一致，出现 AttributeError。
**解决**：保持命名统一，全文件使用 `self.local`（无下划线前缀）。

#### 4. config 字段更新后测试未同步

**问题**：`watch_delay` 改为 `auto_scan_interval` 后，测试断言仍使用旧值 `2.0`。
**解决**：全局搜索替换，测试断言同步更新为 `3600`。

#### 5. 文件名中文数字解析

**问题**：作者可能使用「第一章」和「第1章」两种格式。
**解决**：MVP 阶段只支持阿拉伯数字格式（第1章），中文数字（第一章）暂不支持——Phase 5 前端统一创建文件后可保证格式一致。

### 待办

- Phase 2：LLM 章节解析
- 补充 docs/architecture.md 架构文档
