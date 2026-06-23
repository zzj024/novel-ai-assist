# 开发日志

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
