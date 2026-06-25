"""测试 ForeshadowingAgingRule + HighConfidenceStaleRule + ForeshadowingIntegrityRule"""
import pytest
from core.contradiction.models import ContradictionType, RuleContext
from core.contradiction.foreshadowing_rules import (
    ForeshadowingAgingRule,
    HighConfidenceStaleRule,
    ForeshadowingIntegrityRule,
)


def make_ctx(**kwargs) -> RuleContext:
    return RuleContext(**kwargs)


# ═══════════════════════════════════════════════
# ForeshadowingAgingRule
# ═══════════════════════════════════════════════

class TestForeshadowingAgingRule:

    def test_detects_aging(self):
        """超 20 章未回收 → 报"""
        ctx = make_ctx(
            foreshadowings=[
                {"description": "神秘黑衣人", "laid_chapter": 1,
                 "status": "unrecovered", "related_chars": '["顾长歌"]'},
            ],
            max_parsed_chapter=30,
        )
        rule = ForeshadowingAgingRule(threshold=20)
        results = rule.check(ctx)
        assert len(results) >= 1
        assert results[0].kind.value == "tracking"

    def test_recovered_skipped(self):
        """已回收不报"""
        ctx = make_ctx(
            foreshadowings=[
                {"description": "神秘黑衣人", "laid_chapter": 1,
                 "status": "recovered", "related_chars": '[]',
                 "recovered_at": 15},
            ],
            max_parsed_chapter=30,
        )
        rule = ForeshadowingAgingRule()
        assert rule.check(ctx) == []

    def test_within_threshold_skipped(self):
        """未超阈值不报"""
        ctx = make_ctx(
            foreshadowings=[
                {"description": "小伏笔", "laid_chapter": 25,
                 "status": "unrecovered", "related_chars": '[]'},
            ],
            max_parsed_chapter=30,
        )
        rule = ForeshadowingAgingRule(threshold=20)
        assert rule.check(ctx) == []

    def test_empty_data(self):
        """空数据不报错"""
        ctx = make_ctx()
        rule = ForeshadowingAgingRule()
        assert rule.check(ctx) == []


# ═══════════════════════════════════════════════
# HighConfidenceStaleRule
# ═══════════════════════════════════════════════

class TestHighConfidenceStaleRule:

    def test_detects_high_confidence_stale(self):
        """高置信度超 10 章 → 报"""
        ctx = make_ctx(
            foreshadowings=[
                {"description": "关键伏笔", "laid_chapter": 1,
                 "status": "unrecovered", "related_chars": '[]',
                 "confidence": 0.9, "confidence_label": "high"},
            ],
            max_parsed_chapter=20,
        )
        rule = HighConfidenceStaleRule(threshold=10)
        results = rule.check(ctx)
        assert len(results) >= 1

    def test_low_confidence_skipped(self):
        """低置信度不报"""
        ctx = make_ctx(
            foreshadowings=[
                {"description": "可能伏笔", "laid_chapter": 1,
                 "status": "unrecovered", "related_chars": '[]',
                 "confidence": 0.3, "confidence_label": "low"},
            ],
            max_parsed_chapter=20,
        )
        rule = HighConfidenceStaleRule()
        assert rule.check(ctx) == []

    def test_empty_data(self):
        """空数据不报错"""
        ctx = make_ctx()
        rule = HighConfidenceStaleRule()
        assert rule.check(ctx) == []


# ═══════════════════════════════════════════════
# ForeshadowingIntegrityRule
# ═══════════════════════════════════════════════

class TestForeshadowingIntegrityRule:

    def test_recovered_at_before_laid(self):
        """recovered_at < laid_chapter → 报"""
        ctx = make_ctx(foreshadowings=[
            {"description": "伏笔", "laid_chapter": 10, "recovered_at": 5,
             "status": "recovered", "confidence": 0.8, "confidence_label": "high"},
        ])
        rule = ForeshadowingIntegrityRule()
        results = rule.check(ctx)
        assert len(results) >= 1

    def test_recovered_no_recovered_at(self):
        """status=recovered 但 recovered_at 为空 → 报"""
        ctx = make_ctx(foreshadowings=[
            {"description": "伏笔", "laid_chapter": 1, "recovered_at": None,
             "status": "recovered", "confidence": 0.8, "confidence_label": "high"},
        ])
        rule = ForeshadowingIntegrityRule()
        results = rule.check(ctx)
        assert len(results) >= 1

    def test_confidence_label_mismatch(self):
        """confidence_label=high 但 confidence<0.7 → 报"""
        ctx = make_ctx(foreshadowings=[
            {"description": "伏笔", "laid_chapter": 1, "recovered_at": None,
             "status": "unrecovered", "confidence": 0.5, "confidence_label": "high"},
        ])
        rule = ForeshadowingIntegrityRule()
        results = rule.check(ctx)
        assert len(results) >= 1

    def valid_foreshadowing_skipped(self):
        """正常的伏笔不报"""
        ctx = make_ctx(foreshadowings=[
            {"description": "伏笔", "laid_chapter": 1, "recovered_at": 15,
             "status": "recovered", "confidence": 0.9, "confidence_label": "high"},
        ])
        rule = ForeshadowingIntegrityRule()
        assert rule.check(ctx) == []

    def test_empty_data(self):
        """空数据不报错"""
        ctx = make_ctx()
        rule = ForeshadowingIntegrityRule()
        assert rule.check(ctx) == []
