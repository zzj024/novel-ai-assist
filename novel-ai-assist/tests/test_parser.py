"""ChapterParser 单元测试 —— mock LLM 调用，测试三种路径"""

import json
from unittest.mock import MagicMock, patch


def _make_valid_response() -> str:
    """生成一个合法的 LLM 返回 JSON（符合 ChapterExtract schema）"""
    return json.dumps({
        "title": "青云之始",
        "summary": "林婉儿在天剑山突破金丹期",
        "characters": [
            {
                "name": "林婉儿",
                "status": {
                    "physical": "健康",
                    "emotional": "坚定",
                    "social": "独行",
                    "location": "天剑山",
                },
            }
        ],
        "relations": [
            {"char_a": "林婉儿", "char_b": "顾长歌", "relation": "师徒"}
        ],
        "timeline_events": [
            {"event": "林婉儿突破金丹", "narrative_order": 1}
        ],
        "foreshadowings": [],
        "unresolved_questions": [],
        "meta": {"truncated": False, "warnings": []},
    })


class TestParseAndStore:
    """parse_and_store 方法的三种路径测试"""

    def test_success_path(self, parser_env):
        """正常路径：LLM 一次性返回合法 JSON → ok=True"""
        from core.parser import ChapterParser

        parser = ChapterParser(parser_env["config"], parser_env["kb"])

        # 先插入一条 pending 章节记录（模拟 scan_chapters 的行为）
        conn = parser_env["kb"].get_conn()
        conn.execute(
            "INSERT INTO chapters (num, filename, status) VALUES (?, ?, 'pending')",
            (1, "第1章.md"),
        )
        conn.commit()

        # 构造 mock 返回值：模拟 OpenAI API 的嵌套结构
        fake_response = MagicMock()
        fake_response.choices = [
            MagicMock(message=MagicMock(content=_make_valid_response()))
        ]

        with patch.object(
            parser.client.chat.completions, "create",
            return_value=fake_response,
        ):
            result = parser.parse_and_store(
                parser_env["chapter_text"], 1, "第1章.md"
            )

        assert result["ok"] is True
        assert result["chapter_num"] == 1
        assert result["error"] is None

        # 验证数据库：status 应为 parsed
        conn = parser_env["kb"].get_conn()
        row = conn.execute(
            "SELECT status, title FROM chapters WHERE num = 1"
        ).fetchone()
        assert row is not None
        assert row["status"] == "parsed"
        assert row["title"] == "青云之始"

    def test_retry_then_success_path(self, parser_env):
        """重试路径：第一次非法 JSON，第二次合法 →重试后成功"""
        from core.parser import ChapterParser

        parser = ChapterParser(parser_env["config"],parser_env["kb"])

        # 先插入 pending 记录
        conn = parser_env["kb"].get_conn()
        conn.execute(
            "INSERT INTO chapters (num, filename,status) VALUES (?, ?, 'pending')",
            (2, "第2章.md"),
        )
        conn.commit()

        # 第一次返回非法 JSON，第二次返回合法 JSON
        fake_good = MagicMock()
        fake_good.choices = [
            MagicMock(message=MagicMock(content=_make_valid_response()))
        ]

        fake_bad = MagicMock()
        fake_bad.choices = [
            MagicMock(message=MagicMock(content="我不是JSON，我是描述文字"))
        ]

        call_count = 0

        def side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            return fake_bad if call_count == 1 else fake_good

        with patch.object(
            parser.client.chat.completions, "create",
            side_effect=side_effect,
        ):
            result = parser.parse_and_store(
                parser_env["chapter_text"], 2,"第2章.md"
            )

        assert result["ok"] is True
        assert result["chapter_num"] == 2

        # 验证 LLM 确实被调用了两次
        assert call_count == 2

    def test_failure_path(self, parser_env):
        """失败路径：两次 LLM 都返回非法 JSON →ok=False, status=error"""
        from core.parser import ChapterParser

        parser = ChapterParser(parser_env["config"],parser_env["kb"])

        # 先插入 pending 记录
        conn = parser_env["kb"].get_conn()
        conn.execute(
            "INSERT INTO chapters (num, filename,status) VALUES (?, ?, 'pending')",
            (3, "第3章.md"),
        )
        conn.commit()

        # 两次都返回非法内容
        fake_bad = MagicMock()
        fake_bad.choices = [
            MagicMock(message=MagicMock(content="我不是JSON"))
        ]

        with patch.object(parser.client.chat.completions, "create",return_value=fake_bad,):
            result = parser.parse_and_store(
                parser_env["chapter_text"], 3,"第3章.md"
            )

        assert result["ok"] is False
        assert result["chapter_num"] == 3
        assert result["error"] is not None

        # 验证数据库：status 应为 error
        row = conn.execute(
            "SELECT status FROM chapters WHERE num = 3"
        ).fetchone()
        assert row["status"] == "error"