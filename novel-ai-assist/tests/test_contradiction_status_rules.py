"""测试 StatusChangeAnomalyRule + LocationChangeWithoutTravelRule"""
import pytest
from core.contradiction.models import (
    ContradictionType, RuleContext, RuleResult,
)
from core.contradiction.status_rules import (
    StatusChangeAnomalyRule, LocationChangeWithoutTravelRule,
)


# ── 辅助：构建带 status_history 的 RuleContext ──

def make_ctx(
    status_by_char: dict | None = None,
    timeline_by_chapter: dict | None = None,
    **kwargs,
) -> RuleContext:
    return RuleContext(
        status_by_char=status_by_char or {},
        timeline_by_chapter=timeline_by_chapter or {},
        max_parsed_chapter=kwargs.get("max_parsed_chapter", 10),
    )


# ═══════════════════════════════════════════════
# StatusChangeAnomalyRule
# ═══════════════════════════════════════════════

class TestStatusChangeAnomalyRule:

    def test_detects_physical_change_without_explanation(self):
        """physical 变化但附近无解释事件 → 应产生结果"""
        ctx = make_ctx(
            status_by_char={
                "林婉儿": [
                    {"chapter": 1, "new": {"physical": "清醒"}},
                    {"chapter": 3, "new": {"physical": "醉酒"}},
                ],
            },
        )
        rule = StatusChangeAnomalyRule()
        results = rule.check(ctx)
        assert len(results) >= 1
        r = results[0]
        assert r.rule_name == "StatusChangeAnomalyRule"
        assert r.contradiction_type == ContradictionType.STATUS_CHANGE_ANOMALY
        assert r.severity.value == "warning"
        assert r.related_chars == ["林婉儿"]

    def test_not_detected_when_explanation_exists(self):
        """变化被事件解释 → 不报"""
        ctx = make_ctx(
            status_by_char={
                "林婉儿": [
                    {"chapter": 1, "new": {"physical": "清醒"}},
                    {"chapter": 2, "new": {"physical": "醉酒"}},
                ],
            },
            timeline_by_chapter={
                2: [{"event": "林婉儿喝下三坛烈酒后已醉", "characters": '["林婉儿"]'}],
            },
        )
        rule = StatusChangeAnomalyRule()
        results = rule.check(ctx)
        # "醉" 在事件中 → 有解释
        assert len(results) == 0

    def test_detects_social_change(self):
        """social 变化也应检测"""
        ctx = make_ctx(
            status_by_char={
                "赵无极": [
                    {"chapter": 1, "new": {"social": "弟子"}},
                    {"chapter": 5, "new": {"social": "掌门"}},
                ],
            },
        )
        rule = StatusChangeAnomalyRule()
        results = rule.check(ctx)
        assert any("赵无极" in r.related_chars and r.detail.get("field") == "social"
                   for r in results)

    def test_emotional_not_detected_by_default(self):
        """emotional 默认不检测"""
        ctx = make_ctx(
            status_by_char={
                "林婉儿": [
                    {"chapter": 1, "new": {"emotional": "平静"}},
                    {"chapter": 2, "new": {"emotional": "崩溃"}},
                ],
            },
        )
        rule = StatusChangeAnomalyRule()
        results = rule.check(ctx)
        emotional_results = [r for r in results
                             if r.detail.get("field") == "emotional"]
        assert len(emotional_results) == 0

    def test_multiple_fields_tracked_independently(self):
        """多个字段独立追踪变化"""
        ctx = make_ctx(
            status_by_char={
                "林婉儿": [
                    {"chapter": 1, "new": {"physical": "健康", "location": "天剑山"}},
                    {"chapter": 3, "new": {"physical": "健康", "location": "魔域"}},
                ],
            },
        )
        rule = StatusChangeAnomalyRule()
        results = rule.check(ctx)
        # physical 没变（健康→健康），location 变了
        physical_results = [r for r in results if r.detail.get("field") == "physical"]
        location_results = [r for r in results if r.detail.get("field") == "location"]
        assert len(physical_results) == 0
        assert len(location_results) >= 1

    def test_trivial_change_filtered(self):
        """细微变化（"有些疲惫"→"疲惫"）应被过滤"""
        ctx = make_ctx(
            status_by_char={
                "林婉儿": [
                    {"chapter": 1, "new": {"physical": "有些疲惫"}},
                    {"chapter": 2, "new": {"physical": "疲惫"}},
                ],
            },
        )
        rule = StatusChangeAnomalyRule()
        results = rule.check(ctx)
        assert len(results) == 0

    def test_empty_status_by_char(self):
        """空数据不报错"""
        ctx = make_ctx()
        rule = StatusChangeAnomalyRule()
        results = rule.check(ctx)
        assert results == []

    def test_fingerprint_stable(self):
        """相同输入产生相同 fingerprint"""
        ctx = make_ctx(
            status_by_char={
                "林婉儿": [
                    {"chapter": 1, "new": {"physical": "清醒"}},
                    {"chapter": 3, "new": {"physical": "醉酒"}},
                ],
            },
        )
        rule = StatusChangeAnomalyRule()
        results1 = rule.check(ctx)
        results2 = rule.check(ctx)
        assert len(results1) == len(results2)
        for r1, r2 in zip(results1, results2):
            assert r1.fingerprint == r2.fingerprint

    def test_explanation_from_evidence_field(self):
        """事件 evidence 字段也参与解释匹配"""
        ctx = make_ctx(
            status_by_char={
                "林婉儿": [
                    {"chapter": 1, "new": {"physical": "清醒"}},
                    {"chapter": 2, "new": {"physical": "醉酒"}},
                ],
            },
            timeline_by_chapter={
                2: [{"event": "林婉儿举杯痛饮", "characters": '["林婉儿"]', "evidence": "三杯后已醉"}],
            },
        )
        rule = StatusChangeAnomalyRule()
        results = rule.check(ctx)
        # "醉" 在 evidence 中 → 有解释
        assert len(results) == 0


