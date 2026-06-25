"""伏笔相关检测规则（D 类）

包含：
- ForeshadowingAgingRule: 未回收伏笔超过配置章数
- HighConfidenceStaleRule: 高置信度伏笔长期未处理
- ForeshadowingIntegrityRule: 伏笔字段自相矛盾
"""

import logging

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

DEFAULT_AGING_THRESHOLD = 20
DEFAULT_STALE_THRESHOLD = 10


# ── D1：超龄未回收伏笔 ──────────────────────


class ForeshadowingAgingRule(BaseRule):
    """检测超过 N 章仍未回收的伏笔"""

    name = "ForeshadowingAgingRule"
    description = "伏笔超龄未回收"
    contradiction_type = ContradictionType.FORESHADOWING_AGING
    default_severity = Severity.WARNING
    default_issue_type = IssueType.TRACKING
    default_kind = IssueKind.TRACKING

    def __init__(self, threshold: int = DEFAULT_AGING_THRESHOLD):
        super().__init__()
        self.threshold = threshold

    def check(self, ctx: RuleContext) -> list[RuleResult]:
        results: list[RuleResult] = []
        max_ch = ctx.max_parsed_chapter

        for fore in ctx.foreshadowings:
            if fore.get("status") != "unrecovered":
                continue
            laid = fore.get("laid_chapter", 0)
            gap = max_ch - laid
            if gap < self.threshold:
                continue

            related = fore.get("related_chars", "[]")
            import json
            try:
                chars = json.loads(related) if isinstance(related, str) else related
            except (json.JSONDecodeError, TypeError):
                chars = []

            fp = make_fingerprint(
                rule_name=self.name,
                contradiction_type=self.contradiction_type.value,
                chapter_start=laid,
                chapter_end=max_ch,
                related_chars=chars if isinstance(chars, list) else [],
                detail_key=f"laid:{laid},gap:{gap}",
            )
            results.append(RuleResult(
                fingerprint=fp,
                issue_type=self.default_issue_type,
                kind=self.default_kind,
                severity=self.default_severity,
                contradiction_type=self.contradiction_type,
                rule_name=self.name,
                description=(
                    f"伏笔「{fore.get('description', '')}」"
                    f"于第{laid}章埋设，已过{gap}章未回收"
                ),
                detail={
                    "description": fore.get("description", ""),
                    "laid_chapter": laid,
                    "current_chapter": max_ch,
                    "gap": gap,
                    "threshold": self.threshold,
                },
                chapter_range=(laid, max_ch),
                related_chars=chars if isinstance(chars, list) else [],
            ))

        return results


# ── D2：高置信度伏笔停滞 ─────────────────────


class HighConfidenceStaleRule(BaseRule):
    """高置信度伏笔超过 N 章未处理

    条件：confidence_label=high 或 confidence>=0.8 且未回收
    """

    name = "HighConfidenceStaleRule"
    description = "高置信度伏笔长期未处理"
    contradiction_type = ContradictionType.FORESHADOWING_STALE
    default_severity = Severity.WARNING
    default_issue_type = IssueType.TRACKING
    default_kind = IssueKind.TRACKING

    def __init__(self, threshold: int = DEFAULT_STALE_THRESHOLD):
        super().__init__()
        self.threshold = threshold

    def check(self, ctx: RuleContext) -> list[RuleResult]:
        results: list[RuleResult] = []
        max_ch = ctx.max_parsed_chapter

        for fore in ctx.foreshadowings:
            if fore.get("status") != "unrecovered":
                continue
            label = fore.get("confidence_label", "")
            conf = fore.get("confidence", 0.0)
            if label != "high" and conf < 0.8:
                continue

            laid = fore.get("laid_chapter", 0)
            gap = max_ch - laid
            if gap < self.threshold:
                continue

            related = fore.get("related_chars", "[]")
            import json
            try:
                chars = json.loads(related) if isinstance(related, str) else related
            except (json.JSONDecodeError, TypeError):
                chars = []

            fp = make_fingerprint(
                rule_name=self.name,
                contradiction_type=self.contradiction_type.value,
                chapter_start=laid,
                chapter_end=max_ch,
                related_chars=chars if isinstance(chars, list) else [],
                detail_key=f"laid:{laid},conf:{conf}",
            )
            results.append(RuleResult(
                fingerprint=fp,
                issue_type=self.default_issue_type,
                kind=self.default_kind,
                severity=self.default_severity,
                contradiction_type=self.contradiction_type,
                rule_name=self.name,
                description=(
                    f"高置信度伏笔「{fore.get('description', '')}」"
                    f"于第{laid}章埋设，已过{gap}章未处理"
                ),
                detail={
                    "description": fore.get("description", ""),
                    "laid_chapter": laid,
                    "current_chapter": max_ch,
                    "gap": gap,
                    "confidence": conf,
                    "confidence_label": label,
                },
                chapter_range=(laid, max_ch),
                related_chars=chars if isinstance(chars, list) else [],
            ))

        return results


