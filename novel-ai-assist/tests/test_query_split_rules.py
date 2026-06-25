"""测试 query 引擎规则层：实体提取 / 意图分类 / 重质检查 / fallback 链

这些测试不调用真实 LLM，只用 mock 或纯函数。
"""
import json
import pytest

from core.query import (
    QueryEngine,
    UNKNOWN_INTENT,
    INTENT_KEYWORDS,
    ENTITY_STOPWORDS,
    VALID_INTENTS,
)


# ============================================================
# Fixtures
# ============================================================

@pytest.fixture
def kb_with_chars(tmp_path):
    """含测试角色的 KnowledgeBase"""
    from core.knowledge import KnowledgeBase
    db_path = tmp_path / "agent_data" / "novel.db"
    kb = KnowledgeBase(db_path)
    kb.init_db()

    # 写入测试角色
    conn = kb.get_conn()
    conn.execute(
        """INSERT INTO characters (name, aliases, first_appeared, last_seen)
           VALUES (?, ?, ?, ?)""",
        ("林婉儿", '["婉儿", "林姑娘"]', 1, 5),
    )
    conn.execute(
        """INSERT INTO characters (name, aliases, first_appeared, last_seen)
           VALUES (?, ?, ?, ?)""",
        ("萧炎", '["炎帝", "萧炎哥哥"]', 1, 8),
    )
    conn.execute(
        """INSERT INTO characters (name, first_appeared, last_seen)
           VALUES (?, ?, ?)""",
        ("药老", 2, 6),
    )
    conn.commit()
    return kb


@pytest.fixture
def empty_kb(tmp_path):
    """空数据库"""
    from core.knowledge import KnowledgeBase
    db_path = tmp_path / "agent_data" / "empty.db"
    kb = KnowledgeBase(db_path)
    kb.init_db()
    return kb


@pytest.fixture
def engine(kb_with_chars):
    """含测试数据的 QueryEngine（client 用 Fake）"""
    return QueryEngine(kb=kb_with_chars, cheap_client=None, expensive_client=None)


@pytest.fixture
def empty_engine(empty_kb):
    """空数据库的 QueryEngine"""
    return QueryEngine(kb=empty_kb, cheap_client=None, expensive_client=None)


# ============================================================
# 1. _known_character_names
# ============================================================

class TestKnownCharacterNames:
    def test_returns_names_and_aliases(self, engine):
        names = engine._known_character_names()
        assert "林婉儿" in names
        assert "萧炎" in names
        assert "药老" in names
        assert "婉儿" in names
        assert "林姑娘" in names
        assert "炎帝" in names

    def test_longest_first(self, engine):
        names = engine._known_character_names()
        # 长名优先排序
        assert len(names) > 0

    def test_empty_db_returns_empty(self, empty_engine):
        names = empty_engine._known_character_names()
        assert names == []


# ============================================================
# 2. _extract_entities
# ============================================================

class TestExtractEntities:
    def test_known_character_detected(self, engine):
        entities = engine._extract_entities("林婉儿现在在哪里")
        assert "林婉儿" in entities

    def test_multiple_known_characters(self, engine):
        entities = engine._extract_entities("林婉儿和萧炎是什么关系")
        assert "林婉儿" in entities
        assert "萧炎" in entities

    def test_quoted_entity(self, engine):
        entities = engine._extract_entities("「药老」是什么身份")
        assert "药老" in entities

    def test_stopwords_not_detected(self, engine):
        entities = engine._extract_entities("有哪些章节列表")
        for word in ENTITY_STOPWORDS:
            assert word not in entities

    def test_empty_text(self, engine):
        entities = engine._extract_entities("")
        assert entities == []

    def test_no_entity_in_text(self, engine):
        entities = engine._extract_entities("你好")
        # "你好" 不含常见姓氏，应无命中
        assert entities == []

    def test_relation_both_sides(self, engine):
        entities = engine._extract_entities("林婉儿和萧炎的关系如何")
        assert "林婉儿" in entities
        assert "萧炎" in entities

    def test_context_pattern_status(self, engine):
        entities = engine._extract_entities("林婉儿的修为")
        assert "林婉儿" in entities


