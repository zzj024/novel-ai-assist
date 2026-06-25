"""时间线相关矛盾检测规则（B 类）

包含：
- SameTimeDifferentLocationRule: 同一角色同一 story_time 出现在不同地点
- NarrativeOrderAnomalyRule: 章内 narrative_order 不连续或重复
- TimelineFlagRule: 汇总 is_anomaly=1 的事件
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

# 位置矛盾降级关键词——出现这些时 critical→warning
LOCATION_EXCEPTION_KEYWORDS = [
    "分身", "幻境", "梦境", "传送", "远程", "通讯",
    "视频", "化身", "投影", "回忆", "想象",
]


# ── B1：同一时间不同地点 ─────────────────────


class SameTimeDifferentLocationRule(BaseRule):
    """检测同一角色、同一 story_time 出现在不同地点

    这是 Phase 4 最稳固的规则之一——不依赖任何领域知识，
    纯结构化数据对比。

    如果事件文本中出现分身/幻境/梦境等词则降级。
    """

    name = "SameTimeDifferentLocationRule"
    description = "同一角色同一时间出现在不同地点"
    contradiction_type = ContradictionType.SAME_TIME_DIFF_LOCATION
    default_severity = Severity.CRITICAL
    default_issue_type = IssueType.CONTRADICTION
    default_kind = IssueKind.CONTRADICTION

    def check(self, ctx: RuleContext) -> list[RuleResult]:
        results: list[RuleResult] = []

        for story_time, events in ctx.timeline_by_story_time.items():
            if not story_time or len(events) < 2:
                continue

            # 按角色分组：角色 → [(chapter, location, event)]
            char_groups: dict[str, list[dict[str, Any]]] = {}
            for evt in events:
                chars_raw = evt.get("characters", "[]")
                try:
                    chars = json.loads(chars_raw) if isinstance(chars_raw, str) else chars_raw
                except (json.JSONDecodeError, TypeError):
                    chars = []
                location = evt.get("location", "") or ""
                if not location:
                    continue
                for c in chars:
                    if not c:
                        continue
                    char_groups.setdefault(c, []).append({
                        "chapter": evt.get("chapter", 0),
                        "location": location,
                        "event": evt.get("event", "") or "",
                        "evidence": evt.get("evidence", "") or "",
                    })

            # 对每个角色，检查是否出现在不同地点
            for char_name, entries in char_groups.items():
                if len(entries) < 2:
                    continue
                locations = {e["location"] for e in entries}
                if len(locations) < 2:
                    continue

                # 检查是否有降级关键词
                has_exception = False
                combined_text = " ".join(
                    f'{e["event"]} {e["evidence"]}' for e in entries
                )
                for kw in LOCATION_EXCEPTION_KEYWORDS:
                    if kw in combined_text:
                        has_exception = True
                        break

                severity = Severity.WARNING if has_exception else self.default_severity
                issue_type = IssueType.REVIEW_NEEDED if has_exception else IssueType.CONTRADICTION
                kind = IssueKind.REVIEW_NEEDED if has_exception else IssueKind.CONTRADICTION

                chapters = sorted({e["chapter"] for e in entries})
                loc_list = sorted(locations)

                fp = make_fingerprint(
                    rule_name=self.name,
                    contradiction_type=self.contradiction_type.value,
                    chapter_start=chapters[0],
                    chapter_end=chapters[-1],
                    related_chars=[char_name],
                    detail_key=f"{story_time}:{','.join(loc_list)}",
                )
                results.append(RuleResult(
                    fingerprint=fp,
                    issue_type=issue_type,
                    kind=kind,
                    severity=severity,
                    contradiction_type=self.contradiction_type,
                    rule_name=self.name,
                    description=(
                        f"{story_time}「{story_time}」{char_name}同时出现在"
                        f"{' 和 '.join(loc_list)}"
                        + ("（有分身/幻境等解释）" if has_exception else "")
                    ),
                    detail={
                        "story_time": story_time,
                        "character": char_name,
                        "locations": list(locations),
                        "chapters": chapters,
                        "has_exception": has_exception,
                        "exception_keywords": [
                            kw for kw in LOCATION_EXCEPTION_KEYWORDS
                            if kw in combined_text
                        ] if has_exception else [],
                    },
                    chapter_range=(chapters[0], chapters[-1]),
                    related_chars=[char_name],
                ))

        return results


# ── B2：叙事顺序异常 ─────────────────────────


class NarrativeOrderAnomalyRule(BaseRule):
    """检测章节内 narrative_order 的连续性

    检查：
    - 是否存在重复的 order 值
    - 是否存在不连续（如 1,2,5 缺少 3,4）

    不报 critical——叙事顺序不连续在小说中可能有合理原因。
    """

    name = "NarrativeOrderAnomalyRule"
    description = "章内叙事顺序异常"
    contradiction_type = ContradictionType.NARRATIVE_ANOMALY
    default_severity = Severity.WARNING
    default_issue_type = IssueType.REVIEW_NEEDED
    default_kind = IssueKind.REVIEW_NEEDED

    def check(self, ctx: RuleContext) -> list[RuleResult]:
        results: list[RuleResult] = []

        for chapter, events in ctx.timeline_by_chapter.items():
            orders = []
            for evt in events:
                o = evt.get("narrative_order", 0)
                if o:
                    orders.append((o, evt))

            if len(orders) < 2:
                continue

            orders.sort(key=lambda x: x[0])
            order_values = [o for o, _ in orders]

            # 检查重复
            seen: set[int] = set()
            duplicates: list[int] = []
            for o in order_values:
                if o in seen:
                    duplicates.append(o)
                seen.add(o)

            # 检查不连续（从 1 开始）
            gaps: list[int] = []
            if order_values[0] == 1:
                for i in range(1, len(order_values)):
                    expected = order_values[i - 1] + 1
                    if order_values[i] > expected:
                        gaps.extend(range(expected, order_values[i]))

            if duplicates or gaps:
                fp = make_fingerprint(
                    rule_name=self.name,
                    contradiction_type=self.contradiction_type.value,
                    chapter_start=chapter,
                    chapter_end=chapter,
                    related_chars=[],
                    detail_key=f"ch{chapter}:{','.join(map(str, order_values))}",
                )
                results.append(RuleResult(
                    fingerprint=fp,
                    issue_type=self.default_issue_type,
                    kind=self.default_kind,
                    severity=self.default_severity,
                    contradiction_type=self.contradiction_type,
                    rule_name=self.name,
                    description=(
                        f"第{chapter}章叙事顺序异常"
                        + (f"——重复: {duplicates}" if duplicates else "")
                        + (f"——缺失: {gaps}" if gaps else "")
                    ),
                    detail={
                        "chapter": chapter,
                        "order_values": order_values,
                        "duplicates": duplicates,
                        "gaps": gaps,
                    },
                    chapter_range=(chapter, chapter),
                ))

        return results


# ── B3：时间线标记汇总 ────────────────────────


class TimelineFlagRule(BaseRule):
    """汇总 is_anomaly=1 的时间线事件

    不执行新检测，只汇总 LLM 已经标注的异常事件。
    属于 tracking 类型。
    """

    name = "TimelineFlagRule"
    description = "LLM 标记的时间线异常汇总"
    contradiction_type = ContradictionType.TIMELINE_FLAG
    default_severity = Severity.WARNING
    default_issue_type = IssueType.TRACKING
    default_kind = IssueKind.TRACKING

    def check(self, ctx: RuleContext) -> list[RuleResult]:
        results: list[RuleResult] = []

        for evt in ctx.timeline_events:
            if not evt.get("is_anomaly"):
                continue

            chapter = evt.get("chapter", 0)
            event_text = evt.get("event", "") or ""
            chars_raw = evt.get("characters", "[]")
            try:
                chars = json.loads(chars_raw) if isinstance(chars_raw, str) else chars_raw
            except (json.JSONDecodeError, TypeError):
                chars = []

            fp = make_fingerprint(
                rule_name=self.name,
                contradiction_type=self.contradiction_type.value,
                chapter_start=chapter,
                chapter_end=chapter,
                related_chars=chars if isinstance(chars, list) else [],
                detail_key=f"ch{chapter}:{event_text[:50]}",
            )
            results.append(RuleResult(
                fingerprint=fp,
                issue_type=self.default_issue_type,
                kind=self.default_kind,
                severity=self.default_severity,
                contradiction_type=self.contradiction_type,
                rule_name=self.name,
                description=f"第{chapter}章时间线异常：{event_text[:100]}",
                detail={
                    "chapter": chapter,
                    "event": event_text,
                    "story_time": evt.get("story_time", ""),
                },
                chapter_range=(chapter, chapter),
                related_chars=chars if isinstance(chars, list) else [],
            ))

        return results
