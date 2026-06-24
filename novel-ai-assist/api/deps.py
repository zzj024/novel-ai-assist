"""FastAPI 依赖注入

职责：
- 提供 get_db()：每个请求注入一个 KnowledgeBase 实例
- 路由只需声明类型注解，FastAPI 自动管理生命周期

注意：get_config() 暂时移除——Settings 模型当前不含 db_path，
      get_db 直接使用默认路径。后续如需从配置读取 db_path 再恢复。
"""

from collections.abc import Generator
from pathlib import Path

from core.knowledge import KnowledgeBase


def get_db() -> Generator[KnowledgeBase, None, None]:
    """注入 KnowledgeBase 实例

    yield 让 FastAPI 在请求结束后回到这里，
    后续可扩展事务提交/回滚逻辑。
    """
    kb = KnowledgeBase(Path("agent_data/novel.db"))
    yield kb