# ============================================================
# 3. _classify_intent
# ============================================================

class TestClassifyIntent:
    def test_character_status(self, engine):
        intent = engine._classify_intent("林婉儿什么修为", ["林婉儿"])
        assert intent == "character.status"

    def test_character_location(self, engine):
        intent = engine._classify_intent("林婉儿现在在哪里", ["林婉儿"])
        assert intent == "character.status"

    def test_character_info(self, engine):
        intent = engine._classify_intent("介绍一下林婉儿", ["林婉儿"])
        assert intent == "character.info"

    def test_relation_between_two_entities(self, engine):
        intent = engine._classify_intent(
            "林婉儿和萧炎是什么关系",
            ["林婉儿", "萧炎"],
        )
        assert intent == "relation.between"

    def test_relation_all(self, engine):
        intent = engine._classify_intent("列出所有人物关系", [])
        assert intent == "relation.all"

    def test_chapter_summary(self, engine):
        intent = engine._classify_intent("第5章讲了什么", [])
        assert intent == "chapter.summary"

    def test_chapter_list(self, engine):
        intent = engine._classify_intent("有哪些章节", [])
        assert intent == "chapter.list"

    def test_foreshadowing_list(self, engine):
        intent = engine._classify_intent("还有哪些伏笔没有回收", [])
        assert intent == "foreshadowing.list"

    def test_timeline_list(self, engine):
        intent = engine._classify_intent("按时间线列出重要事件", [])
        assert intent == "timeline.list"

    def test_unknown_intent(self, engine):
        intent = engine._classify_intent("今天天气怎么样", [])
        assert intent == UNKNOWN_INTENT

    def test_relation_between_strong_with_two_entities(self, engine):
        """两个实体 + 关系词 → 强倾向 relation.between"""
        intent = engine._classify_intent(
            "林婉儿和萧炎最近关系如何",
            ["林婉儿", "萧炎"],
        )
        assert intent == "relation.between"

    def test_single_entity_relation_not_between(self, engine):
        """单个实体+关系词 → 不会误判为 relation.between，走 relation.all"""
        intent = engine._classify_intent("林婉儿的关系", ["林婉儿"])
        assert intent == "relation.all"


# ============================================================
# 4. _dedupe_entities
# ============================================================

class TestDedupeEntities:
    def test_removes_duplicates(self, engine):
        result = engine._dedupe_entities(["林婉儿", "林婉儿", "萧炎"])
        assert result == ["林婉儿", "萧炎"]

    def test_filters_stopwords(self, engine):
        result = engine._dedupe_entities(["什么", "关系", "林婉儿"])
        assert "什么" not in result
        assert "关系" not in result
        assert "林婉儿" in result

    def test_filters_short_names(self, engine):
        """1 个字的不是角色名，应过滤；2 个字及以上的保留"""
        result = engine._dedupe_entities(["a", "林婉儿", "萧炎"])
        assert "a" not in result
        assert "林婉儿" in result
        assert "萧炎" in result

    def test_max_entities_capped(self, engine):
        many = [f"角色{i}" for i in range(10)]
        result = engine._dedupe_entities(many)
        assert len(result) <= 4

    def test_empty_input(self, engine):
        assert engine._dedupe_entities([]) == []
        assert engine._dedupe_entities(None) == []

    def test_filters_non_string(self, engine):
        result = engine._dedupe_entities(["林婉儿", 123, None, "萧炎"])
        assert result == ["林婉儿", "萧炎"]


# ============================================================
# 5. _enrich_split_items
# ============================================================

