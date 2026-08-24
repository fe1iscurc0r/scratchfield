"""
屏幕感知触发器
负责管理冷却时间和发送主动消息
"""

import asyncio
import logging
import time
from typing import Dict, Optional

import httpx

from .config import TriggerRule

logger = logging.getLogger(__name__)


class ProactiveVisionTrigger:
    """主动视觉触发器"""

    def __init__(self):
        self._rule_last_triggered: dict[str, float] = {}
        self._http_client: httpx.AsyncClient | None = None

    def _get_http_client(self) -> httpx.AsyncClient:
        """获取或创建共享 httpx 客户端"""
        if self._http_client is None or self._http_client.is_closed:
            self._http_client = httpx.AsyncClient(timeout=5.0, proxy=None)
        return self._http_client

    async def close(self):
        """关闭共享 httpx 客户端"""
        if self._http_client and not self._http_client.is_closed:
            await self._http_client.aclose()
            self._http_client = None

    async def send_proactive_message(self, rule: TriggerRule, context: str) -> bool:
        """发送主动消息到前端，返回是否成功"""
        from .metrics import get_metrics

        metrics = get_metrics()

        # 检查冷却时间
        if not self._can_trigger(rule):
            logger.debug(f"[ScreenVision] 规则 {rule.name} 处于冷却中")
            return False

        # 渲染消息模板
        message = rule.message_template.format(context=context)

        # 通过消息队列路由（临时屏幕消息 + 队列入队）
        queue_ok = await self._route_via_queue(message, rule.name)

        # 同时保留原有 UI 展示通道（屏幕监测消息需要立即展示给用户）
        display_ok = await self._notify_frontend(message, rule.name)

        success = queue_ok or display_ok

        # 记录metrics
        metrics.record_notification(success)

        if success:
            # 更新触发时间
            self._rule_last_triggered[rule.rule_id] = time.time()
            logger.info(f"[ScreenVision] 触发规则: {rule.name}")
            return True
        else:
            logger.warning(f"[ScreenVision] 规则 {rule.name} 消息发送失败")
            return False

    def _can_trigger(self, rule: TriggerRule) -> bool:
        """检查规则是否可以触发"""
        if rule.rule_id not in self._rule_last_triggered:
            return True

        elapsed = time.time() - self._rule_last_triggered[rule.rule_id]
        return elapsed >= rule.cooldown_seconds

    async def _route_via_queue(self, message: str, source: str) -> bool:
        """通过 api_server 的消息队列路由（设置临时屏幕槽 + 对话中入队）"""
        from system.config import get_server_port

        api_port = get_server_port("api_server")
        try:
            client = self._get_http_client()
            resp = await client.post(
                f"http://localhost:{api_port}/queue/push",
                json={
                    "content": message,
                    "source": "screen_monitor",
                    "metadata": {"rule": source},
                },
            )
            if resp.status_code == 200:
                result = resp.json()
                logger.debug(f"[ScreenVision] 消息队列路由: {result.get('status')}")
                return True
            return False
        except Exception as e:
            logger.warning(f"[ScreenVision] 消息队列路由失败: {e}")
            return False

    async def _notify_frontend(self, message: str, source: str) -> bool:
        """通知前端显示主动消息（优先使用WebSocket，降级HTTP）"""
        from system.config import get_server_port

        api_port = get_server_port("api_server")

        # 尝试通过WebSocket推送
        ws_success = await self._try_websocket_push(message, source, api_port)
        if ws_success:
            return True

        # WebSocket失败，降级到HTTP POST
        logger.debug("[ScreenVision] WebSocket推送失败，降级到HTTP")
        return await self._try_http_push(message, source, api_port)

    async def _try_websocket_push(self, message: str, source: str, api_port: int) -> bool:
        """尝试通过WebSocket推送消息"""
        try:
            # 调用API Server的内部接口触发WebSocket广播
            url = f"http://127.0.0.1:{api_port}/ws/broadcast"
            payload = {
                "type": "proactive_message",
                "content": message,
                "source": f"ScreenVision:{source}",
                "timestamp": time.time()
            }

            client = self._get_http_client()
            resp = await client.post(url, json=payload)
            if resp.status_code == 200:
                result = resp.json()
                sent_count = result.get("sent_count", 0)
                if sent_count > 0:
                    logger.debug(f"[ScreenVision] WebSocket推送成功: {sent_count}个连接")
                    return True
                else:
                    logger.debug("[ScreenVision] 无活跃WebSocket连接")
                    return False
        except Exception as e:
            logger.debug(f"[ScreenVision] WebSocket推送失败: {e}")
            return False

    async def _try_http_push(self, message: str, source: str, api_port: int) -> bool:
        """通过HTTP POST推送消息（降级方案）"""
        import httpx

        url = f"http://127.0.0.1:{api_port}/proactive_message"
        payload = {
            "message": message,
            "source": f"ScreenVision:{source}",
            "timestamp": time.time()
        }

        try:
            client = self._get_http_client()
            resp = await client.post(url, json=payload)
            if resp.status_code == 200:
                logger.debug(f"[ScreenVision] HTTP推送成功: {message[:50]}...")
                return True
            else:
                logger.warning(f"[ScreenVision] HTTP响应异常: {resp.status_code}")
                return False
        except httpx.ConnectError:
            logger.warning("[ScreenVision] 无法连接到API服务器，请检查服务是否启动")
            return False
        except httpx.TimeoutException:
            logger.warning("[ScreenVision] HTTP推送超时")
            return False
        except Exception as e:
            logger.error(f"[ScreenVision] HTTP推送失败: {e}")
            return False

    def reset_cooldown(self, rule_id: str):
        """重置指定规则的冷却时间（用于测试或手动重置）"""
        if rule_id in self._rule_last_triggered:
            del self._rule_last_triggered[rule_id]
            logger.info(f"[ScreenVision] 已重置规则 {rule_id} 的冷却时间")

    def get_cooldown_remaining(self, rule: TriggerRule) -> float:
        """获取规则剩余冷却时间（秒）"""
        if rule.rule_id not in self._rule_last_triggered:
            return 0.0

        elapsed = time.time() - self._rule_last_triggered[rule.rule_id]
        remaining = rule.cooldown_seconds - elapsed
        return max(0.0, remaining)


# 全局单例
_trigger: ProactiveVisionTrigger | None = None


def get_proactive_trigger() -> ProactiveVisionTrigger | None:
    """获取触发器单例"""
    return _trigger


def create_proactive_trigger() -> ProactiveVisionTrigger:
    """创建并注册触发器单例"""
    global _trigger
    if _trigger is not None:
        logger.warning("[ScreenVision] 触发器已存在，将被替换")

    _trigger = ProactiveVisionTrigger()
    return _trigger
