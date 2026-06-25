"""测试 RelationChangeAnomalyRule + RelationConflictRule"""
import pytest
from core.contradiction.models import ContradictionType, RuleContext
from core.contradiction.relation_rules import (
    RelationChangeAnomalyRule,
    RelationConflictRule,
)


def make_ctx(**kwargs) -> RuleContext:
    return RuleContext(**kwargs)


# ═══════════════════════════════════════════════
# RelationChangeAnomalyRule
# ═══════════════════════════════════════════════

class TestRelationChangeAnomalyRule:

    def test_detects_change_without_common_event(self):
        """关系变化无共同事件 → 报"""
        ctx = make_ctx(relations_by_pair={
            ("林婉儿", "顾长歌"): [
                {"char_a": "林婉儿", "char_b": "顾长歌",
                 "relation": "师徒", "chapter": 1},
                {"char_a": "林婉儿", "char_b": "顾长歌",
                 "relation": "敌对", "chapter": 10},
            ],
        })
        rule = RelationChangeAnomalyRule()
        results = rule.check(ctx)
        assert len(results) >= 1

    def test_skipped_with_common_event(self):
        """关系变化但中间有共同事件 → 不报"""
        ctx = make_ctx(
            relations_by_pair={
                ("林婉儿", "顾长歌"): [
                    {"char_a": "林婉儿", "char_b": "顾长歌",
                     "relation": "师徒", "chapter": 1},
                    {"char_a": "林婉儿", "char_b": "顾长歌",
                     "relation": "敌对", "chapter": 10},
                ],
            },
            timeline_by_chapter={
                5: [{"event": "师徒决裂", "characters": '["林婉儿","顾长歌"]'}],
            },
        )
        rule = RelationChangeAnomalyRule()
        results = rule.check(ctx)
        assert len(results) == 0

    def test_same_relation_skipped(self):
        """关系没变不报"""
        ctx = make_ctx(relations_by_pair={
            ("林婉儿", "顾长歌"): [
                {"char_a": "林婉儿", "char_b": "顾长歌",
                 "relation": "师徒", "chapter": 1},
                {"char_a": "林婉儿", "char_b": "顾长歌",
                 "relation": "师徒", "chapter": 5},
            ],
        })
        rule = RelationChangeAnomalyRule()
        assert rule.check(ctx) == []

    def test_single_entry_skipped(self):
        """只有一个关系记录跳过"""
        ctx = make_ctx(relations_by_pair={
            ("林婉儿", "顾长歌"): [
                {"char_a": "林婉儿", "char_b": "顾长歌",
                 "relation": "师徒", "chapter": 1},
            ],
        })
        rule = RelationChangeAnomalyRule()
        assert rule.check(ctx) == []

    def test_empty_data(self):
        """空数据不报错"""
        ctx = make_ctx()
        rule = RelationChangeAnomalyRule()
        assert rule.check(ctx) == []


# ═══════════════════════════════════════════════
# RelationConflictRule
# ═══════════════════════════════════════════════

class TestRelationConflictRule:

    def test_detects_multiple_relations_same_chapter(self):
        """同章同角色对多个不同关系 → 报"""
        ctx = make_ctx(relations_by_pair={
            ("林婉儿", "顾长歌"): [
                {"char_a": "林婉儿", "char_b": "顾长歌",
                 "relation": "师徒", "chapter": 5},
                {"char_a": "林婉儿", "char_b": "顾长歌",
                 "relation": "敌对", "chapter": 5},
            ],
        })
        rule = RelationConflictRule()
        results = rule.check(ctx)
        assert len(results) >= 1

    def test_same_relation_same_chapter_skipped(self):
        """同章但同关系不报"""
        ctx = make_ctx(relations_by_pair={
            ("林婉儿", "顾长歌"): [
                {"char_a": "林婉儿", "char_b": "顾长歌",
                 "relation": "师徒", "chapter": 5},
                {"char_a": "林婉儿", "char_b": "顾长歌",
                 "relation": "师徒", "chapter": 5},
            ],
        })
        rule = RelationConflictRule()
        assert rule.check(ctx) == []

    def test_different_chapters_skipped(self):
        """不同章不同关系不报"""
        ctx = make_ctx(relations_by_pair={
            ("林婉儿", "顾长歌"): [
                {"char_a": "林婉儿", "char_b": "顾长歌",
                 "relation": "师徒", "chapter": 1},
                {"char_a": "林婉儿", "char_b": "顾长歌",
                 "relation": "敌对", "chapter": 10},
            ],
        })
        rule = RelationConflictRule()
        assert rule.check(ctx) == []

    def test_empty_data(self):
        """空数据不报错"""
        ctx = make_ctx()
        rule = RelationConflictRule()
        assert rule.check(ctx) == []