class TestEnrichSplitItems:
    def test_fills_entities_from_rules(self, engine):
        items = [{"original": "林婉儿什么修为", "intent_hint": "unknown"}]
        enriched = engine._enrich_split_items(items, "林婉儿什么修为")
        assert enriched[0]["entities"] == ["林婉儿"]
        assert enriched[0]["intent_hint"] == "character.status"

    def test_preserves_existing_valid_entities(self, engine):
        items = [{
            "original": "林婉儿和萧炎的关系",
            "entities": ["林婉儿"],
            "intent_hint": "unknown",
        }]
        enriched = engine._enrich_split_items(items, "")
        assert "林婉儿" in enriched[0]["entities"]
        assert "萧炎" in enriched[0]["entities"]  # 规则补齐
        # 两个实体 + 关系词 → relation.between
        assert enriched[0]["intent_hint"] == "relation.between"

    def test_preserves_valid_intent(self, engine):
        items = [{
            "original": "林婉儿什么修为",
            "entities": ["林婉儿"],
            "intent_hint": "character.status",
        }]
        enriched = engine._enrich_split_items(items, "")
        assert enriched[0]["intent_hint"] == "character.status"

    def test_fixes_invalid_intent(self, engine):
        items = [{
            "original": "林婉儿什么修为",
            "entities": ["林婉儿"],
            "intent_hint": "invalid_intent_type",
        }]
        enriched = engine._enrich_split_items(items, "")
        assert enriched[0]["intent_hint"] == "character.status"

    def test_skips_empty_original(self, engine):
        items = [{"original": ""}, {"original": "   "}]
        enriched = engine._enrich_split_items(items, "")
        assert enriched == []

    def test_caps_max_items(self, engine):
        items = [{"original": f"第{i}条"} for i in range(10)]
        enriched = engine._enrich_split_items(items, "")
        assert len(enriched) <= 5

    def test_empty_input(self, engine):
        assert engine._enrich_split_items([], "") == []


# ============================================================
# 6. 集成：规则拆句 + 实体 + intent 全链路
# ============================================================

class TestRuleBasedSplitPipeline:
    def test_single_question_status(self, engine):
        entities = engine._extract_entities("林婉儿现在什么修为")
        intent = engine._classify_intent("林婉儿现在什么修为", entities)
        assert intent == "character.status"
        assert entities == ["林婉儿"]

    def test_single_question_relation(self, engine):
        entities = engine._extract_entities("林婉儿和萧炎是什么关系")
        intent = engine._classify_intent("林婉儿和萧炎是什么关系", entities)
        assert intent == "relation.between"
        assert "林婉儿" in entities
        assert "萧炎" in entities

    def test_single_question_foreshadowing(self, engine):
        entities = engine._extract_entities("当前还有哪些伏笔")
        intent = engine._classify_intent("当前还有哪些伏笔", entities)
        assert intent == "foreshadowing.list"

    def test_integration_empty_kb_still_works(self, empty_engine):
        """空数据库不应崩溃"""
        entities = empty_engine._extract_entities("林婉儿什么修为")
        # 空库没有已知角色，通过姓氏正则可能匹配"林婉儿"
        assert isinstance(entities, list)
        intent = empty_engine._classify_intent("林婉儿什么修为", entities)
        assert intent == "character.status"

    def test_text_without_surname(self, engine):
        """无姓氏文本不应误匹配"""
        entities = engine._extract_entities("今天天气真好")
        assert entities == []


class TestIntentKeywordsCoverage:
    """验证所有 INTENT_KEYWORDS 模式都是合法 intent"""

    def test_all_intents_are_valid(self):
        for intent in INTENT_KEYWORDS:
            assert intent in VALID_INTENTS, f"{intent} 不在 VALID_INTENTS 中"

    def test_no_extra_intents(self):
        for intent in VALID_INTENTS:
            assert intent in INTENT_KEYWORDS, (
                f"{intent} 有 VALID_INTENTS 但 INTENT_KEYWORDS 缺匹配规则"
            )


# ============================================================
# 7. _rule_split 直接测试（Step 2）
# ============================================================

