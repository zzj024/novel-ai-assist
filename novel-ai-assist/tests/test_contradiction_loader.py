"""Phase 4 Step 2：DataLoader 单元测试"""
import json
import pytest
from core.contradiction.loader import DataLoader
from core.contradiction.models import RuleContext


@pytest.fixture
def loaded_kb(tmp_path):
    """构建含测试数据的 KnowledgeBase"""
    from core.knowledge import KnowledgeBase

    db_path = tmp_path / "agent_data" / "novel.db"
    kb = KnowledgeBase(db_path)
    kb.init_db()
    conn = kb.get_conn()

    # 5 个已解析章节
    for i in range(1, 6):
        conn.execute(
            "INSERT INTO chapters (num, filename, status, summary) VALUES (?,?,?,?)",
            (i, f"第{i}章.md", "parsed", f"第{i}章摘要"),
        )

    # 2 个角色，含 status_history
    conn.execute(
        """INSERT INTO characters (name, aliases, first_appeared, last_seen,
           current_status, status_history, description)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (
            "林婉儿",
            json.dumps(["婉儿", "林师妹"]),
            1, 5,
            json.dumps({"physical": "金丹期", "location": "天剑山"}),
            json.dumps([
                {"chapter": 1, "field": "status", "new": {"physical": "筑基期", "location": "天剑山"}},
                {"chapter": 3, "field": "status", "new": {"physical": "金丹期", "location": "天剑山"}},
            ]),
            "天剑宗弟子",
        ),
    )
    conn.execute(
        """INSERT INTO characters (name, aliases, first_appeared, last_seen,
           current_status, status_history, description)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (
            "顾长歌",
            json.dumps(["掌门", "顾师叔"]),
            1, 5,
            json.dumps({"physical": "元婴期", "location": "天剑山"}),
            json.dumps([
                {"chapter": 1, "field": "status", "new": {"physical": "元婴期", "location": "天剑山"}},
            ]),
            "天剑宗掌门",
        ),
    )

    # 关系
    conn.execute(
        "INSERT INTO relations (char_a, char_b, relation, chapter, detail) "
        "VALUES (?, ?, ?, ?, ?)",
        ("林婉儿", "顾长歌", "师徒", 1, "天剑宗掌门弟子"),
    )

    # 时间线
    conn.execute(
        "INSERT INTO timeline_events (chapter, story_time, event, narrative_order, "
        "characters, location) VALUES (?, ?, ?, ?, ?, ?)",
        (1, "清晨", "林婉儿突破金丹期", 1, json.dumps(["林婉儿"]), "天剑山"),
    )

    # 伏笔
    conn.execute(
        "INSERT INTO foreshadowings (description, laid_chapter, status, confidence, "
        "confidence_label) VALUES (?, ?, ?, ?, ?)",
        ("神秘黑衣人", 1, "unrecovered", 0.8, "high"),
    )

    conn.commit()
    return kb


class TestDataLoader:
    def test_load_returns_rule_context(self, loaded_kb):
        loader = DataLoader(loaded_kb)
        ctx = loader.load()
        assert isinstance(ctx, RuleContext)

    def test_load_characters(self, loaded_kb):
        loader = DataLoader(loaded_kb)
        ctx = loader.load()
        assert len(ctx.characters) == 2

    def test_load_status_by_char(self, loaded_kb):
        """status_history 被正确解析并按章节排序"""
        loader = DataLoader(loaded_kb)
        ctx = loader.load()
        assert "林婉儿" in ctx.status_by_char
        assert len(ctx.status_by_char["林婉儿"]) == 2
        # 按 chapter 升序
        assert ctx.status_by_char["林婉儿"][0]["chapter"] == 1
        assert ctx.status_by_char["林婉儿"][1]["chapter"] == 3

    def test_load_relations(self, loaded_kb):
        loader = DataLoader(loaded_kb)
        ctx = loader.load()
        assert len(ctx.relations) == 1

    def test_load_relations_by_pair(self, loaded_kb):
        loader = DataLoader(loaded_kb)
        ctx = loader.load()
        # pair 应该是排序后的 (林婉儿, 顾长歌)
        pair = ("林婉儿", "顾长歌")
        assert pair in ctx.relations_by_pair
        assert len(ctx.relations_by_pair[pair]) == 1

    def test_load_timeline(self, loaded_kb):
        loader = DataLoader(loaded_kb)
        ctx = loader.load()
        assert len(ctx.timeline_events) == 1
        # 按 story_time 分组
        assert "清晨" in ctx.timeline_by_story_time
        assert len(ctx.timeline_by_story_time["清晨"]) == 1
        # 按 chapter 分组
        assert 1 in ctx.timeline_by_chapter

    def test_load_foreshadowings(self, loaded_kb):
        loader = DataLoader(loaded_kb)
        ctx = loader.load()
        assert len(ctx.foreshadowings) == 1

    def test_load_max_parsed_chapter(self, loaded_kb):
        loader = DataLoader(loaded_kb)
        ctx = loader.load()
        assert ctx.max_parsed_chapter == 5

    def test_load_chapters(self, loaded_kb):
        loader = DataLoader(loaded_kb)
        ctx = loader.load()
        assert len(ctx.chapters) == 5

    def test_load_empty_db(self, tmp_path):
        """空数据库不报错"""
        from core.knowledge import KnowledgeBase

        kb = KnowledgeBase(tmp_path / "empty.db")
        kb.init_db()
        loader = DataLoader(kb)
        ctx = loader.load()
        assert ctx.characters == []
        assert ctx.max_parsed_chapter == 0
        assert ctx.timeline_events == []
        assert ctx.foreshadowings == []

    def test_parse_status_history_empty(self, loaded_kb):
        """没有 status_history 的角色不会出现在 status_by_char 中"""
        loader = DataLoader(loaded_kb)
        ctx = loader.load()
        # status_by_char 只含有关注的状态变更
        assert isinstance(ctx.status_by_char, dict)

    def test_load_with_config(self, loaded_kb):
        loader = DataLoader(loaded_kb, config={"threshold": 20})
        ctx = loader.load()
        assert ctx.config["threshold"] == 20
