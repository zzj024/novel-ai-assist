"""角色状态变化异常检测规则（A 类）

核心原则：不判断"变化是否合理"，只判断"变化是否有叙事记录支撑"。

包含：
- StatusChangeAnomalyRule: 4 个状态字段（physical/emotional/social/location）
  的跨章变化，检查附近是否有解释性事件
- LocationChangeWithoutTravelRule: 位置变化缺少旅程事件
"""

import json
import logging
from typing import Any

from core.contradiction.fingerprint import make_fingerprint
from core.contradiction.models import (
    BaseRule,
    ContradictionType,
    IssueKind,
    IssueType,
    RuleContext,
    RuleResult,
    Severity,
)

logger = logging.getLogger(__name__)


# ── 通用解释关键词（不依赖任何世界观）────────────

GENERIC_EXPLANATION_KEYWORDS = [
    "变得", "变成", "成为", "恢复", "失去", "获得",
    "受伤", "治愈", "痊愈", "昏迷", "醒来", "死亡", "复活",
    "中毒", "解毒", "感染", "康复",
    "喝酒", "醉", "病倒",
    "加入", "离开", "背叛", "投靠", "升任", "册封",
    "被贬", "逐出", "前往", "抵达", "返回", "逃往", "进入",
    "来到", "赶到", "传送", "迁移",
]

# 按字段分组的解释关键词
FIELD_KEYWORDS: dict[str, list[str]] = {
    "physical": [
        "受伤", "伤", "痊愈", "恢复", "昏迷", "醒来",
        "中毒", "解毒", "感染", "虚弱", "死亡", "复活",
        "喝酒", "醉", "病", "治疗",
    ],
    "social": [
        "加入", "离开", "背叛", "投靠", "升任", "册封",
        "被贬", "逐出", "成为", "身份", "职位", "阵营",
    ],
    "location": [
        "前往", "抵达", "离开", "返回", "逃往", "进入",
        "来到", "赶到", "传送", "迁移",
    ],
    "emotional": [
        "愤怒", "恐惧", "崩溃", "悲伤", "震惊",
        "冷静", "坚定", "动摇",
    ],
}

# 变化太细微时忽略的修饰词
TRIVIAL_PREFIXES = ["有些", "略微", "十分", "非常", "仍然", "保持", "似乎", "有点"]

# 默认检查的字段及其敏感度配置
FIELD_CONFIG: dict[str, dict[str, Any]] = {
    "physical": {
        "enabled": True,
        "default_severity": Severity.WARNING,
    },
    "social": {
        "enabled": True,
        "default_severity": Severity.WARNING,
    },
    "location": {
        "enabled": True,
        "default_severity": Severity.WARNING,
    },
    "emotional": {
        "enabled": False,  # 情绪变化太频繁，默认关闭
        "default_severity": Severity.INFO,
    },
}


def _normalize_text(value: str) -> str:
    """去掉修饰前缀，用于过滤细微变化"""
    cleaned = value.strip()
    for prefix in TRIVIAL_PREFIXES:
        if cleaned.startswith(prefix):
            cleaned = cleaned[len(prefix):].strip()
            break
    return cleaned


def _is_trivial_change(old: str, new: str) -> bool:
    """判断变化是否过于细微，不值得报"""
    if not old or not new:
        return True
    return _normalize_text(old) == _normalize_text(new)


def _has_explanation_in_events(
    ctx: RuleContext,
    char_name: str,
    chapter_start: int,
    chapter_end: int,
    field: str,
    old_value: str,
    new_value: str,
) -> bool:
    """检查指定章节范围内是否有解释性事件"""
    # 合并该字段的关键词 + 通用关键词 + 新旧值本身
    keywords = list(GENERIC_EXPLANATION_KEYWORDS)
    keywords.extend(FIELD_KEYWORDS.get(field, []))

    for ch in range(chapter_start, chapter_end + 1):
        events = ctx.timeline_by_chapter.get(ch, [])
        for evt in events:
            event_text = evt.get("event", "") or ""
            location = evt.get("location", "") or ""
            evidence = evt.get("evidence", "") or ""
            combined = f"{event_text} {location} {evidence}"

            # 检查包含该角色
            chars_raw = evt.get("characters", "[]")
            try:
                event_chars = json.loads(chars_raw) if isinstance(chars_raw, str) else chars_raw
            except (json.JSONDecodeError, TypeError):
                event_chars = []

            if char_name not in event_chars and event_chars:
                continue  # 事件不涉及该角色，跳过

            # 检查新旧值是否出现在事件文本中
            if old_value and old_value in combined:
                return True
            if new_value and new_value in combined:
                return True
            # 检查关键词
            for kw in keywords:
                if kw in combined:
                    return True
    return False


# ── A1：状态变化异常检测 ─────────────────────