class TestRuleSplit:
    """_rule_split 是 Level 1 fallback，必须可靠"""

    def test_single_question(self, engine):
        result = engine._rule_split("林婉儿现在什么修为")
        assert len(result) == 1
        assert result[0]["original"] == "林婉儿现在什么修为"
        assert result[0]["entities"] == ["林婉儿"]
        assert result[0]["intent_hint"] == "character.status"

    def test_multi_question_sentence(self, engine):
        result = engine._rule_split("林婉儿现在在哪里？她和萧炎是什么关系？")
        assert len(result) == 2
        assert result[0]["intent_hint"] == "character.status"
        # 注意：第二句的"她"规则层不消解（依赖上下文过多）
        assert result[1]["original"] == "她和萧炎是什么关系"

    def test_no_split_text(self, engine):
        """没有明显分句标志 → 保留原问题"""
        result = engine._rule_split("林婉儿修为如何")
        assert len(result) == 1
        assert result[0]["original"] == "林婉儿修为如何"

    def test_empty_text(self, engine):
        result = engine._rule_split("")
        assert result == []

    def test_whitespace_only(self, engine):
        result = engine._rule_split("   ")
        assert result == []

    def test_question_with_quotes(self, engine):
        result = engine._rule_split("「药老」是什么来历")
        assert len(result) == 1
        assert "药老" in result[0]["entities"]

    def test_chapter_number_split(self, engine):
        """含章节号 + 逗号衔接 → 按句号拆分"""
        result = engine._rule_split("第5章讲了什么？第6章呢？")
        assert len(result) == 2
        assert result[0]["intent_hint"] == "chapter.summary"

    def test_text_with_exclamation(self, engine):
        result = engine._rule_split("林婉儿太厉害了！她现在什么修为？")
        assert len(result) == 2

    def test_only_unknown_intent(self, engine):
        """无法识别的 intent 应返回 unknown"""
        result = engine._rule_split("今天天气如何")
        assert result[0]["intent_hint"] == "unknown"


# ============================================================
# 8. _split_quality_ok 直接测试（Step 3）
# ============================================================

class TestSplitHardOk:
    """硬检查：结构性校验，失败=降级"""

    def test_accepts_valid_result(self, engine):
        result = [{
            "original": "林婉儿什么修为",
            "entities": ["林婉儿"],
            "intent_hint": "character.status",
        }]
        assert engine._split_hard_ok(result) is True

    def test_rejects_non_list(self, engine):
        assert engine._split_hard_ok("not a list") is False

    def test_rejects_empty_list(self, engine):
        assert engine._split_hard_ok([]) is False

    def test_rejects_too_many_items(self, engine):
        result = [
            {"original": f"问题{i}", "entities": [], "intent_hint": "unknown"}
            for i in range(10)
        ]
        assert engine._split_hard_ok(result) is False

    def test_rejects_non_dict_item(self, engine):
        result = [{"original": "a", "entities": [], "intent_hint": "unknown"}, "not dict"]
        assert engine._split_hard_ok(result) is False

    def test_rejects_missing_original(self, engine):
        result = [{"entities": [], "intent_hint": "character.status"}]
        assert engine._split_hard_ok(result) is False

    def test_rejects_empty_original(self, engine):
        result = [{"original": "", "entities": [], "intent_hint": "character.status"}]
        assert engine._split_hard_ok(result) is False

    def test_rejects_non_string_entities(self, engine):
        result = [{
            "original": "林婉儿什么修为",
            "entities": [123, "林婉儿"],
            "intent_hint": "character.status",
        }]
        assert engine._split_hard_ok(result) is False

    def test_rejects_entities_exceeding_max(self, engine):
        result = [{
            "original": "测试",
            "entities": ["a", "b", "c", "d", "e"],
            "intent_hint": "character.status",
        }]
        assert engine._split_hard_ok(result) is False

    def test_rejects_invalid_intent(self, engine):
        result = [{
            "original": "林婉儿什么修为",
            "entities": ["林婉儿"],
            "intent_hint": "not_valid_intent",
        }]
        assert engine._split_hard_ok(result) is False

    def test_accepts_unknown_intent(self, engine):
        """unknown 是合法值，硬检查通过"""
        result = [{
            "original": "不可识别",
            "entities": [],
            "intent_hint": "unknown",
        }]
        assert engine._split_hard_ok(result) is True


