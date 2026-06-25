"""矛盾检测引擎——调度所有规则、聚合结果、缓存支持"""

from __future__ import annotations

import hashlib
import json
import logging
import time
from typing import Optional

from core.knowledge import KnowledgeBase
from core.contradiction.loader import DataLoader
from core.contradiction.models import (
    ContradictionType,
    RuleContext,
    RuleResult,
    ScanSummary,
)
from core.contradiction.status_rules import (
    StatusChangeAnomalyRule,
    LocationChangeWithoutTravelRule,
)
from core.contradiction.timeline_rules import (
    NarrativeOrderAnomalyRule,
    SameTimeDifferentLocationRule,
    TimelineFlagRule,
)
from core.contradiction.relation_rules import (
    RelationChangeAnomalyRule,
    RelationConflictRule,
)
from core.contradiction.foreshadowing_rules import (
    ForeshadowingAgingRule,
    ForeshadowingIntegrityRule,
    HighConfidenceStaleRule,
)
from core.contradiction.integrity_rules import (
    AliasCollisionRule,
    ChapterIntegrityRule,
)

logger = logging.getLogger(__name__)

# 严重级别排序权重
_SEVERITY_ORDER = {"critical": 0, "warning": 1, "info": 2}


class ContradictionEngine:
    """矛盾检测引擎调度器

    职责：
    - 一次性加载数据（DataLoader）
    - 运行所有已注册的规则
    - 聚合结果 + 生成统计摘要
    - 支持结果分页、筛选、排序
    - 缓存最近一次扫描结果
    """

    def __init__(
        self,
        kb: KnowledgeBase,
        config: dict | None = None,
    ) -> None:
        self.kb = kb
        self.config = config or {}
        self._cache: Optional[ScanCache] = None

        # 注册规则
        self._rules = [
            # A 类：状态变化
            StatusChangeAnomalyRule(),
            LocationChangeWithoutTravelRule(),
            # B 类：时间线
            SameTimeDifferentLocationRule(),
            NarrativeOrderAnomalyRule(),
            TimelineFlagRule(),
            # C 类：关系
            RelationChangeAnomalyRule(),
            RelationConflictRule(),
            # D 类：伏笔
            ForeshadowingAgingRule(),
            HighConfidenceStaleRule(),
            ForeshadowingIntegrityRule(),
            # E 类：完整性
            AliasCollisionRule(),
            ChapterIntegrityRule(),
        ]

    # ── 扫描 ──────────────────────────────────────

    def scan_all(self) -> ScanResultData:
        """全量扫描所有规则

        返回最近一次扫描结果（如果缓存有效则使用缓存）。
        自动加载 dismissed fingerprints 标记结果状态。
        """
        start = time.perf_counter()

        # 1. 加载数据
        loader = DataLoader(self.kb, config=self.config)
        ctx = loader.load()

        # 2. 运行所有规则
        all_results: list[RuleResult] = []
        for rule in self._rules:
            try:
                results = rule.check(ctx)
                # 注入规则版本号到每条结果
                for r in results:
                    r.rule_version = rule.version
                all_results.extend(results)
            except Exception as e:
                logger.warning("规则 %s 执行异常: %s", rule.name, e)

        # 3. 加载审查记录并标记状态（同时检查版本变化）
        dismissed = self.kb.get_dismissed_fingerprints()
        reviews = self.kb.get_all_reviews()
        review_map: dict[str, dict] = {rev["fingerprint"]: rev for rev in reviews}
        for r in all_results:
            rev = review_map.get(r.fingerprint)
            if rev is None:
                continue
            if rev.get("rule_version") and rev["rule_version"] != r.rule_version:
                r.status = "open"
                self.kb.save_review(
                    fingerprint=r.fingerprint,
                    rule_name=r.rule_name,
                    rule_version=r.rule_version,
                    type_str=r.contradiction_type.value,
                    kind=r.kind.value,
                    severity=r.severity.value,
                    status="open",
                    reason=f"规则版本变更: {rev.get('rule_version', '?')}→{r.rule_version}",
                )
            else:
                r.status = rev["status"]

        # 4. 按严重级别排序
        all_results.sort(
            key=lambda r: (_SEVERITY_ORDER.get(r.severity.value, 99), r.score),
        )

        # 5. 构建统计摘要
        duration = (time.perf_counter() - start) * 1000

        by_sev: dict[str, int] = {}
        by_issue: dict[str, int] = {}
        by_type: dict[str, int] = {}
        open_count = 0
        dismissed_count = 0
        for r in all_results:
            by_sev[r.severity.value] = by_sev.get(r.severity.value, 0) + 1
            by_issue[r.issue_type.value] = by_issue.get(r.issue_type.value, 0) + 1
            by_type[r.contradiction_type.value] = by_type.get(r.contradiction_type.value, 0) + 1
            if r.status == "dismissed":
                dismissed_count += 1
            else:
                open_count += 1

        summary = ScanSummary(
            total=len(all_results),
            by_severity=by_sev,
            by_issue_type=by_issue,
            by_contradiction_type=by_type,
            open_count=open_count,
            dismissed_count=dismissed_count,
            duration_ms=round(duration, 2),
        )

        result = ScanResultData(summary=summary, results=all_results)
        self._cache = ScanCache(
            data=result,
            knowledge_digest=self._compute_knowledge_digest(),
            config_digest=self._compute_config_digest(),
        )
        return result

    # ── 分页查询 ──────────────────────────────────

    def get_paginated_results(
        self,
        page: int = 1,
        page_size: int = 20,
        type_filter: str | None = None,
        severity_filter: str | None = None,
        issue_type_filter: str | None = None,
        sort_by: str = "severity",
        sort_order: str = "desc",
        include_dismissed: bool = False,
    ) -> tuple[list[RuleResult], int, ScanSummary]:
        """对扫描结果进行分页排序"""
        cache = self._cache
        if not cache:
            self.scan_all()
            cache = self._cache

        results = cache.data.results

        # 过滤
        if not include_dismissed:
            results = [r for r in results if r.status != "dismissed"]
        if type_filter:
            results = [r for r in results if r.contradiction_type.value == type_filter]
        if severity_filter:
            results = [r for r in results if r.severity.value == severity_filter]
        if issue_type_filter:
            results = [r for r in results if r.issue_type.value == issue_type_filter]

        # 排序
        reverse = sort_order == "desc"
        if sort_by == "severity":
            results.sort(key=lambda r: _SEVERITY_ORDER.get(r.severity.value, 99), reverse=reverse)
        elif sort_by == "chapter":
            results.sort(key=lambda r: r.chapter_range[0], reverse=reverse)
        elif sort_by == "type":
            results.sort(key=lambda r: r.contradiction_type.value, reverse=reverse)
        elif sort_by == "score":
            results.sort(key=lambda r: r.score, reverse=reverse)

        total = len(results)
        offset = (page - 1) * page_size
        page_data = results[offset: offset + page_size]

        return page_data, total, cache.data.summary

    # ── 缓存失效 ──────────────────────────────────────

    def _compute_knowledge_digest(self) -> str:
        """计算知识库当前状态的 digest

        基于以下维度：
        - 已解析章节总数
        - 最大已解析章节号
        - 所有已解析章节的 file_hash + updated_at
        """
        max_ch = self.kb.get_max_parsed_chapter()
        total = self.kb.count_chapters(status="parsed")

        conn = self.kb.get_conn()
        rows = conn.execute(
            "SELECT file_hash, updated_at FROM chapters "
            "WHERE status = 'parsed' ORDER BY num"
        ).fetchall()

        parts = [str(max_ch), str(total)]
        for r in rows:
            parts.append(f"{r['file_hash']}:{r['updated_at']}")
        raw = "|".join(parts)
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    def _compute_config_digest(self) -> str:
        """计算配置 digest（配置变化时也触发重新扫描）"""
        raw = json.dumps(self.config, sort_keys=True)
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    def get_cached(self) -> Optional[ScanResultData]:
        """获取缓存，如果 digest 不匹配则自动失效返回 None"""
        if not self._cache:
            return None
        current_kd = self._compute_knowledge_digest()
        current_cd = self._compute_config_digest()
        if (self._cache.knowledge_digest != current_kd
                or self._cache.config_digest != current_cd):
            self._cache = None
            return None
        return self._cache.data

    def clear_cache(self) -> None:
        """强制清除缓存，下次 scan_all 会重新扫描"""
        self._cache = None


class ScanCache:
    """内部缓存，含 digest 用于失效判断"""
    def __init__(
        self,
        data: "ScanResultData",
        knowledge_digest: str,
        config_digest: str,
    ) -> None:
        self.data = data
        self.knowledge_digest = knowledge_digest
        self.config_digest = config_digest


class ScanResultData:
    """一次完整扫描的结果"""
    def __init__(self, summary: ScanSummary, results: list[RuleResult]) -> None:
        self.summary = summary
        self.results = results
