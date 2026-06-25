"""Phase 4 矛盾检测数据模型

包含：
- Severity / IssueType / ContradictionType 枚举
- RuleResult 统一结果模型
- ScanSummary / ScanResult 扫描结果
- BaseRule 规则基类接口
- RuleContext 数据快照
"""


from __future__ import annotations

import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field

class Severity(str, Enum):
    """严重级别"""
    CRITICAL = "critical"     # 确定性矛盾
    WARNING = "warning"       # 需作者确认
    INFO = "info"             # 提醒类

class IssueType(str, Enum):
    """问题类型——区分不同性质的检测结果"""
    CONTRADICTION = "contradiction"  # 确定性矛盾
    REVIEW_NEEDED = "review_needed"  # 需作者复核
    TRACKING = "tracking"            # 提醒/跟踪
    INTEGRITY = "integrity"          # 数据完整性问题


class IssueKind(str, Enum):
    """结果种类——供 UI 区分结果性质"""
    CONTRADICTION = "contradiction"    # 硬冲突
    REVIEW_NEEDED = "review_needed"    # 软异常，需复核
    TRACKING = "tracking"              # 长期未处理提醒
    INTEGRITY = "integrity"            # 数据自相矛盾


class ContradictionType(str, Enum):
    """具体矛盾类型——每个规则对应一个"""
    # A 类：角色状态变化
    STATUS_CHANGE_ANOMALY = "status_change_anomaly"
    LOCATION_CHANGE_NO_TRAVEL = "location_change_no_travel"
    SAME_TIME_DIFF_LOCATION = "same_time_diff_location"
    # B 类：时间线
    NARRATIVE_ANOMALY = "narrative_anomaly"
    TIMELINE_FLAG = "timeline_flag"
    # C 类：关系
    RELATION_ABRUPT = "relation_abrupt"
    RELATION_CONFLICT = "relation_conflict"
    # D 类：伏笔
    FORESHADOWING_AGING = "foreshadowing_aging"
    FORESHADOWING_STALE = "foreshadowing_stale"
    FORESHADOWING_INTEGRITY = "foreshadowing_integrity"
    # E 类：完整性
    ALIAS_COLLISION = "alias_collision"
    CHAPTER_INTEGRITY = "chapter_integrity"

class RuleResult(BaseModel):
    """单条规则的一条检测结果

    所有规则统一使用此模型输出，engine层据此做排序/去重/审查合并。
    """
    fingerprint: str = Field(...,description="稳定指纹，用于去重和 dismiss")
    issue_type: IssueType = Field(..., description="问题类型")
    kind: IssueKind = Field(..., description="结果种类")
    severity: Severity = Field(..., description="严重级别")
    contradiction_type: ContradictionType = Field(...,description="矛盾类型")
    rule_name: str = Field(..., description="规则名称")
    rule_version: str = Field(default="1.0", description="规则版本号")
    description: str = Field(...,description="人类可读的矛盾描述")
    detail: dict = Field(default_factory=dict,description="结构化细节，供 UI 和 fingerprint 使用")
    evidence: list[str] = Field(default_factory=list,description="原文引用")
    chapter_range: tuple[int, int] = Field(default=(0, 0),description="涉及章节范围 (start, end)")
    related_chars: list[str] = Field(default_factory=list,description="涉及角色")
    score: float = Field(default=1.0, ge=0.0, le=1.0,description="置信度")
    status: str = Field(default="open", description="open / dismissed / confirmed")
    explained: bool = Field(default=False,description="是否有合理解释（如跌境事件）")

class ScanSummary(BaseModel):
    """一次扫描的统计摘要"""
    total: int = 0
    by_severity: dict[str, int] = Field(default_factory=dict)
    by_issue_type: dict[str, int] = Field(default_factory=dict)
    by_contradiction_type: dict[str, int] = Field(default_factory=dict)
    open_count: int = 0
    dismissed_count: int = 0
    duration_ms: float = 0.0

@dataclass
class RuleContext:
    """检测上下文——engine 一次性预加载的数据快照
    所有规则共享此数据，避免每条规则各自查库。
    """
    characters: list[dict] = field(default_factory=list)
    status_by_char: dict[str, list[dict]] =field(default_factory=dict)
    timeline_events: list[dict] = field(default_factory=list)
    timeline_by_story_time: dict[str, list[dict]] =field(default_factory=dict)
    timeline_by_chapter: dict[int, list[dict]] =field(default_factory=dict)
    relations: list[dict] = field(default_factory=list)
    relations_by_pair: dict[tuple[str, str], list[dict]] =field(default_factory=dict)
    foreshadowings: list[dict] = field(default_factory=list)
    max_parsed_chapter: int = 0
    chapters: list[dict] = field(default_factory=list)
    config: dict = field(default_factory=dict)


class BaseRule(ABC):
    """所有规则的基类

    子类只需实现 check() 方法，返回 RuleResult 列表。
    """
    name: str = ""
    description: str = ""
    version: str = "1.0"
    contradiction_type: ContradictionType =ContradictionType.STATUS_CHANGE_ANOMALY
    default_severity: Severity = Severity.WARNING
    default_issue_type: IssueType = IssueType.REVIEW_NEEDED

    @abstractmethod
    def check(self, ctx: RuleContext) -> list[RuleResult]:
        """执行规则检测，返回匹配的结果列表"""
        ...