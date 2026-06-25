"""WebSocket 连接管理器——管理客户端连接池 + 消息广播

职责：
- 接受/断开 WebSocket 连接
- 向所有活跃连接广播 JSON 消息
- 提供同步接口（sync→async 桥接），供 parser/monitor 调用

使用方式（在 routes.py 中）：
    manager = ConnectionManager()
    await manager.connect(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket)
"""

import asyncio
import logging
from fastapi import WebSocket

logger = logging.getLogger(__name__)


class ConnectionManager:
    """WebSocket 连接池"""

    def __init__(self) -> None:
        self.active_connections: list[WebSocket] = []
        self._loop: asyncio.AbstractEventLoop | None = None

    def set_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        """记录 asyncio 事件循环（main.py 中初始化）"""
        self._loop = loop

    async def connect(self, ws: WebSocket) -> None:
        """接受新的 WebSocket 连接"""
        await ws.accept()
        self.active_connections.append(ws)
        logger.info("WebSocket 已连接，当前 %d 个连接", len(self.active_connections))

    def disconnect(self, ws: WebSocket) -> None:
        """断开 WebSocket 连接"""
        self.active_connections.remove(ws)
        logger.info("WebSocket 已断开，剩余 %d 个连接", len(self.active_connections))

    def broadcast(self, message: dict) -> None:
        """同步广播：向所有活跃连接推送消息

        可被 sync 线程（parser/monitor）安全调用。
        内部通过 run_coroutine_threadsafe 桥接到 asyncio 事件循环。
        """
        if not self.active_connections:
            return
        alive = []
        for ws in self.active_connections:
            try:
                if self._loop:
                    coro = ws.send_json(message)
                    asyncio.run_coroutine_threadsafe(coro, self._loop)
                alive.append(ws)
            except Exception:
                logger.warning("WebSocket 发送失败，跳过")
        self.active_connections = alive
