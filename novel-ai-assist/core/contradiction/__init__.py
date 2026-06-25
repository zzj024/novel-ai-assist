"""Phase 4 矛盾检测包"""
from core.contradiction.models import (
    BaseRule,
    ContradictionType,
    IssueKind,
    IssueType,
    RuleContext,
    RuleResult,
    ScanSummary,
    Severity,
)
from core.contradiction.engine import ContradictionEngine, ScanResultData
from core.contradiction.loader import DataLoader
