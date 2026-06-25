"""测试 ContradictionEngine 集成"""
import json
import pytest
from core.contradiction.engine import ContradictionEngine


@pytest.fixture
def engine_kb(tmp_path):
    """构建含测试数据的 KnowledgeBase，覆盖多条规则"""
    from core.knowledge import KnowledgeBase

    db_path = tmp_path / "agent_data" / "novel.db"
    kb = KnowledgeBase(db_path)
    kb.init_db()
    conn = kb.get_conn()

    # 25 个已解析章节（让伏笔 gap > 20）
    for i in range(1, 26):
        conn.execute(
            "INSERT INTO chapters (num, filename, status, summary) VALUES (?,?,?,?)",
            (i, f"第{i}章.md", "parsed", f"第{i}章摘要"),
        )

    # 角色—林婉儿（跨章状态变化）
    conn.execute(
        """INSERT INTO characters (name, aliases, first_appeared, last_seen,
           current_status, status_history, description)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        ("林婉儿", '["婉儿"]', 1, 25,
         json.dumps({"physical": "金丹期", "location": "魔域"}),
         json.dumps([
             {"chapter": 1, "new": {"physical": "筑基期", "location": "天剑山"}},
             {"chapter": 3, "new": {"physical": "金丹期", "location": "天剑山"}},
             {"chapter": 6, "new": {"physical": "金丹期", "location": "魔域"}},
         ]),
         "主角"),
    )

    # 角色—赵无极（别名冲突用）
    conn.execute(
        """INSERT INTO characters (name, aliases, first_appeared, last_seen,
           current_status, status_history, description)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        ("赵无极", '["尊者"]', 1, 3,
         json.dumps({"physical": "元婴期"}),
         json.dumps([
             {"chapter": 1, "new": {"physical": "元婴期"}},
         ]),
         "反派"),
    )

    # 另一角色用同一别名 → alias collision
    conn.execute(
        """INSERT INTO characters (name, aliases, first_appeared, last_seen,
           current_status, status_history, description)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        ("神秘人", '["尊者"]', 5, 5,
         json.dumps({"physical": "?"}),
         json.dumps([]),
         "神秘角色"),
    )

    # 时间线—同 story_time 不同地点
    conn.execute(
        "INSERT INTO timeline_events (chapter, story_time, event, narrative_order, "
        "characters, location) VALUES (?, ?, ?, ?, ?, ?)",
        (3, "子时", "林婉儿在天剑山", 1, '["林婉儿"]', "天剑山"),
    )
    conn.execute(
        "INSERT INTO timeline_events (chapter, story_time, event, narrative_order, "
        "characters, location) VALUES (?, ?, ?, ?, ?, ?)",
        (4, "子时", "林婉儿在魔域", 1, '["林婉儿"]', "魔域"),
    )

    # 关系
    conn.execute(
        "INSERT INTO relations (char_a, char_b, relation, chapter, detail) "
        "VALUES (?, ?, ?, ?, ?)",
        ("林婉儿", "顾长歌", "师徒", 1, ""),
    )

    # 伏笔—超龄未回收
    conn.execute(
        "INSERT INTO foreshadowings (description, laid_chapter, status, confidence, "
        "confidence_label) VALUES (?, ?, ?, ?, ?)",
        ("神秘黑衣人", 1, "unrecovered", 0.9, "high"),
    )

    conn.commit()
    return kb


class TestContradictionEngine:

    def test_scan_all_returns_results(self, engine_kb):
        """全量扫描返回结果"""
        engine = ContradictionEngine(engine_kb)
        result = engine.scan_all()
        assert result.summary.total > 0
        assert result.summary.duration_ms > 0

    def test_scan_detects_alias_collision(self, engine_kb):
        """别名冲突应被检测到"""
        engine = ContradictionEngine(engine_kb)
        result = engine.scan_all()
        alias_results = [
            r for r in result.results
            if r.contradiction_type.value == "alias_collision"
        ]
        assert len(alias_results) >= 1

    def test_scan_detects_same_time_diff_location(self, engine_kb):
        """同时间不同地点应被检测到"""
        engine = ContradictionEngine(engine_kb)
        result = engine.scan_all()
        st_loc_results = [
            r for r in result.results
            if r.contradiction_type.value == "same_time_diff_location"
        ]
        assert len(st_loc_results) >= 1

    def test_scan_detects_status_change(self, engine_kb):
        """状态变化无解释应被检测到"""
        engine = ContradictionEngine(engine_kb)
        result = engine.scan_all()
        status_results = [
            r for r in result.results
            if r.contradiction_type.value == "status_change_anomaly"
        ]
        assert len(status_results) >= 1

    def test_scan_detects_foreshadowing_aging(self, engine_kb):
        """伏笔超龄应被检测到（laid=1, curr=25, gap=24 > 20）"""
        engine = ContradictionEngine(engine_kb)
        result = engine.scan_all()
        aging_results = [
            r for r in result.results
            if r.contradiction_type.value == "foreshadowing_aging"
        ]
        assert len(aging_results) >= 1

    def test_scan_summary_has_counts(self, engine_kb):
        """摘要包含分类统计"""
        engine = ContradictionEngine(engine_kb)
        result = engine.scan_all()
        assert result.summary.total > 0
        assert len(result.summary.by_severity) > 0
        assert len(result.summary.by_issue_type) > 0
        assert len(result.summary.by_contradiction_type) > 0

    def test_get_cached_returns_same(self, engine_kb):
        """缓存应返回相同结果"""
        engine = ContradictionEngine(engine_kb)
        result1 = engine.scan_all()
        cached = engine.get_cached()
        assert cached is not None
        assert cached.summary.total == result1.summary.total

    def test_scan_empty_db(self, tmp_path):
        """空数据库不报错"""
        from core.knowledge import KnowledgeBase
        kb = KnowledgeBase(tmp_path / "empty.db")
        kb.init_db()
        engine = ContradictionEngine(kb)
        result = engine.scan_all()
        assert result.summary.total == 0

    def test_get_paginated_results(self, engine_kb):
        """分页查询正常工作"""
        engine = ContradictionEngine(engine_kb)
        engine.scan_all()
        items, total, summary = engine.get_paginated_results(
            page=1, page_size=5, sort_by="severity", sort_order="desc",
        )
        assert len(items) <= 5
        assert total > 0

    def test_filter_by_type(self, engine_kb):
        """按类型筛选"""
        engine = ContradictionEngine(engine_kb)
        engine.scan_all()
        items, total, _ = engine.get_paginated_results(
            type_filter="alias_collision",
        )
        assert total >= 1
        assert all(i.contradiction_type.value == "alias_collision" for i in items)
