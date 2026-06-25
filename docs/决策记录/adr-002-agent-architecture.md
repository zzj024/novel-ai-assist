# ADR-002: Agent + RAG + Multi-Agent 架构设计

## 状态
已批准

## 上下文
现有 Novel AI Assist 已经完成了 Phase 1-4，核心能力包括：
- LLM 章节解析 → SQLite 存储
- REST API + 三层查询引擎（规则→SQL→DeepSeek）
- 矛盾检测引擎（12 条规则）

当前 query 引擎是"规则为中心"（Rule-centric）的架构。为了：
1. 学习 LangChain / LangGraph / 多 Agent / RAG 技术
2. 处理复杂推理问题（规则层无法覆盖的场景）
3. 提供更灵活的回答整合机制

需要设计一个 Agent 层包装现有系统。

## 决策

### 架构原则
1. **包装不替代**：Agent 层是现有 QueryEngine 的上层包装，不修改 core/ 和 api/
2. **独立目录**：所有新代码在 `novel-ai-assist/agent/` 下
3. **渐进引入**：LangChain → RAG → Multi-Agent → 记忆系统，逐步加入

### 整体架构

```
用户问题
  ↓
┌──────────────────────────────────────┐
│  Agent 1: Planner (LangChain)        │
│  拆解为子任务列表                     │
│  每个子任务：{task, type, depends_on}  │
└──────────────┬───────────────────────┘
               ↓
    ┌──────────┴──────────┐
    ↓                      ↓
  简单子任务             复杂子任务
    ↓                      ↓
  调现有工具函数          Multi-Agent 论证
                          (LangGraph)
    ↓                      ↓
┌──────────────────────────────────────┐
│  Reviewer Agent (每个子任务独立)       │
│  质量检查 → 合格？→ 否→ 重试最多3次    │
└──────────────┬───────────────────────┘
               ↓
┌──────────────────────────────────────┐
│  Integrator Agent                     │
│  合并所有子任务结果 → 去重 → 消矛盾    │
└──────────────────────────────────────┘
```

### Planner 拆解策略

每个子任务标注：
- **type**: "simple"（走现有规则层）或 "complex"（走多 Agent）
- **depends_on**: 依赖的子任务 ID 列表（空 = 可并行）

执行策略：
- `depends_on: []` → 立即并行执行
- `depends_on: [id]` → 等依赖完成后串行

### 工具层定义

所有现有 QueryEngine 方法包装为 Agent Tool：
- `get_character_status(name)`
- `get_character_info(name)`
- `get_relation(char_a, char_b)`
- `get_all_relations(name)`
- `get_chapter_summary(num)`
- `list_chapters()`
- `list_foreshadowings(status)`
- `search_timeline(keyword)`
- `raw_text_search(query)` → RAG 向量检索

### RAG 向量检索

向量数据库：Chroma（嵌入式，零配置）
Embedding 模型：BGE-small-zh（本地运行，免费）

同步策略：
- characters（角色名+描述）→ 全量同步
- relations（关系描述）→ 全量同步
- timeline_events（事件描述）→ 全量同步
- chapters.raw_text（正文）→ 分块同步
- chapters.summary（摘要）→ 全量同步

### Multi-Agent 辩论 (LangGraph)

当子任务标注为 "complex" 时：
- 根据问题类型动态选择 Agent 组合
- 每个 Agent 从不同角度分析
- 结果汇总到 Arbiter

### Reviewer 机制

- 每个子任务完成后触发独立 Reviewer
- 检查标准：回答完整性、证据引用、矛盾性
- 不合格 → 最多重试 3 次
- 3 次后仍不合格 → 标记"低质量"供 Integrator 处理

### Integrator 合并

- 收集所有子任务结果
- 去重：相同信息只保留一份
- 消矛盾：冲突信息标注分歧
- 最终输出单一答案

## 后果

### 优点
- 现有 300+ 测试不碰，稳定性不变
- Agent 层独立实验区，不影响 v1.0 发布
- 技术栈从浅入深可渐进引入

### 缺点
- 增加架构复杂度，需维护两套查询路径
- 需要额外本地资源（Chroma 磁盘空间 + embedding 模型）
- 学习曲线：需同时掌握 LangChain 和 LangGraph

### 风险
- Chroma 数据与 SQLite 可能不一致（需同步策略）
- Multi-Agent 的 token 消耗和延迟

## 关联
- ADR-001:（本项目的第一个 ADR，项目骨架设计）