class StatusChangeAnomalyRule(BaseRule):
    """检测角色状态字段的变化是否有叙事记录支撑

    不判断变化是否合理（如"金丹→元婴"是否跨级），
    只判断"变了但附近没有解释性事件"。
    产出 review_needed，不产出 critical。
    """

    name = "StatusChangeAnomalyRule"
    description = "角色状态变化缺少解释性事件"
    contradiction_type = ContradictionType.STATUS_CHANGE_ANOMALY
    default_severity = Severity.WARNING
    default_issue_type = IssueType.REVIEW_NEEDED
    default_kind = IssueKind.REVIEW_NEEDED

    def check(self, ctx: RuleContext) -> list[RuleResult]:
        results: list[RuleResult] = []

        for char_name, history in ctx.status_by_char.items():
            # 展开为字段级变更序列
            prev_values: dict[str, tuple[str, int]] = {}  # field -> (value, chapter)

            for entry in history:
                chapter = entry.get("chapter", 0)
                new_status = entry.get("new", {})
                if not isinstance(new_status, dict):
                    continue

                for field in ["physical", "emotional", "social", "location"]:
                    config = FIELD_CONFIG.get(field, {})
                    if not config.get("enabled", False):
                        continue

                    new_val = (new_status.get(field, "") or "").strip()
                    if not new_val:
                        continue

                    if field in prev_values:
                        old_val, old_ch = prev_values[field]

                        # 过滤无意义变化
                        if _is_trivial_change(old_val, new_val):
                            prev_values[field] = (new_val, chapter)
                            continue

                        # 检查附近是否有解释
                        search_start = max(1, old_ch - 1)
                        search_end = min(chapter + 1, ctx.max_parsed_chapter)
                        explained = _has_explanation_in_events(
                            ctx, char_name, search_start, search_end,
                            field, old_val, new_val,
                        )

                        if not explained:
                            fp = make_fingerprint(
                                rule_name=self.name,
                                contradiction_type=self.contradiction_type.value,
                                chapter_start=old_ch,
                                chapter_end=chapter,
                                related_chars=[char_name],
                                detail_key=f"{field}:{old_val}→{new_val}",
                            )
                            results.append(RuleResult(
                                fingerprint=fp,
                                issue_type=self.default_issue_type,
                                kind=self.default_kind,
                                severity=config.get("default_severity", self.default_severity),
                                contradiction_type=self.contradiction_type,
                                rule_name=self.name,
                                description=(
                                    f"{char_name}第{old_ch}章「{old_val}」→"
                                    f"第{chapter}章「{new_val}」（{field}），"
                                    f"附近未找到解释性事件"
                                ),
                                detail={
                                    "character": char_name,
                                    "field": field,
                                    "old_value": old_val,
                                    "new_value": new_val,
                                    "from_chapter": old_ch,
                                    "to_chapter": chapter,
                                    "explanation_found": False,
                                },
                                chapter_range=(old_ch, chapter),
                                related_chars=[char_name],
                                explained=False,
                            ))

                    prev_values[field] = (new_val, chapter)

        return results


# ── A2：位置变化缺少旅程事件 ─────────────────


class LocationChangeWithoutTravelRule(BaseRule):
    """检测角色位置连续变化中缺少旅程事件

    不判断位置跳跃是否可能（如 天剑山→魔域），
    只判断"位置变了但没有记录旅途事件"。
    默认 warning。
    """

    name = "LocationChangeWithoutTravelRule"
    description = "位置变化缺少旅程事件"
    contradiction_type = ContradictionType.LOCATION_CHANGE_NO_TRAVEL
    default_severity = Severity.WARNING
    default_issue_type = IssueType.REVIEW_NEEDED
    default_kind = IssueKind.REVIEW_NEEDED

    def check(self, ctx: RuleContext) -> list[RuleResult]:
        results: list[RuleResult] = []

        for char_name, history in ctx.status_by_char.items():
            prev_location: str | None = None
            prev_chapter: int = 0

            for entry in history:
                chapter = entry.get("chapter", 0)
                new_status = entry.get("new", {})
                if not isinstance(new_status, dict):
                    continue
                location = (new_status.get("location", "") or "").strip()

                if not location:
                    prev_location = None
                    continue

                if prev_location is not None and location != prev_location:
                    has_travel = self._has_travel_event(
                        ctx, char_name, prev_chapter, chapter, location,
                    )
                    if not has_travel:
                        fp = make_fingerprint(
                            rule_name=self.name,
                            contradiction_type=self.contradiction_type.value,
                            chapter_start=prev_chapter,
                            chapter_end=chapter,
                            related_chars=[char_name],
                            detail_key=f"{prev_location}→{location}",
                        )
                        results.append(RuleResult(
                            fingerprint=fp,
                            issue_type=self.default_issue_type,
                            kind=self.default_kind,
                            severity=self.default_severity,
                            contradiction_type=self.contradiction_type,
                            rule_name=self.name,
                            description=(
                                f"{char_name}从第{prev_chapter}章「{prev_location}」→"
                                f"第{chapter}章「{location}」，缺少旅程事件"
                            ),
                            detail={
                                "character": char_name,
                                "from_chapter": prev_chapter,
                                "to_chapter": chapter,
                                "from_location": prev_location,
                                "to_location": location,
                            },
                            chapter_range=(prev_chapter, chapter),
                            related_chars=[char_name],
                        ))

                prev_location = location
                prev_chapter = chapter

        return results

    def _has_travel_event(
        self, ctx: RuleContext, char_name: str,
        from_chapter: int, to_chapter: int, target_location: str,
    ) -> bool:
        """检查 from_chapter 到 to_chapter 之间是否有涉及目的地的事件"""
        travel_kw = FIELD_KEYWORDS.get("location", [])
        for ch in range(from_chapter, to_chapter + 1):
            events = ctx.timeline_by_chapter.get(ch, [])
            for evt in events:
                evt_loc = evt.get("location", "") or ""
                if evt_loc == target_location:
                    return True
                evt_text = evt.get("event", "") or ""
                for kw in travel_kw:
                    if kw in evt_text:
                        chars_raw = evt.get("characters", "[]")
                        try:
                            event_chars = json.loads(chars_raw) if isinstance(chars_raw, str) else chars_raw
                        except (json.JSONDecodeError, TypeError):
                            event_chars = []
                        if char_name in event_chars or not event_chars:
                            return True
        return False
