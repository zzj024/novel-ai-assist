"""API 请求/响应 Pydantic 模型

职责：
    - 定义 API 端点收什么、返什么的数据结构
    - 每个模型只暴露前端需要的字段，不直接暴露 DB 整行
    - FastAPI 自动据此生成 Swagger 文档

与 core/models.py 的区别：
    - core/models.py → 校验 LLM 输出（给 parser.py 内部用）
    - api/schemas.py → 定义 HTTP 收/发契约（给 routes.py 用）
"""

from pydantic import BaseModel, Field


# ── 通用 ─────────────────────────────────────────

class ErrorResponse(BaseModel):
    """统一错误响应"""
    detail: str = Field(..., description="错误描述")


class StatusResponse(BaseModel):
    """健康检查/状态响应"""
    status: str = Field("ok", description="服务状态")
    version: str = Field("0.1.0", description="应用版本")
    db_size_bytes: int = Field(0, description="数据库文件大小（字节）")
    chapters_total: int = Field(0, description="总章节数")
    chapters_parsed: int = Field(0, description="已解析章节数")


# ── 章节 ─────────────────────────────────────────

class ChapterListItem(BaseModel):
    """章节列表项——轻量，仅含列表页展示信息"""
    num: int = Field(..., ge=1, description="章序号")
    title: str = Field("", description="章节标题")
    status: str = Field("pending", description="解析状态")
    word_count: int = Field(0, description="正文字数")
    summary: str = Field("", description="摘要（截取前200字）")
    updated_at: str = Field("", description="更新时间")


class ChapterListResponse(BaseModel):
    """章节列表响应"""
    items: list[ChapterListItem] = Field(default=[], description="章节列表")
    total: int = Field(0, description="总章节数")


class ChapterResponse(BaseModel):
    """单章详情——返回完整解析信息"""
    num: int = Field(..., ge=1, description="章序号")
    title: str = Field("", description="章节标题")
    status: str = Field("pending", description="解析状态")
    word_count: int = Field(0, description="正文字数")
    summary: str = Field("", description="章节摘要")
    error_msg: str = Field("", description="解析错误信息（如有）")
    created_at: str = Field("", description="创建时间")
    updated_at: str = Field("", description="最后更新时间")


# ── 角色 ─────────────────────────────────────────

class CharacterListItem(BaseModel):
    """角色列表项"""
    name: str = Field(..., min_length=1, description="角色名")
    aliases: list[str] = Field(default=[], description="别名")
    first_appeared: int = Field(..., ge=1, description="首次出场章节")
    last_seen: int = Field(..., ge=1, description="最近出现章节")
    physical: str = Field("", description="当前修为/身体状况")
    location: str = Field("", description="当前位置")


class CharacterListResponse(BaseModel):
    """角色列表响应"""
    items: list[CharacterListItem] = Field(default=[], description="角色列表")
    total: int = Field(0, description="总角色数")


class CharacterResponse(BaseModel):
    """角色详情——含完整状态快照"""
    name: str = Field(..., min_length=1, description="角色名")
    aliases: list[str] = Field(default=[], description="别名")
    first_appeared: int = Field(..., ge=1, description="首次出场章节")
    last_seen: int = Field(..., ge=1, description="最近出现章节")
    current_status: dict = Field(default={}, description="当前状态快照")
    description: str = Field("", description="角色描述")
    updated_at: str = Field("", description="最后更新时间")


# ── 人物关系 ────────────────────────────────────

class RelationResponse(BaseModel):
    """人物关系项"""
    char_a: str = Field(..., description="角色A")
    char_b: str = Field(..., description="角色B")
    relation: str = Field(..., description="关系类型（师徒/敌对/爱慕等）")
    detail: str = Field("", description="关系补充描述")
    chapter: int = Field(..., ge=1, description="记录章节")


class RelationListResponse(BaseModel):
    """人物关系列表响应"""
    items: list[RelationResponse] = Field(default=[], description="关系列表")
    total: int = Field(0, description="总关系数")


# ── 时间线 ──────────────────────────────────────

class TimelineResponse(BaseModel):
    """时间线事件"""
    chapter: int = Field(..., ge=1, description="所属章节")
    story_time: str = Field("", description="故事内时间描述")
    event: str = Field(..., description="事件描述")
    narrative_order: int = Field(1, ge=1, description="本章叙事顺序")
    characters: list[str] = Field(default=[], description="参与角色")
    location: str = Field("", description="事件发生地点")
    evidence: str = Field("", description="原文依据")
    is_anomaly: bool = Field(False, description="是否时间线异常")


class TimelineListResponse(BaseModel):
    """时间线列表响应"""
    items: list[TimelineResponse] = Field(default=[], description="事件列表")
    total: int = Field(0, description="总事件数")


# ── 伏笔 ────────────────────────────────────────

class ForeshadowingResponse(BaseModel):
    """伏笔条目"""
    description: str = Field(..., min_length=1, description="伏笔描述")
    laid_chapter: int = Field(..., ge=1, description="埋设章节")
    recovered_at: int | None = Field(None, description="回收章节（未回收为 null）")
    status: str = Field("unrecovered", description="回收状态")
    related_chars: list[str] = Field(default=[], description="相关角色")
    evidence: str = Field("", description="原文依据")
    confidence: float = Field(1.0, ge=0.0, le=1.0, description="置信度")
    confidence_label: str = Field("medium", description="置信度标签")


class ForeshadowingListResponse(BaseModel):
    """伏笔列表响应"""
    items: list[ForeshadowingResponse] = Field(default=[], description="伏笔列表")
    total: int = Field(0, description="总伏笔数")
    recovered: int = Field(0, description="已回收数")
    unrecovered: int = Field(0, description="未回收数")


# ── 对话查询 ─────────────────────────────────

class QueryRequest(BaseModel):
    """对话查询请求"""
    question: str = Field(..., min_length=1, description="用户问题")


class QueryResponse(BaseModel):
    """对话查询响应"""
    answer: str = Field("", description="答案文本")
    source: str = Field("sql", description="答案来源（sql/llm/mixed/polished）")
