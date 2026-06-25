"""测试 AliasCollisionRule + ChapterIntegrityRule"""
import pytest
from core.contradiction.models import ContradictionType, RuleContext
from core.contradiction.integrity_rules import (
    AliasCollisionRule,
    ChapterIntegrityRule,
)


def make_ctx(**kwargs) -> RuleContext:
    return RuleContext(**kwargs)


# ═══════════════════════════════════════════════
# AliasCollisionRule
# ═══════════════════════════════════════════════

class TestAliasCollisionRule:

    def test_detects_alias_collision(self):
        """同一别名被多个角色使用 → 报"""
        ctx = make_ctx(characters=[
            {"name": "萧玄", "aliases": '["玄尊", "师父"]'},
            {"name": "陆玄", "aliases": '["玄尊"]'},
        ])
        rule = AliasCollisionRule()
        results = rule.check(ctx)
        assert len(results) >= 1
        assert results[0].kind.value == "integrity"

    def test_unique_alias_skipped(self):
        """别名唯一不报"""
        ctx = make_ctx(characters=[
            {"name": "萧玄", "aliases": '["玄尊"]'},
            {"name": "陆玄", "aliases": '["玄师"]'},
        ])
        rule = AliasCollisionRule()
        assert rule.check(ctx) == []

    def test_empty_data(self):
        """空数据不报错"""
        ctx = make_ctx()
        rule = AliasCollisionRule()
        assert rule.check(ctx) == []

    def test_no_aliases_skipped(self):
        """没有别名的角色不报"""
        ctx = make_ctx(characters=[
            {"name": "林婉儿", "aliases": "[]"},
            {"name": "顾长歌", "aliases": "[]"},
        ])
        rule = AliasCollisionRule()
        assert rule.check(ctx) == []

    def test_name_in_other_alias_skipped(self):
        """角色名出现在别名中不算冲突（此规则只检测别名 vs 别名）"""
        ctx = make_ctx(characters=[
            {"name": "萧玄", "aliases": '["萧玄"]'},
        ])
        rule = AliasCollisionRule()
        assert rule.check(ctx) == []


# ═══════════════════════════════════════════════
# ChapterIntegrityRule
# ═══════════════════════════════════════════════

class TestChapterIntegrityRule:

    def test_detects_num_gap(self):
        """章节序号不连续 → 报"""
        ctx = make_ctx(chapters=[
            {"num": 1, "filename": "第1章.md", "status": "parsed"},
            {"num": 2, "filename": "第2章.md", "status": "parsed"},
            {"num": 5, "filename": "第5章.md", "status": "parsed"},
        ])
        rule = ChapterIntegrityRule()
        results = rule.check(ctx)
        assert any(r.detail.get("type") == "num_gap" for r in results)

    def test_detects_duplicate_filename(self):
        """重复文件名 → 报"""
        ctx = make_ctx(chapters=[
            {"num": 1, "filename": "第1章.md", "status": "parsed"},
            {"num": 2, "filename": "第1章.md", "status": "parsed"},
        ])
        rule = ChapterIntegrityRule()
        results = rule.check(ctx)
        assert any(r.detail.get("type") == "duplicate_filename" for r in results)

    def test_detects_error_chapters(self):
        """error 章节 → 报 warning"""
        ctx = make_ctx(chapters=[
            {"num": 1, "filename": "第1章.md", "status": "parsed"},
            {"num": 2, "filename": "第2章.md", "status": "error"},
            {"num": 3, "filename": "第3章.md", "status": "error"},
        ])
        rule = ChapterIntegrityRule()
        results = rule.check(ctx)
        error_results = [r for r in results if r.detail.get("type") == "error_chapters"]
        assert len(error_results) == 1
        assert error_results[0].severity.value == "warning"

    def test_continuous_skipped(self):
        """连续且无错误 → 不报"""
        ctx = make_ctx(chapters=[
            {"num": 1, "filename": "第1章.md", "status": "parsed"},
            {"num": 2, "filename": "第2章.md", "status": "parsed"},
            {"num": 3, "filename": "第3章.md", "status": "parsed"},
        ])
        rule = ChapterIntegrityRule()
        assert rule.check(ctx) == []

    def test_empty_data(self):
        """空数据不报错"""
        ctx = make_ctx()
        rule = ChapterIntegrityRule()
        assert rule.check(ctx) == []