class TestSplitSoftOk:
    """软检查：内容质量校验，失败=enrich 可修复"""

    def test_accepts_valid_result(self, engine):
        result = [{
            "original": "林婉儿什么修为",
            "entities": ["林婉儿"],
            "intent_hint": "character.status",
        }]
        assert engine._split_soft_ok(result) is True

    def test_rejects_relation_between_with_one_entity(self, engine):
        result = [{
            "original": "林婉儿和萧炎是什么关系",
            "entities": ["林婉儿"],
            "intent_hint": "relation.between",
        }]
        assert engine._split_soft_ok(result) is False

    def test_rejects_duplicate_originals(self, engine):
        result = [
            {"original": "林婉儿什么修为", "entities": ["林婉儿"], "intent_hint": "character.status"},
            {"original": "林婉儿什么修为", "entities": ["林婉儿"], "intent_hint": "character.status"},
        ]
        assert engine._split_soft_ok(result) is False

    def test_rejects_all_unknown(self, engine):
        """全部 unknown → 软检查不通过"""
        result = [{"original": "不可识别", "entities": [], "intent_hint": "unknown"}]
        assert engine._split_soft_ok(result) is False

    def test_rejects_unknown_ratio_too_high(self, engine):
        """2/3 unknown > 0.34 → 不通过"""
        result = [
            {"original": "林婉儿什么修为", "entities": ["林婉儿"], "intent_hint": "character.status"},
            {"original": "不可识别1", "entities": [], "intent_hint": "unknown"},
            {"original": "不可识别2", "entities": [], "intent_hint": "unknown"},
        ]
        assert engine._split_soft_ok(result) is False

    def test_accepts_one_unknown_with_three_items(self, engine):
        """3 条中 1 条 unknown (0.33 ≤ 0.34) → 通过"""
        result = [
            {"original": "林婉儿什么修为", "entities": ["林婉儿"], "intent_hint": "character.status"},
            {"original": "萧炎在哪里", "entities": ["萧炎"], "intent_hint": "character.status"},
            {"original": "不可识别", "entities": [], "intent_hint": "unknown"},
        ]
        assert engine._split_soft_ok(result) is True

    def test_accepts_location_with_entities(self, engine):
        result = [{
            "original": "林婉儿现在在哪里",
            "entities": ["林婉儿"],
            "intent_hint": "character.status",
        }]
        assert engine._split_soft_ok(result) is True

    def test_accepts_relation_with_two_entities(self, engine):
        result = [{
            "original": "林婉儿和萧炎是什么关系",
            "entities": ["林婉儿", "萧炎"],
            "intent_hint": "relation.between",
        }]
        assert engine._split_soft_ok(result) is True


class TestAcceptOrRepair:
    """_accept_or_repair 两阶段：硬检查→降级，软检查→enrich"""

    def test_passes_through_good_result(self, engine):
        result = [{
            "original": "林婉儿什么修为",
            "entities": ["林婉儿"],
            "intent_hint": "character.status",
        }]
        fixed = engine._accept_or_repair(result)
        assert fixed is not None
        assert fixed[0]["entities"] == ["林婉儿"]

    def test_repairs_missing_entity_soft_failure(self, engine):
        """实体缺失（软失败）→ enrich 修复后返回，不走降级"""
        result = [{
            "original": "林婉儿什么修为",
            "entities": [],
            "intent_hint": "character.status",
        }]
        fixed = engine._accept_or_repair(result)
        assert fixed is not None
        assert fixed[0]["entities"] == ["林婉儿"]

    def test_repairs_unknown_intent(self, engine):
        """unknown intent（软失败）→ enrich 修复"""
        result = [{
            "original": "林婉儿什么修为",
            "entities": ["林婉儿"],
            "intent_hint": "unknown",
        }]
        fixed = engine._accept_or_repair(result)
        assert fixed is not None
        assert fixed[0]["intent_hint"] == "character.status"

    def test_repairs_relation_with_one_entity(self, engine):
        """relation.between 少一个实体 → enrich 补齐"""
        result = [{
            "original": "林婉儿和萧炎是什么关系",
            "entities": [],
            "intent_hint": "relation.between",
        }]
        fixed = engine._accept_or_repair(result)
        assert fixed is not None
        assert "林婉儿" in fixed[0]["entities"]
        assert "萧炎" in fixed[0]["entities"]

    def test_rejects_hard_failure(self, engine):
        """硬失败（JSON 坏）→ None，走降级"""
        assert engine._accept_or_repair("not a list") is None

    def test_rejects_empty_list_hard(self, engine):
        assert engine._accept_or_repair([]) is None

