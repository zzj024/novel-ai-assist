"""Phase 4 Step 1：数据模型 + fingerprint 单元测试"""
import pytest
from core.contradiction.models import (
    Severity,
    IssueType,
    IssueKind,
    ContradictionType,
    RuleResult,
    ScanSummary,
    BaseRule,
    RuleContext,
)
from core.contradiction.fingerprint import make_fingerprint


class TestSeverityEnum:
    def test_has_three_levels(self):
        assert Severity.CRITICAL.value == "critical"
        assert Severity.WARNING.value == "warning"
        assert Severity.INFO.value == "info"

    def test_ordering(self):
        assert Severity.CRITICAL != Severity.WARNING


class TestIssueTypeEnum:
    def test_has_four_types(self):
        assert IssueType.CONTRADICTION.value == "contradiction"
        assert IssueType.REVIEW_NEEDED.value == "review_needed"
        assert IssueType.TRACKING.value == "tracking"
        assert IssueType.INTEGRITY.value == "integrity"


class TestIssueKindEnum:
    def test_has_four_kinds(self):
        assert IssueKind.CONTRADICTION.value == "contradiction"
        assert IssueKind.REVIEW_NEEDED.value == "review_needed"
        assert IssueKind.TRACKING.value == "tracking"
        assert IssueKind.INTEGRITY.value == "integrity"


class TestContradictionTypeEnum:
    def test_has_12_types(self):
        assert len(ContradictionType) == 12

    def test_status_change_anomaly_exists(self):
        assert ContradictionType.STATUS_CHANGE_ANOMALY.value == "status_change_anomaly"


class TestRuleResult:
    def test_minimal_creation(self):
        r = RuleResult(
            fingerprint="abc123",
            issue_type=IssueType.CONTRADICTION,
            kind=IssueKind.CONTRADICTION,
            severity=Severity.CRITICAL,
            contradiction_type=ContradictionType.STATUS_CHANGE_ANOMALY,
            rule_name="TestRule",
            description="测试矛盾",
        )
        assert r.fingerprint == "abc123"
        assert r.issue_type == IssueType.CONTRADICTION
        assert r.kind == IssueKind.CONTRADICTION
        assert r.severity == Severity.CRITICAL
        assert r.contradiction_type == ContradictionType.STATUS_CHANGE_ANOMALY
        assert r.rule_name == "TestRule"
        assert r.description == "测试矛盾"

    def test_default_values(self):
        r = RuleResult(
            fingerprint="def456",
            issue_type=IssueType.REVIEW_NEEDED,
            kind=IssueKind.REVIEW_NEEDED,
            severity=Severity.WARNING,
            contradiction_type=ContradictionType.LOCATION_CHANGE_NO_TRAVEL,
            rule_name="TestRule",
            description="测试",
        )
        assert r.score == 1.0
        assert r.evidence == []
        assert r.chapter_range == (0, 0)
        assert r.related_chars == []
        assert r.status == "open"
        assert r.explained is False
        assert r.detail == {}

    def test_with_all_fields(self):
        r = RuleResult(
            fingerprint="ghi789",
            issue_type=IssueType.TRACKING,
            kind=IssueKind.TRACKING,
            severity=Severity.INFO,
            contradiction_type=ContradictionType.FORESHADOWING_AGING,
            rule_name="ForeshadowingAgingRule",
            description="伏笔超20章未回收",
            detail={"threshold": 20, "actual_gap": 25},
            evidence=["第1章埋下伏笔"],
            chapter_range=(1, 26),
            related_chars=["林婉儿"],
            score=0.85,
            status="open",
            explained=False,
        )
        assert r.chapter_range == (1, 26)
        assert r.related_chars == ["林婉儿"]
        assert r.detail["threshold"] == 20


class TestScanSummary:
    def test_empty_summary(self):
        s = ScanSummary()
        assert s.total == 0
        assert s.by_severity == {}
        assert s.open_count == 0
        assert s.dismissed_count == 0
        assert s.duration_ms == 0.0


class TestRuleContext:
    def test_empty_context(self):
        ctx = RuleContext()
        assert ctx.characters == []
        assert ctx.max_parsed_chapter == 0

    def test_with_data(self):
        ctx = RuleContext(
            characters=[{"name": "林婉儿"}],
            max_parsed_chapter=10,
            config={"threshold": 20},
        )
        assert len(ctx.characters) == 1
        assert ctx.max_parsed_chapter == 10
        assert ctx.config["threshold"] == 20


class TestBaseRule:
    def test_interface(self):
        """BaseRule 不可直接实例化（抽象类）"""
        with pytest.raises(TypeError):
            BaseRule()  # abstract methods can't be instantiated

    def test_concrete_rule_must_implement_check(self):
        """子类不实现 check() 会报 TypeError"""
        class Incomplete(BaseRule):
            pass

        with pytest.raises(TypeError):
            Incomplete()


class TestMakeFingerprint:
    def test_returns_string(self):
        fp = make_fingerprint("TestRule", "status_jump", 1, 3, ["林婉儿"], "筑基→金丹")
        assert isinstance(fp, str)
        assert len(fp) == 64  # SHA256 hex

    def test_same_input_same_fingerprint(self):
        fp1 = make_fingerprint("TestRule", "status_jump", 1, 3, ["林婉儿"], "筑基→金丹")
        fp2 = make_fingerprint("TestRule", "status_jump", 1, 3, ["林婉儿"], "筑基→金丹")
        assert fp1 == fp2

    def test_different_input_different_fingerprint(self):
        fp1 = make_fingerprint("TestRule", "status_jump", 1, 3, ["林婉儿"], "筑基→金丹")
        fp2 = make_fingerprint("TestRule", "status_jump", 1, 5, ["林婉儿"], "筑基→金丹")
        assert fp1 != fp2

    def test_sorted_chars_stable(self):
        """角色顺序不影响 fingerprint"""
        fp1 = make_fingerprint("R", "t", 1, 3, ["林婉儿", "顾长歌"], "key")
        fp2 = make_fingerprint("R", "t", 1, 3, ["顾长歌", "林婉儿"], "key")
        assert fp1 == fp2

    def test_empty_chars(self):
        fp = make_fingerprint("R", "t", 0, 0, [], "key")
        assert isinstance(fp, str)
        assert len(fp) == 64
