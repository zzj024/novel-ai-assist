"""关系变化异常检测规则（C 类）

遵循原则：不判断关系变化是否"合理"，只判断是否缺少过渡记录。

包含：
- RelationChangeAnomalyRule: 角色对关系变化，检查中间是否有共同事件
- RelationConflictRule: 同章同角色对出现互斥关系
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


# ── C1：关系变化异常 ────────────────────────


class RelationChangeAnomalyRule(BaseRule):
    """检测同一对角色关系的变化是否缺少过渡事件

    师徒→敌对 本身不是矛盾，但如果中间章节没有
    同时包含两人的事件，则标记为 review_needed。
    """

    name = "RelationChangeAnomalyRule"
    description = "角色关系变化缺少过渡记录"
    contradiction_type = ContradictionType.RELATION_ABRUPT
    default_severity = Severity.WARNING
    default_issue_type = IssueType.REVIEW_NEEDED
    default_kind = IssueKind.REVIEW_NEEDED

    def check(self, ctx: RuleContext) -> list[RuleResult]:
        results: list[RuleResult] = []

        for pair, rel_list in ctx.relations_by_pair.items():
            if len(rel_list) < 2:
                continue

            # 按 chapter 排序
            sorted_rels = sorted(rel_list, key=lambda r: r.get("chapter", 0))
            char_a, char_b = pair

            for i in range(1, len(sorted_rels)):
                prev = sorted_rels[i - 1]
                curr = sorted_rels[i]
                prev_ch = prev.get("chapter", 0)
                curr_ch = curr.get("chapter", 0)
                prev_rel = prev.get("relation", "")
                curr_rel = curr.get("relation", "")

                if prev_rel == curr_rel:
                    continue

                # 检查中间章节是否有同时包含两人的事件
                has_common_event = self._has_common_event(
                    ctx, char_a, char_b, prev_ch, curr_ch,
                )

                if not has_common_event:
                    fp = make_fingerprint(
                        rule_name=self.name,
                        contradiction_type=self.contradiction_type.value,
                        chapter_start=prev_ch,
                        chapter_end=curr_ch,
                        related_chars=[char_a, char_b],
                        detail_key=f"{prev_rel}→{curr_rel}",
                    )
                    results.append(RuleResult(
                        fingerprint=fp,
                        issue_type=self.default_issue_type,
                        kind=self.default_kind,
                        severity=self.default_severity,
                        contradiction_type=self.contradiction_type,
                        rule_name=self.name,
                        description=(
                            f"{char_a}与{char_b}的关系从第{prev_ch}章「{prev_rel}」"
                            f"变为第{curr_ch}章「{curr_rel}」，中间无共同事件记录"
                        ),
                        detail={
                            "char_a": char_a,
                            "char_b": char_b,
                            "from_chapter": prev_ch,
                            "to_chapter": curr_ch,
                            "from_relation": prev_rel,
                            "to_relation": curr_rel,
                        },
                        chapter_range=(prev_ch, curr_ch),
                        related_chars=[char_a, char_b],
                    ))

        return results

    def _has_common_event(
        self, ctx: RuleContext, char_a: str, char_b: str,
        from_chapter: int, to_chapter: int,
    ) -> bool:
        """检查从 from_chapter 到 to_chapter 之间是否有同时包含两人的事件"""
        for ch in range(from_chapter, to_chapter + 1):
            events = ctx.timeline_by_chapter.get(ch, [])
            for evt in events:
                chars_raw = evt.get("characters", "[]")
                try:
                    chars = json.loads(chars_raw) if isinstance(chars_raw, str) else chars_raw
                except (json.JSONDecodeError, TypeError):
                    chars = []
                if char_a in chars and char_b in chars:
                    return True
        return False


# ── C2：关系冲突 ─────────────────────────────


class RelationConflictRule(BaseRule):
    """检测同一章节同一对角色出现多个不同关系

    注意：不是所有不同关系都算冲突（师徒+盟友可共存）。
    只报 warning，由作者判断是否真的矛盾。
    """

    name = "RelationConflictRule"
    description = "同一章节角色关系声明不一致"
    contradiction_type = ContradictionType.RELATION_CONFLICT
    default_severity = Severity.WARNING
    default_issue_type = IssueType.REVIEW_NEEDED
    default_kind = IssueKind.REVIEW_NEEDED

    def check(self, ctx: RuleContext) -> list[RuleResult]:
        results: list[RuleResult] = []

        for pair, rel_list in ctx.relations_by_pair.items():
            # 按 chapter 分组的 relation 值
            chapter_groups: dict[int, set[str]] = {}
            for rel in rel_list:
                ch = rel.get("chapter", 0)
                if ch:
                    chapter_groups.setdefault(ch, set()).add(rel.get("relation", ""))

            # 检查同一章是否有多个不同 relation
            for chapter, relations in chapter_groups.items():
                if len(relations) < 2:
                    continue

                char_a, char_b = pair
                fp = make_fingerprint(
                    rule_name=self.name,
                    contradiction_type=self.contradiction_type.value,
                    chapter_start=chapter,
                    chapter_end=chapter,
                    related_chars=[char_a, char_b],
                    detail_key=f"ch{chapter}:{','.join(sorted(relations))}",
                )
                results.append(RuleResult(
                    fingerprint=fp,
                    issue_type=self.default_issue_type,
                    kind=self.default_kind,
                    severity=self.default_severity,
                    contradiction_type=self.contradiction_type,
                    rule_name=self.name,
                    description=(
                        f"第{chapter}章{char_a}与{char_b}的关系存在多种声明："
                        f"{'、'.join(relations)}"
                    ),
                    detail={
                        "char_a": char_a,
                        "char_b": char_b,
                        "chapter": chapter,
                        "relations": list(relations),
                    },
                    chapter_range=(chapter, chapter),
                    related_chars=[char_a, char_b],
                ))

        return results