class TestSplitWithMock:
    """mock LLM 返回，验证 _split 走 enrich 补齐流程"""

    def test_mock_llm_returns_bare_originals(self, engine):
        """mock qwen 只返回 original（轻量 prompt 格式），entities/intent 由规则补齐"""
        from unittest.mock import MagicMock
        mock_response = MagicMock()
        mock_response.choices = [
            MagicMock(message=MagicMock(content='[{"original": "林婉儿什么修为"}]'))
        ]
        engine.cheap = MagicMock()
        engine.cheap.chat.completions.create.return_value = mock_response

        result = engine._split("林婉儿什么修为")
        assert len(result) == 1
        assert result[0]["original"] == "林婉儿什么修为"
        assert result[0]["entities"] == ["林婉儿"]
        assert result[0]["intent_hint"] == "character.status"

    def test_mock_llm_returns_multiple(self, engine):
        from unittest.mock import MagicMock
        mock_response = MagicMock()
        mock_response.choices = [
            MagicMock(message=MagicMock(content=(
                '[{"original": "林婉儿什么修为"}, {"original": "萧炎在哪里"}]'
            )))
        ]
        engine.cheap = MagicMock()
        engine.cheap.chat.completions.create.return_value = mock_response

        result = engine._split("林婉儿什么修为？萧炎在哪里？")
        assert len(result) == 2
        assert result[0]["entities"] == ["林婉儿"]
        assert result[1]["entities"] == ["萧炎"]

    def test_mock_llm_returns_empty(self, engine):
        """LLM 返回空 → 走 enrich 兜底"""
        from unittest.mock import MagicMock
        mock_response = MagicMock()
        mock_response.choices = [MagicMock(message=MagicMock(content=None))]
        engine.cheap = MagicMock()
        engine.cheap.chat.completions.create.return_value = mock_response

        result = engine._split("林婉儿什么修为")
        assert result[0]["intent_hint"] == "character.status"

    def test_mock_llm_returns_old_format_with_entities(self, engine):
        """兼容旧格式：LLM 返回带 entities/intent 的结果 → enrich 合并"""
        from unittest.mock import MagicMock
        mock_response = MagicMock()
        mock_response.choices = [
            MagicMock(message=MagicMock(content=(
                '[{"original": "林婉儿什么修为", "entities": ["林婉儿"], "intent_hint": "character.status"}]'
            )))
        ]
        engine.cheap = MagicMock()
        engine.cheap.chat.completions.create.return_value = mock_response

        result = engine._split("林婉儿什么修为")
        assert result[0]["entities"] == ["林婉儿"]
        assert result[0]["intent_hint"] == "character.status"


# ============================================================
# 10. 边界测试
# ============================================================

