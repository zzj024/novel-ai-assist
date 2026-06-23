"""文件监听模块测试"""
import pytest

class TestExtractChapterNum:
    """文件名 -> 章序号提取测试"""
    def test_chinese_format(self):
        """第3章.md -> 3"""
        from watcher.monitor import extract_chapter_num

        assert extract_chapter_num("第3章.md") == 3
        assert extract_chapter_num("第12章.md") == 12
        assert extract_chapter_num("第1章 青云之始.md") == 1


    def test_english_format(self):
        """ch12.md → 12，chapter_04.md → 4"""
        from watcher.monitor import extract_chapter_num

        assert extract_chapter_num("ch12.md") == 12
        assert extract_chapter_num("ch01.md") == 1
        assert extract_chapter_num("chapter_04.md") == 4
        assert extract_chapter_num("chapter-05.md") == 5

    def test_digits_only(self):
        """07.md → 7"""
        from watcher.monitor import extract_chapter_num

        assert extract_chapter_num("07.md") == 7
        assert extract_chapter_num("123.md") == 123

    def test_no_match(self):
        """无法提取章序号时应抛出 ValueError"""
        from watcher.monitor import extract_chapter_num

        with pytest.raises(ValueError):
            extract_chapter_num("readme.md")


class TestScanChapters:
    """目录扫描测试"""

    def test_scan_finds_new_files(self, tmp_db_path, tmp_chapter_dir):
        """新文件不在db中->标记为pending"""
        from watcher.monitor import scan_chapters
        from core.knowledge import KnowledgeBase

        kb = KnowledgeBase(tmp_db_path)
        kb.init_db()

        # 在 tmp_chapter_dir 里再加一章
        ch2 = tmp_chapter_dir / "第2章.md"
        ch2.write_text("# 第2章\n\n内容.",encoding="utf-8")

        # 执行扫描
        result = scan_chapters(kb, tmp_chapter_dir)
        # 验证返回了被标记的章序号
        assert 1 in result
        assert 2 in result

        # 验证db里 status = "pending"
        conn = kb.get_conn()
        rows = conn.execute("SELECT num, status FROM chapters ORDER BY num").fetchall()

        assert len(rows) == 2
        assert rows[0]["status"] == "pending"
        assert rows[1]["status"] == "pending"

    def test_scan_detects_content_change(self, tmp_db_path,tmp_chapter_dir):
        """文件内容变了 → 重置为 pending"""
        from watcher.monitor import scan_chapters
        from core.knowledge import KnowledgeBase

        kb = KnowledgeBase(tmp_db_path)
        kb.init_db()

        # 先扫描一次（文件入库）
        scan_chapters(kb, tmp_chapter_dir)
        ch1 = tmp_chapter_dir / "第2章.md"
        ch1.write_text("# 第2章 秘境探险\n\n"
            "顾长歌带着林婉儿穿过天剑山的后山禁地，"
            "一路上荆棘密布，毒虫横行。\n\n"
            "「前方就是秘境入口了，」顾长歌指着前方"
            "一个散发着淡蓝色光芒的漩涡说道。\n\n"
            "林婉儿握紧手中的长剑，心中既紧张又期待。"
            "这次秘境试炼是她突破金丹期后的第一次实战。", 
        encoding="utf-8")

        # 再次扫描
        result = scan_chapters(kb, tmp_chapter_dir)

        # 第2章应该被标记为 pending
        assert 2 in result

    def test_scan_skips_unchanged_files(self, tmp_db_path, tmp_chapter_dir):
        """文件内容没变 → 不标记，返回空列表"""
        from watcher.monitor import scan_chapters
        from core.knowledge import KnowledgeBase

        kb = KnowledgeBase(tmp_db_path)
        kb.init_db()

        # 先扫描一次（文件入库）
        scan_chapters(kb, tmp_chapter_dir)

        # 不修改任何文件，再扫一次
        result = scan_chapters(kb, tmp_chapter_dir)

          # 没有文件变化
        assert result == []



