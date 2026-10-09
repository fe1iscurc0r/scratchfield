"""
WebSocket 连接管理器
用于实时推送消息到前端
"""

import asyncio
import json
import logging
import time
from typing import Any, Dict, Set

from fastapi import WebSocket, WebSocketDisconnect
import threading

logger = logging.getLogger(__name__)


class WebSocketManager:
    """WebSocket连接管理器"""

    def __init__(self):
        # session_id -> WebSocket connections
        self._connections: dict[str, set[WebSocket]] = {}
        # 全局连接（不绑定特定session）
        self._global_connections: set[WebSocket] = set()
        self._lock = asyncio.Lock()

    async def connect(self, websocket: WebSocket, session_id: str = None):
        """接受新的WebSocket连接"""
        await websocket.accept()

        async with self._lock:
            if session_id:
                if session_id not in self._connections:
                    self._connections[session_id] = set()
                self._connections[session_id].add(websocket)
                logger.info(f"[WebSocket] 新连接: session={session_id}, 总连接数={len(self._connections[session_id])}")
            else:
                self._global_connections.add(websocket)
                logger.info(f"[WebSocket] 新全局连接, 总连接数={len(self._global_connections)}")

    async def disconnect(self, websocket: WebSocket, session_id: str = None):
        """断开WebSocket连接"""
        async with self._lock:
            if session_id and session_id in self._connections:
                self._connections[session_id].discard(websocket)
                if not self._connections[session_id]:
                    del self._connections[session_id]
                logger.info(f"[WebSocket] 连接断开: session={session_id}")
            else:
                self._global_connections.discard(websocket)
                logger.info("[WebSocket] 全局连接断开")

    async def send_to_session(self, session_id: str, message: dict[str, Any]):
        """发送消息到特定会话的所有连接"""
        if session_id not in self._connections:
            logger.debug(f"[WebSocket] 会话 {session_id} 无活跃连接")
            return 0

        message_json = json.dumps(message, ensure_ascii=False)
        disconnected = set()
        sent_count = 0

        for ws in self._connections[session_id]:
            try:
                await ws.send_text(message_json)
                sent_count += 1
            except Exception as e:
                logger.warning(f"[WebSocket] 发送失败: {e}")
                disconnected.add(ws)

        # 清理断开的连接
        if disconnected:
            async with self._lock:
                self._connections[session_id] -= disconnected
                if not self._connections[session_id]:
                    del self._connections[session_id]

        return sent_count

    async def broadcast(self, message: dict[str, Any], exclude_session: str = None):
        """广播消息到所有连接"""
        message_json = json.dumps(message, ensure_ascii=False)
        disconnected_global = set()
        disconnected_sessions = {}
        sent_count = 0

        # 发送到全局连接
        for ws in self._global_connections:
            try:
                await ws.send_text(message_json)
                sent_count += 1
            except Exception as e:
                logger.warning(f"[WebSocket] 广播失败: {e}")
                disconnected_global.add(ws)

        # 发送到所有会话连接
        for session_id, connections in self._connections.items():
            if session_id == exclude_session:
                continue

            for ws in connections:
                try:
                    await ws.send_text(message_json)
                    sent_count += 1
                except Exception as e:
                    logger.warning(f"[WebSocket] 广播失败 (session={session_id}): {e}")
                    if session_id not in disconnected_sessions:
                        disconnected_sessions[session_id] = set()
                    disconnected_sessions[session_id].add(ws)

        # 清理断开的连接
        if disconnected_global or disconnected_sessions:
            async with self._lock:
                self._global_connections -= disconnected_global

                for session_id, ws_set in disconnected_sessions.items():
                    if session_id in self._connections:
                        self._connections[session_id] -= ws_set
                        if not self._connections[session_id]:
                            del self._connections[session_id]

        logger.debug(f"[WebSocket] 广播完成: 发送{sent_count}条")
        return sent_count

    async def send_proactive_message(self, message: str, source: str, session_id: str = None):
        """发送主动消息（ProactiveVision专用）"""
        payload = {
            "type": "proactive_message",
            "content": message,
            "source": source,
            "timestamp": time.time(),
        }
        if session_id:
            payload["session_id"] = session_id

        # 广播到所有连接
        sent_count = await self.broadcast(payload)
        logger.info(f"[WebSocket] 主动消息已推送: {message[:50]}... (发送{sent_count}个连接)")
        return sent_count > 0

    def get_stats(self) -> dict[str, Any]:
        """获取连接统计"""
        total_session_connections = sum(len(conns) for conns in self._connections.values())
        return {
            "total_sessions": len(self._connections),
            "total_session_connections": total_session_connections,
            "global_connections": len(self._global_connections),
            "total_connections": total_session_connections + len(self._global_connections),
        }


# 全局单例
_ws_manager: WebSocketManager = None


_ws_manager_lock = threading.Lock()


def get_websocket_manager() -> WebSocketManager:
    """获取WebSocket管理器单例"""
    global _ws_manager
    if _ws_manager is None:
        with _ws_manager_lock:
            if _ws_manager is None:
                _ws_manager = WebSocketManager()
    return _ws_manager