# ── D3：伏笔字段完整性 ───────────────────────


class ForeshadowingIntegrityRule(BaseRule):
    """检测伏笔自身字段的矛盾

    检查项：
    - recovered_at < laid_chapter（回收早于埋设）
    - status=recovered 但 recovered_at 为空
    - status=unrecovered 但 recovered_at 有值
    - confidence_label=high 但 confidence < 0.7
    """

    name = "ForeshadowingIntegrityRule"
    description = "伏笔字段自相矛盾"
    contradiction_type = ContradictionType.FORESHADOWING_INTEGRITY
    default_severity = Severity.WARNING
    default_issue_type = IssueType.CONTRADICTION
    default_kind = IssueKind.CONTRADICTION

    def check(self, ctx: RuleContext) -> list[RuleResult]:
        results: list[RuleResult] = []

        for fore in ctx.foreshadowings:
            laid = fore.get("laid_chapter", 0)
            recovered = fore.get("recovered_at")
            status = fore.get("status", "")
            label = fore.get("confidence_label", "")
            conf = fore.get("confidence", 0.0)
            desc = fore.get("description", "")

            issues: list[str] = []

            if recovered is not None and laid and recovered < laid:
                issues.append("recovered_at < laid_chapter")
            if status == "recovered" and recovered is None:
                issues.append("status=recovered 但 recovered_at 为空")
            if status == "unrecovered" and recovered is not None:
                issues.append("status=unrecovered 但 recovered_at 有值")
            if label == "high" and conf < 0.7:
                issues.append("confidence_label=high 但 confidence<0.7")

            if not issues:
                continue

            related = fore.get("related_chars", "[]")
            import json
            try:
                chars = json.loads(related) if isinstance(related, str) else related
            except (json.JSONDecodeError, TypeError):
                chars = []

            fp = make_fingerprint(
                rule_name=self.name,
                contradiction_type=self.contradiction_type.value,
                chapter_start=laid or 0,
                chapter_end=recovered or laid or 0,
                related_chars=chars if isinstance(chars, list) else [],
                detail_key=f"{desc[:30]}:{';'.join(issues)}",
            )
            results.append(RuleResult(
                fingerprint=fp,
                issue_type=self.default_issue_type,
                kind=self.default_kind,
                severity=self.default_severity,
                contradiction_type=self.contradiction_type,
                rule_name=self.name,
                description=(
                    f"伏笔「{desc}」字段矛盾：{'；'.join(issues)}"
                ),
                detail={
                    "description": desc,
                    "laid_chapter": laid,
                    "recovered_at": recovered,
                    "status": status,
                    "confidence": conf,
                    "confidence_label": label,
                    "issues": issues,
                },
                chapter_range=(laid or 0, recovered or laid or 0),
                related_chars=chars if isinstance(chars, list) else [],
            ))

        return results