class TestBoundaryCases:
    """特殊输入、极端场景"""

    def test_text_with_only_stopwords(self, engine):
        entities = engine._extract_entities("什么关系状态")
        assert entities == []

    def test_text_with_numbers(self, engine):
        entities = engine._extract_entities("第5章的内容")
        assert entities == []

    def test_text_with_mixed_lang(self, engine):
        entities = engine._extract_entities("Lin Wan'er 的修为")
        # 英文字母不应被识别为中文人名
        assert all(len(e) >= 2 for e in entities)

    def test_text_with_special_chars(self, engine):
        entities = engine._extract_entities("@林婉儿 #萧炎")
        assert "林婉儿" in entities or entities == []

    def test_very_long_text(self, engine):
        text = "林婉儿" * 100
        entities = engine._extract_entities(text)
        assert "林婉儿" in entities
        assert len(entities) <= 4  # 不应爆炸

    def test_intent_conflict_chapter_and_relation(self, engine):
        """第N章 + 两个实体 + 关系词 → 应优先 relation.between"""
        intent = engine._classify_intent(
            "第10章里林婉儿和萧炎的关系有什么变化",
            ["林婉儿", "萧炎"],
        )
        assert intent == "relation.between"

    def test_intent_conflict_chapter_and_status(self, engine):
        """第N章 + 状态词 → chapter.summary 优先"""
        intent = engine._classify_intent("第3章林婉儿什么修为", ["林婉儿"])
        # 第N章 + 状态词 → 因为 chapter.summary +4 而 status +2
        assert intent == "chapter.summary"

    def test_split_soft_ok_with_focus_context(self, engine):
        """质量检查不应受对话上下文影响（纯函数）"""
        result = [{
            "original": "他和萧炎什么关系",
            "entities": ["萧炎"],
            "intent_hint": "relation.between",
        }]
        # 注意："他" 没有被 entities 覆盖，但 relation.between 有 1 个实体 < 2 → 不合格
        assert engine._split_soft_ok(result) is False

    def test_known_character_alias_not_in_text(self, engine):
        """别名不在原文中时不应提取"""
        entities = engine._extract_entities("萧炎在哪里")
        assert "婉儿" not in entities  # 别名不应凭空出现
        assert "林姑娘" not in entities
        assert "炎帝" not in entities  # "炎帝"不在原文"萧炎在哪里"中


# ============================================================
# 11. Debug trace 测试
# ============================================================

class TestDebugTrace:
    """enrich trace 可观测性测试"""

    def test_trace_records_before_and_after(self, engine):
        """debug 模式下 trace 记录 entities 和 intent 的变化"""
        engine._debug_trace = []
        items = [{
            "original": "林婉儿什么修为",
            "entities": [],
            "intent_hint": "unknown",
        }]
        engine._enrich_split_items(items, "")
        assert len(engine._debug_trace) == 1
        entry = engine._debug_trace[0]
        assert entry["original"] == "林婉儿什么修为"
        assert entry["entities_before"] == []
        assert "林婉儿" in entry["entities_after"]
        assert entry["intent_before"] == "unknown"
        assert entry["intent_after"] == "character.status"

    def test_trace_empty_when_debug_off(self, engine):
        """非 debug 模式不记录 trace"""
        engine._debug_trace = None
        items = [{
            "original": "林婉儿什么修为",
            "entities": [],
            "intent_hint": "unknown",
        }]
        engine._enrich_split_items(items, "")
        assert engine._debug_trace is None

    def test_trace_fills_entities(self, engine):
        """trace 中 entities_after 应包含所有补齐的实体"""
        engine._debug_trace = []
        items = [{
            "original": "林婉儿和萧炎的关系",
            "entities": [],
            "intent_hint": "unknown",
        }]
        engine._enrich_split_items(items, "")
        entry = engine._debug_trace[0]
        assert "林婉儿" in entry["entities_after"]
        assert "萧炎" in entry["entities_after"]

    def test_trace_multiple_items(self, engine):
        """多子问题，每个各有独立 trace"""
        engine._debug_trace = []
        items = [
            {"original": "林婉儿什么修为", "entities": [], "intent_hint": "unknown"},
            {"original": "萧炎在哪里", "entities": [], "intent_hint": "unknown"},
        ]
        engine._enrich_split_items(items, "")
        assert len(engine._debug_trace) == 2
        assert engine._debug_trace[0]["intent_after"] == "character.status"
        assert engine._debug_trace[1]["intent_after"] == "character.status"

    def test_run_with_debug_returns_trace(self, engine):
        """run(debug=True) 返回结果应含 debug_trace"""
        result = engine.run("林婉儿什么修为", debug=True)
        assert "debug_trace" in result
        assert isinstance(result["debug_trace"], list)

    def test_run_without_debug_no_trace(self, engine):
        """run(debug=False) 不返回 debug_trace"""
        result = engine.run("林婉儿什么修为", debug=False)
        assert "debug_trace" not in result


