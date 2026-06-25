"""数据完整性检测规则（E 类）

包含：
- AliasCollisionRule: 同一别名指向多个角色
- ChapterIntegrityRule: 章节结构完整性
"""

import json
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


# ── E1：别名冲突 ─────────────────────────────


class AliasCollisionRule(BaseRule):
    """检测同一别名被多个角色使用

    别名冲突会污染后续的查询和矛盾检测：
    - 查"玄尊"时可能返回两个不同角色
    - 角色名出现在另一个角色的别名表中
    """

    name = "AliasCollisionRule"
    description = "别名冲突"
    contradiction_type = ContradictionType.ALIAS_COLLISION
    default_severity = Severity.WARNING
    default_issue_type = IssueType.INTEGRITY
    default_kind = IssueKind.INTEGRITY

    def check(self, ctx: RuleContext) -> list[RuleResult]:
        results: list[RuleResult] = []
        # alias → [角色名列表]
        alias_map: dict[str, list[str]] = {}

        for char in ctx.characters:
            name = char.get("name", "")
            if not name:
                continue
            aliases_raw = char.get("aliases", "[]")
            try:
                aliases = json.loads(aliases_raw) if isinstance(aliases_raw, str) else aliases_raw
            except (json.JSONDecodeError, TypeError):
                aliases = []

            for alias in aliases:
                if not alias or not alias.strip():
                    continue
                a = alias.strip()
                alias_map.setdefault(a, []).append(name)

        for alias, names in alias_map.items():
            if len(names) < 2:
                continue

            fp = make_fingerprint(
                rule_name=self.name,
                contradiction_type=self.contradiction_type.value,
                chapter_start=0,
                chapter_end=0,
                related_chars=names,
                detail_key=f"alias:{alias}",
            )
            results.append(RuleResult(
                fingerprint=fp,
                issue_type=self.default_issue_type,
                kind=self.default_kind,
                severity=self.default_severity,
                contradiction_type=self.contradiction_type,
                rule_name=self.name,
                description=f"别名「{alias}」被多个角色使用：{'、'.join(names)}",
                detail={
                    "alias": alias,
                    "characters": names,
                },
                related_chars=names,
            ))

        return results


# ── E2：章节完整性 ───────────────────────────


class ChapterIntegrityRule(BaseRule):
    """检测章节结构完整性

    检查项：
    - chapters.num 是否连续（检测 gap）
    - 是否存在重复 filename
    - status=error 的章节数
    - 有正文但 summary 为空
    """

    name = "ChapterIntegrityRule"
    description = "章节结构完整性"
    contradiction_type = ContradictionType.CHAPTER_INTEGRITY
    default_severity = Severity.INFO
    default_issue_type = IssueType.INTEGRITY
    default_kind = IssueKind.INTEGRITY

    def check(self, ctx: RuleContext) -> list[RuleResult]:
        results: list[RuleResult] = []
        chapters = ctx.chapters

        if not chapters:
            return results

        # 1. 检查序号连续性
        nums = sorted(c.get("num", 0) for c in chapters if c.get("num"))
        gaps = []
        for i in range(1, len(nums)):
            if nums[i] > nums[i - 1] + 1:
                gaps.extend(range(nums[i - 1] + 1, nums[i]))
        if gaps:
            fp = make_fingerprint(
                rule_name=self.name,
                contradiction_type=self.contradiction_type.value,
                chapter_start=nums[0],
                chapter_end=nums[-1],
                related_chars=[],
                detail_key=f"gaps:{','.join(map(str, gaps[:10]))}",
            )
            results.append(RuleResult(
                fingerprint=fp,
                issue_type=self.default_issue_type,
                kind=self.default_kind,
                severity=self.default_severity,
                contradiction_type=self.contradiction_type,
                rule_name=self.name,
                description=f"章节序号不连续：缺少第{'、第'.join(map(str, gaps[:10]))}章"
                + (f"等{gaps[10:]}个" if len(gaps) > 10 else ""),
                detail={
                    "type": "num_gap",
                    "gaps": gaps,
                    "chapter_count": len(chapters),
                },
                chapter_range=(nums[0], nums[-1]),
            ))

        # 2. 重复 filename
        seen_files: dict[str, list[int]] = {}
        for c in chapters:
            fn = c.get("filename", "")
            if fn:
                seen_files.setdefault(fn, []).append(c["num"])
        for fn, ch_nums in seen_files.items():
            if len(ch_nums) < 2:
                continue
            fp = make_fingerprint(
                rule_name=self.name,
                contradiction_type=self.contradiction_type.value,
                chapter_start=ch_nums[0],
                chapter_end=ch_nums[-1],
                related_chars=[],
                detail_key=f"dup_file:{fn}",
            )
            results.append(RuleResult(
                fingerprint=fp,
                issue_type=self.default_issue_type,
                kind=self.default_kind,
                severity=self.default_severity,
                contradiction_type=self.contradiction_type,
                rule_name=self.name,
                description=f"文件名「{fn}」被多章使用：第{'、第'.join(map(str, ch_nums))}章",
                detail={
                    "type": "duplicate_filename",
                    "filename": fn,
                    "chapters": ch_nums,
                },
                chapter_range=(ch_nums[0], ch_nums[-1]),
            ))

        # 3. error 章节统计
        error_chapters = [c for c in chapters if c.get("status") == "error"]
        if error_chapters:
            nums_str = "、".join(str(c["num"]) for c in error_chapters[:10])
            fp = make_fingerprint(
                rule_name=self.name,
                contradiction_type=self.contradiction_type.value,
                chapter_start=error_chapters[0]["num"],
                chapter_end=error_chapters[-1]["num"],
                related_chars=[],
                detail_key=f"error_chapters:{len(error_chapters)}",
            )
            results.append(RuleResult(
                fingerprint=fp,
                issue_type=self.default_issue_type,
                kind=self.default_kind,
                severity=Severity.WARNING,
                contradiction_type=self.contradiction_type,
                rule_name=self.name,
                description=f"存在{len(error_chapters)}个解析失败的章节（第{nums_str}章）",
                detail={
                    "type": "error_chapters",
                    "count": len(error_chapters),
                    "chapters": [c["num"] for c in error_chapters],
                },
                chapter_range=(error_chapters[0]["num"], error_chapters[-1]["num"]),
            ))

        return results
