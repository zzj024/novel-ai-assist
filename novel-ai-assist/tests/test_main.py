"""应用入口测试"""
from fastapi.testclient import TestClient

class TestAppCreation:
    """应用创建测试"""
    def test_app_creates_successfully(self):
        """create_app() 应返回FastAPI实例"""
        from main import create_app

        app = create_app()
        assert app.title == "novel-ai-assist"

    def test_start_up_creates_default_dirs(self, tmp_path):
        """启动时应创建默认 chapters/ 和 agent_data/"""
        from main import create_app

        app = create_app(base_dir=tmp_path)
        with TestClient(app) as client:
            assert (tmp_path / "chapters").exists()
            assert (tmp_path / "agent_data").exists()

















