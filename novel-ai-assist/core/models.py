"""Pydantic 校验模型——LLM 输出 JSON 的类型安全校验

职责：
- 定义 LLM 返回 JSON 的 Pydantic 模型
- 提供 model_validate() 方法校验 JSON 数据
- 校验失败时抛 ValidationError，由 parser.py 捕获处理

企业级原则覆盖：
- 技能管理 → 每个技能的输出有明确的 Schema 定义
- 知识积累 → evidence 字段非空校验，确保知识可溯源
"""

from pydantic import BaseModel, Field, field_validator


class StatusModel(BaseModel):
    """角色状态快照——固定 4 个键位，防止 LLM 自由发挥

    设计原因：如果让 LLM 自由写 status key，可能这章写
    "cultivation": "金丹期"，下章写 "修为": "金丹期"，
    导致跨章数据无法对比。
    """
    physical: str = Field(default="", description="身体状况")
    emotional: str = Field(default="", description="情绪状态")
    social: str = Field(default="", description="社会关系状态")
    location: str = Field(default="", description="当前位置")


class CharacterModel(BaseModel):
    """角色信息——对应 OUTPUT_SCHEMA.characters.items"""
    name: str = Field(..., min_length=1, description="角色名")
    aliases: list[str] = Field(default=[], description="别名列表")
    status: StatusModel = Field(
        default_factory=lambda: StatusModel(),
        description="角色状态快照",
    )
    description: str = Field(default="", description="角色描述")
    evidence: str = Field(default="", description="原文依据（30字以内）")


class RelationModel(BaseModel):
    """人物关系——对应 OUTPUT_SCHEMA.relations.items"""
    char_a: str = Field(..., min_length=1, description="角色A")
    char_b: str = Field(..., min_length=1, description="角色B")
    relation: str = Field(..., description="关系类型（师徒/敌对/爱慕等）")
    detail: str = Field(default="", description="关系补充描述")
    evidence: str = Field(default="", description="原文依据（30字以内）")


class PlotFlowItem(BaseModel):
    """剧情流向节点——对应 OUTPUT_SCHEMA.plot_flow.items

    作用：按叙事顺序记录一章的剧情节奏，供 Phase 4 矛盾检测使用。
    """
    order: int = Field(..., ge=1, description="叙事顺序（从1递增）")
    stage: str = Field(..., description="剧情阶段标签")
    description: str = Field(..., description="该阶段事件描述")
    characters: list[str] = Field(default=[], description="参与角色")
    location: str = Field(default="", description="事件发生地点")
    evidence: str = Field(default="", description="原文依据（30字以内）")


class TimelineEvent(BaseModel):
    """时间线事件——对应 OUTPUT_SCHEMA.timeline_events.items

    story_time 记录故事内时间（如"三年后"），用于跨章时间线对比。
    """
    event: str = Field(..., description="事件描述")
    story_time: str = Field(default="", description="故事内时间描述")
    narrative_order: int = Field(..., ge=1, description="本章叙事顺序")
    characters: list[str] = Field(default=[], description="参与角色")
    location: str = Field(default="", description="事件发生地点")
    evidence: str = Field(default="", description="原文依据（30字以内）")


class ForeshadowingModel(BaseModel):
    """伏笔——对应 OUTPUT_SCHEMA.foreshadowings.items

    confidence 和 confidence_label 配合使用：
    - high (0.8~1.0) → 明显伏笔，可以直接入库
    - medium (0.4~0.8) → 疑似伏笔，需要标注
    - low (0.0~0.4) → 不确定，可能误报
    """
    description: str = Field(..., min_length=1, description="伏笔描述")
    related_chars: list[str] = Field(default=[], description="相关角色")
    evidence: str = Field(default="", description="原文依据（30字以内）")
    confidence: float = Field(default=1.0, ge=0.0, le=1.0, description="置信度")
    confidence_label: str = Field(default="medium", description="置信度标签")


class UnresolvedQuestion(BaseModel):
    """未解问题——对应 OUTPUT_SCHEMA.unresolved_questions.items

    记录本章未解答的悬念，后续章节解析时对比是否已解答。
    """
    question: str = Field(..., min_length=1, description="未解问题描述")
    related_chars: list[str] = Field(default=[], description="相关问题角色")
    evidence: str = Field(default="", description="原文依据（30字以内）")


class MetaModel(BaseModel):
    """解析元信息——记录截断、警告等调试信息"""
    truncated: bool = Field(default=False, description="正文是否被截断")
    truncation_strategy: str = Field(default="", description="截断策略")
    warnings: list[str] = Field(default=[], description="解析警告列表")

    @field_validator("truncation_strategy", mode="before")
    @classmethod
    def coerce_null_to_empty(cls, v):
        """LLM 有时返回 null，Pydantic v2 会拒收 → 转成空字符串"""
        return v if v is not None else ""

    @field_validator("warnings", mode="before")
    @classmethod
    def coerce_null_to_empty_list(cls, v):
        """同上，warnings 也可能 null"""
        return v if v is not None else []


class ChapterExtract(BaseModel):
    """章节解析结果——顶层 Pydantic 模型，对应完整 LLM 输出

    这是 parser.py 最终校验使用的入口模型。
    model_validate() 会递归校验所有嵌套字段。
    """
    title: str = Field(default="", description="本章标题")
    summary: str = Field(default="", description="本章摘要")
    plot_flow: list[PlotFlowItem] = Field(default=[], description="剧情流向")
    characters: list[CharacterModel] = Field(default=[], description="角色列表")
    relations: list[RelationModel] = Field(default=[], description="关系列表")
    timeline_events: list[TimelineEvent] = Field(default=[], description="事件列表")
    foreshadowings: list[ForeshadowingModel] = Field(default=[], description="伏笔列表")
    unresolved_questions: list[UnresolvedQuestion] = Field(default=[], description="未解问题")
    meta: MetaModel = Field(default_factory=MetaModel, description="解析元信息")
