"""测试 SameTimeDifferentLocationRule + NarrativeOrderAnomalyRule + TimelineFlagRule"""
import pytest
from core.contradiction.models import ContradictionType, RuleContext
from core.contradiction.timeline_rules import (
    SameTimeDifferentLocationRule,
    NarrativeOrderAnomalyRule,
    TimelineFlagRule,
)


def make_ctx(**kwargs) -> RuleContext:
    return RuleContext(**kwargs)


# ═══════════════════════════════════════════════
# SameTimeDifferentLocationRule
# ═══════════════════════════════════════════════

class TestSameTimeDifferentLocationRule:

    def test_same_char_diff_location(self):
        """同角色同 story_time 不同地点 → 命中"""
        ctx = make_ctx(timeline_by_story_time={
            "子时": [
                {"chapter": 3, "story_time": "子时", "location": "天剑山",
                 "event": "林婉儿在天剑山", "characters": '["林婉儿"]'},
                {"chapter": 4, "story_time": "子时", "location": "魔域",
                 "event": "林婉儿在魔域", "characters": '["林婉儿"]'},
            ],
        })
        rule = SameTimeDifferentLocationRule()
        results = rule.check(ctx)
        assert len(results) >= 1
        assert results[0].severity.value == "critical"

    def test_same_char_same_location_skipped(self):
        """同角色同 story_time 同地点 → 不报"""
        ctx = make_ctx(timeline_by_story_time={
            "清晨": [
                {"chapter": 1, "story_time": "清晨", "location": "天剑山",
                 "event": "林婉儿练剑", "characters": '["林婉儿"]'},
                {"chapter": 2, "story_time": "清晨", "location": "天剑山",
                 "event": "顾长歌训话", "characters": '["顾长歌"]'},
            ],
        })
        rule = SameTimeDifferentLocationRule()
        results = rule.check(ctx)
        assert len(results) == 0

    def test_different_chars_diff_location_skipped(self):
        """不同角色不同位置 → 不报"""
        ctx = make_ctx(timeline_by_story_time={
            "午时": [
                {"chapter": 2, "story_time": "午时", "location": "天剑山",
                 "event": "林婉儿休息", "characters": '["林婉儿"]'},
                {"chapter": 2, "story_time": "午时", "location": "魔域",
                 "event": "赵无极练功", "characters": '["赵无极"]'},
            ],
        })
        rule = SameTimeDifferentLocationRule()
        results = rule.check(ctx)
        assert len(results) == 0

    def test_downgraded_with_keyword(self):
        """出现分身/幻境等关键词 → 降级为 warning"""
        ctx = make_ctx(timeline_by_story_time={
            "子时": [
                {"chapter": 3, "story_time": "子时", "location": "天剑山",
                 "event": "林婉儿施展分身术", "characters": '["林婉儿"]'},
                {"chapter": 3, "story_time": "子时", "location": "魔域",
                 "event": "林婉儿的化身", "characters": '["林婉儿"]'},
            ],
        })
        rule = SameTimeDifferentLocationRule()
        results = rule.check(ctx)
        assert len(results) >= 1
        assert results[0].severity.value == "warning"

    def test_empty_data(self):
        """空数据不报错"""
        ctx = make_ctx()
        rule = SameTimeDifferentLocationRule()
        assert rule.check(ctx) == []

    def test_single_entry_skipped(self):
        """只有一个事件时跳过"""
        ctx = make_ctx(timeline_by_story_time={
            "子时": [
                {"chapter": 3, "story_time": "子时", "location": "天剑山",
                 "event": "林婉儿单独行动", "characters": '["林婉儿"]'},
            ],
        })
        rule = SameTimeDifferentLocationRule()
        assert rule.check(ctx) == []


# ═══════════════════════════════════════════════
# NarrativeOrderAnomalyRule
# ═══════════════════════════════════════════════

class TestNarrativeOrderAnomalyRule:

    def test_detects_duplicate_order(self):
        """同章重复 narrative_order → 报"""
        ctx = make_ctx(timeline_by_chapter={
            3: [
                {"chapter": 3, "narrative_order": 1, "event": "事件A"},
                {"chapter": 3, "narrative_order": 1, "event": "事件B"},
            ],
        })
        rule = NarrativeOrderAnomalyRule()
        results = rule.check(ctx)
        assert len(results) >= 1
        assert results[0].detail.get("duplicates") == [1]

    def test_detects_gap(self):
        """narrative_order 不连续（1,3 缺 2）→ 报"""
        ctx = make_ctx(timeline_by_chapter={
            2: [
                {"chapter": 2, "narrative_order": 1, "event": "事件A"},
                {"chapter": 2, "narrative_order": 3, "event": "事件B"},
            ],
        })
        rule = NarrativeOrderAnomalyRule()
        results = rule.check(ctx)
        assert len(results) >= 1
        assert results[0].detail.get("gaps") == [2]

    def test_continuous_order_skipped(self):
        """narrative_order 连续 → 不报"""
        ctx = make_ctx(timeline_by_chapter={
            1: [
                {"chapter": 1, "narrative_order": 1, "event": "事件A"},
                {"chapter": 1, "narrative_order": 2, "event": "事件B"},
                {"chapter": 1, "narrative_order": 3, "event": "事件C"},
            ],
        })
        rule = NarrativeOrderAnomalyRule()
        assert rule.check(ctx) == []

    def test_empty_data(self):
        """空数据不报错"""
        ctx = make_ctx()
        rule = NarrativeOrderAnomalyRule()
        assert rule.check(ctx) == []

    def test_single_event_skipped(self):
        """只有一个事件时跳过"""
        ctx = make_ctx(timeline_by_chapter={
            1: [{"chapter": 1, "narrative_order": 1, "event": "唯一事件"}],
        })
        rule = NarrativeOrderAnomalyRule()
        assert rule.check(ctx) == []


# ═══════════════════════════════════════════════
# TimelineFlagRule
# ═══════════════════════════════════════════════

class TestTimelineFlagRule:

    def test_detects_anomaly_flag(self):
        """is_anomaly=1 的事件应被汇总"""
        ctx = make_ctx(timeline_events=[
            {"id": 1, "chapter": 3, "story_time": "子时",
             "event": "林婉儿同时出现在两地", "is_anomaly": 1,
             "characters": '["林婉儿"]'},
        ])
        rule = TimelineFlagRule()
        results = rule.check(ctx)
        assert len(results) == 1
        assert results[0].kind.value == "tracking"

    def test_skips_normal_events(self):
        """is_anomaly=0 的不要汇"""
        ctx = make_ctx(timeline_events=[
            {"id": 1, "chapter": 1, "event": "正常事件", "is_anomaly": 0},
        ])
        rule = TimelineFlagRule()
        assert rule.check(ctx) == []

    def test_empty_data(self):
        """空数据不报错"""
        ctx = make_ctx()
        rule = TimelineFlagRule()
        assert rule.check(ctx) == []