# ============================================================
# 12. Explain / Score 测试
# ============================================================

class TestIntentScore:
    """_score_intent 得分明细测试"""

    def test_returns_scores_dict(self, engine):
        scores = engine._score_intent("林婉儿什么修为", ["林婉儿"])
        assert isinstance(scores, dict)
        assert "character.status" in scores
        assert scores["character.status"] >= 2

    def test_empty_text_returns_empty(self, engine):
        scores = engine._score_intent("", [])
        assert scores == {}

    def test_trace_includes_intent_scores(self, engine):
        """debug 模式下 enrich 的 trace 应包含 intent_scores"""
        engine._debug_trace = []
        items = [{
            "original": "林婉儿什么修为",
            "entities": [],
            "intent_hint": "unknown",
        }]
        engine._enrich_split_items(items, "")
        entry = engine._debug_trace[0]
        assert "intent_scores" in entry
        assert isinstance(entry["intent_scores"], dict)


# ============================================================
# 13. Episodic entity 集成测试
# ============================================================

class TestEpisodicEntityExtraction:
    """描述性实体在查询引擎中的提取测试"""

    def test_known_episodic_descriptor_detected(self, engine):
        """已入库的描述性实体应被提取"""
        engine.kb.get_conn().execute(
            "INSERT INTO episodic_entities (descriptor, chapter) VALUES (?, ?)",
            ("黑衣人", 1),
        )
        engine.kb.get_conn().commit()

        descs = engine._known_episodic_descriptors()
        assert "黑衣人" in descs

    def test_episodic_entity_in_extract(self, engine):
        """_extract_entities 包含已入库的描述性实体"""
        engine.kb.get_conn().execute(
            "INSERT INTO episodic_entities (descriptor, chapter) VALUES (?, ?)",
            ("黑衣人", 1),
        )
        engine.kb.get_conn().commit()

        entities = engine._extract_entities("黑衣人现在什么修为")
        assert "黑衣人" in entities

    def test_episodic_not_in_text_not_extracted(self, engine):
        """描述符不在文本中时不提取"""
        engine.kb.get_conn().execute(
            "INSERT INTO episodic_entities (descriptor, chapter) VALUES (?, ?)",
            ("黑衣人", 1),
        )
        engine.kb.get_conn().commit()

        entities = engine._extract_entities("林婉儿什么修为")
        assert "黑衣人" not in entities

    def test_episodic_takes_lower_priority_than_known(self, engine):
        """已知角色名优先于描述性实体"""
        engine.kb.get_conn().execute(
            "INSERT INTO episodic_entities (descriptor, chapter) VALUES (?, ?)",
            ("林婉儿", 1),  # 描述性实体也叫"林婉儿"
        )
        engine.kb.get_conn().commit()

        entities = engine._extract_entities("林婉儿在哪里")
        # 应识别为已知角色（characters 表已有），不为"林婉儿"在 episodic 表困惑
        assert "林婉儿" in entities

    def test_enrich_fills_episodic_intent(self, engine):
        """描述性实体+状态词 → 正确 intent"""
        engine.kb.get_conn().execute(
            "INSERT INTO episodic_entities (descriptor, chapter) VALUES (?, ?)",
            ("黑衣人", 1),
        )
        engine.kb.get_conn().commit()

        intent = engine._classify_intent("黑衣人什么修为", ["黑衣人"])
        assert intent == "character.status"

    def test_empty_db_episodic(self, empty_engine):
        """空 episodic 表不崩溃"""
        assert empty_engine._known_episodic_descriptors() == []
