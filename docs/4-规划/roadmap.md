# v1.0 路线图

## 总览

| Phase | 内容 | 预估 |
|-------|------|------|
| **5** | Vue 前端（聊天 + 章节 + 矛盾） | 2-3 天 |
| **6** | 后端集成 + 打包 exe | 1 天 |
| **7** | Agent + RAG 基础设施 | v1.0 后 |
| **8** | Multi-Agent 辩论系统 | v1.0 后 |

## Phase 5: Vue 前端（v1.0 MVP）

### 目标
提供一个可用的浏览器界面，用户不用 curl 就能操作。

### 功能范围
- 聊天对话框（输入问题 → 展示回答）
- 章节列表（状态、重解析按钮）
- 矛盾列表（查看、dismiss、confirm）
- 对话历史

### 不包含
- 悬浮窗模式（v1.0 不做）
- WebSocket 实时推送（v1.0 后）
- Agent 智能模式（v2.0）

### 技术栈
- Vue 3 + Vite + Tailwind CSS
- 编译产物 → FastAPI 托管

### 验收标准
1. 用户双击 exe → 浏览器打开 → 可聊天
2. 用户可查看已解析章节
3. 用户可查看矛盾检测结果
4. 用户可标记矛盾为 dismiss/confirm

## Phase 6: 后端集成 + 打包

### 目标
单 exe 文件，用户双击即可使用。

### 功能范围
- FastAPI 托管前端静态文件
- 自动打开浏览器（`webbrowser.open`）
- PyInstaller 打包配置
- 新手指南 + README 更新

### 验收标准
1. 双击 exe 启动后端，不依赖 Python 环境
2. 自动打开 http://localhost:8000
3. 前端正常调用全部 API

---

## 未来路线（v1.0 后）

## Phase 7: Agent + RAG

### 目标
引入 LangChain 和 RAG 检索，使复杂问题可被 Agent 拆解和推理。

### 功能范围
- LangChain tool 定义（包装现有 QueryEngine 方法）
- Chroma 向量数据库 + BGE 模型
- SQLite → Chroma 同步机制
- Planner Agent 拆解问题为子任务

## Phase 8: Multi-Agent 辩论

### 目标
用 LangGraph 实现多 Agent 协作论证。

### 功能范围
- LangGraph StateGraph 状态图
- Reviewer Agent（每个子任务独立审查）
- Integrator Agent（合并结果 + 消矛盾）
- 记忆系统（会话记忆 + 实体记忆）
- 重试机制（最多 3 次）