# ═══════════════════════════════════════════════
# LocationChangeWithoutTravelRule
# ═══════════════════════════════════════════════

class TestLocationChangeWithoutTravelRule:

    def test_detects_location_change_without_travel(self):
        """位置变化无旅程事件 → 产生结果"""
        ctx = make_ctx(
            status_by_char={
                "林婉儿": [
                    {"chapter": 1, "new": {"location": "天剑山"}},
                    {"chapter": 4, "new": {"location": "魔域"}},
                ],
            },
        )
        rule = LocationChangeWithoutTravelRule()
        results = rule.check(ctx)
        assert len(results) >= 1

    def test_skipped_when_travel_event_exists(self):
        """有旅程事件时跳过"""
        ctx = make_ctx(
            status_by_char={
                "林婉儿": [
                    {"chapter": 1, "new": {"location": "天剑山"}},
                    {"chapter": 4, "new": {"location": "魔域"}},
                ],
            },
            timeline_by_chapter={
                3: [{"event": "林婉儿前往魔域", "characters": '["林婉儿"]', "location": "路上"}],
            },
        )
        rule = LocationChangeWithoutTravelRule()
        results = rule.check(ctx)
        assert len(results) == 0

    def test_no_change_skipped(self):
        """位置没变不报"""
        ctx = make_ctx(
            status_by_char={
                "林婉儿": [
                    {"chapter": 1, "new": {"location": "天剑山"}},
                    {"chapter": 5, "new": {"location": "天剑山"}},
                ],
            },
        )
        rule = LocationChangeWithoutTravelRule()
        results = rule.check(ctx)
        assert len(results) == 0

    def test_empty_data(self):
        """空数据不报错"""
        ctx = make_ctx()
        rule = LocationChangeWithoutTravelRule()
        results = rule.check(ctx)
        assert results == []

    def test_travel_event_at_destination(self):
        """事件地点等于新位置时跳过"""
        ctx = make_ctx(
            status_by_char={
                "林婉儿": [
                    {"chapter": 1, "new": {"location": "天剑山"}},
                    {"chapter": 4, "new": {"location": "魔域"}},
                ],
            },
            timeline_by_chapter={
                4: [{"event": "林婉儿抵达魔域", "characters": '["林婉儿"]', "location": "魔域"}],
            },
        )
        rule = LocationChangeWithoutTravelRule()
        results = rule.check(ctx)
        assert len(results) == 0
