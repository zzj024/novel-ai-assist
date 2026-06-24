"""Phase 1 共享测试Fixture"""
import pytest


@pytest.fixture
def tmp_config_path(tmp_path):
    """返回一个临时的config.json路径"""
    return tmp_path / "agent_data" / "config.json"

@pytest.fixture
def tmp_db_path(tmp_path):
    """返回一个临时的novel.db路径"""
    return tmp_path / "agent_data" / "novel.db"

@pytest.fixture
def sample_config_data():
    """一份有效的配置数据"""
    return {
        "novel_dir": ".",
        "ai_provider": "deepseek",
        "api_base": "https://api.deepseek.com/v1",
        "api_key": "sk-test-key-12345",
        "model": "deepseek-chat",
        "language": "zh",
        "auto_scan_interval": 3600,
    }
@pytest.fixture
def sample_ollama_config_data():
    """Ollama 本地模型配置数据"""
    return {
        "novel_dir": ".",
        "ai_provider": "ollama",
        "api_base": "http://localhost:11434/v1",
        "api_key": "",
        "model": "qwen2.5:7b",
        "language": "zh",
        "auto_scan_interval": 3600,
    }

@pytest.fixture
def tmp_chapter_dir(tmp_path):
    """返回一个临时的chapters/目录，内含一个实例.md文件"""
    ch_dir = tmp_path / "chapters"
    ch_dir.mkdir(parents=True)
    ch_file = ch_dir / "第1章.md"
    ch_file.write_text("# 第1章 青云之始\n\n"
        "天剑山，云雾缭绕，万仞高峰直插云霄。\n\n"

        "林婉儿站在山巅，衣袂飘飘，目光坚定。今日是她突破金丹期的关键时刻。"
        "体内灵力运转三个大周天，丹田处的真气已经开始凝结成丹。\n\n"
        "「这一次，我一定要成功。」她低声自语。\n\n"

        "远处，一道剑光破空而来，落在她身后十丈处。来人是天剑宗掌门——顾长歌。\n\n"
        "「婉儿，准备好了吗？」顾长歌的声音沉稳有力，带着一丝关切。\n\n"
        "林婉儿点头，没有回头：「嗯。」\n\n"
        "顾长歌在她身后护法，灵力外放，形成一个防护罩。",
    encoding="utf-8")
    return ch_dir

@pytest.fixture
def parser_env(tmp_path):
    """构造 ChapterParser 的测试环境（真实 knowledge_base + mock 配置）
    返回一个 dict:
        kb: KnowledgeBase 实例（临时数据库已初始化）
        config: 模拟的配置对象
        chapter_text: 测试用章节正文
    """
    from core.knowledge import KnowledgeBase

    db_path = tmp_path / "agent_data" / "novel.db"
    kb = KnowledgeBase(db_path)
    kb.init_db()

    class FakeConfig:
        api_key = "sk-test"
        api_base = "https://api.deepseek.com/v1"
        model = "deepseek-chat"

    chapter_text = (
        "天剑山，云雾缭绕。林婉儿站在山巅，衣袂飘飘。\n"
        "今日是她突破金丹期的关键时刻。"
        "体内灵力运转三个大周天，丹田处的真气已经开始凝结成丹。\n"
        "「这一次，我一定要成功。」她低声自语。\n"
        "远处，一道剑光破空而来，落在她身后十丈处。"
        "来人是天剑宗掌门——顾长歌。\n"
        "「婉儿，准备好了吗？」顾长歌的声音沉稳有力。\n"
        "林婉儿点头，没有回头：「嗯。」"
    )

    return {
        "kb": kb,
        "config": FakeConfig(),
        "chapter_text": chapter_text,
    }
