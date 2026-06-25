"""应用入口：FastAPI 创建 + 生命周期管理"""
import threading
import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from config import load_config
from core.knowledge import KnowledgeBase
from watcher.monitor import scan_chapters
from api.routes import router

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用启动时初始化，关闭时清理"""
    base_dir: Path = app.state.base_dir
    config_path = base_dir / "agent_data" / "config.json"
    db_path = base_dir / "agent_data" / "novel.db"
    chapters_dir = base_dir / "chapters"

    # 1. 加载配置
    settings = load_config(config_path)
    app.state.settings = settings
    logger.info("配置已加载: %s", config_path)

    # 2. 初始化数据库
    kb = KnowledgeBase(db_path)
    kb.init_db()
    app.state.knowledge_base = kb
    logger.info("数据库已初始化: %s", db_path)

    # 3. 创建 chapters 目录（如不存在）
    chapters_dir.mkdir(parents=True, exist_ok=True)

    # 4. 首次扫描
    scan_chapters(kb, chapters_dir)

    # 5. 启动定时扫描
    stop_event = app.state.stop_event
    if settings.auto_scan_interval > 0:

        def periodic_scan():
            while not stop_event.is_set():
                scan_chapters(kb, chapters_dir)
                stop_event.wait(settings.auto_scan_interval)

        t = threading.Thread(target=periodic_scan, daemon=True)
        t.start()
        logger.info("定时扫描已启动，间隔 %d 秒", settings.auto_scan_interval)

    # 6. 初始化 WebSocket 连接管理器
    from api.ws_manager import ConnectionManager
    ws_manager = ConnectionManager()
    ws_manager.set_loop(asyncio.get_event_loop())
    app.state.ws_manager = ws_manager
    logger.info("WebSocket 管理器已初始化")

    yield  # ← 从这里开始是关闭逻辑

    # 关闭时：停止定时扫描
    stop_event.set()
    logger.info("应用关闭，定时扫描已停止")


def create_app(base_dir: Path = Path(".")) -> FastAPI:
    """创建 FastAPI 应用实例

    base_dir 允许测试时指定临时目录，生产环境默认为当前目录。
    """
    app = FastAPI(title="novel-ai-assist", lifespan=lifespan)

    # 把 base_dir 挂到 app.state 上，lifespan 里能用
    app.state.base_dir = base_dir
    app.state.settings = None
    app.state.knowledge_base = None
    app.state.scan_timer = None
    app.state.stop_event = threading.Event()

    # 注册 CORS 中间件
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(router)

    return app
