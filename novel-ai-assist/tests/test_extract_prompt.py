"""LLM Prompt 模板测试"""


class TestSystemPrompt:
    """System Prompt 内容验证"""

    def test_system_prompt_defines_role(self):
        """System Prompt 应定义分析工具角色"""
        from core.extract_prompt import SYSTEM_PROMPT

        assert "分析工具" in SYSTEM_PROMPT

    def test_system_prompt_rejects_generation(self):
        """System Prompt 应明确不生成正文"""
        from core.extract_prompt import SYSTEM_PROMPT

        assert (
            "禁止生成" in SYSTEM_PROMPT
            or "不生成" in SYSTEM_PROMPT
            or "不要生成" in SYSTEM_PROMPT
        )


class TestOutputSchema:
    """输出 Schema 验证"""

    def test_schema_has_required_sections(self):
        """输出 JSON 应包含 5 个核心部分"""
        from core.extract_prompt import OUTPUT_SCHEMA

        sections = OUTPUT_SCHEMA["properties"]
        assert "title" in sections
        assert "characters" in sections
        assert "relations" in sections
        assert "timeline_events" in sections
        assert "foreshadowings" in sections


class TestBuildMessages:
    """消息构建测试"""

    def test_returns_list_with_two_messages(self):
        """build_extract_messages 应返回 system + user 两条消息"""
        from core.extract_prompt import build_extract_messages

        messages = build_extract_messages("正文内容")
        assert len(messages) == 2
        assert messages[0]["role"] == "system"
        assert messages[1]["role"] == "user"

    def test_user_message_contains_chapter_text(self):
        """user 消息应包含传入的章节正文"""
        from core.extract_prompt import build_extract_messages

        text = "林婉儿站在天剑山之巅"
        messages = build_extract_messages(text)
        assert text in messages[1]["content"]