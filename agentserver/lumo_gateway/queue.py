"""消息队列：asyncio.Queue + 消费者任务 + 背压。

背压策略（照 SPEC-11 风险#6）：
  - 队列上限 queue_maxsize
  - 满时丢弃最旧消息，累计 dropped 计数 + 日志告警
  - 消费者异常不中断消费循环（降级纪律）
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable

from .models import InboundMessage

logger = logging.getLogger("lumo_gateway.queue")


class MessageQueue:
    """有界 asyncio 队列 + 单消费者任务。"""

    def __init__(self, maxsize: int = 1024) -> None:
        self.maxsize = maxsize
        self._queue: asyncio.Queue[InboundMessage] = asyncio.Queue(maxsize=maxsize)
        self.enqueued = 0  # 累计成功入队
        self.dropped = 0  # 累计因背压丢弃
        self._consumer_task: asyncio.Task | None = None
        self._handler: Callable[[InboundMessage], Awaitable[None]] | None = None

    async def put(self, msg: InboundMessage) -> bool:
        """入队；队列满时丢弃最旧（FIFO 背压），返回是否最终入队。"""
        try:
            self._queue.put_nowait(msg)
            self.enqueued += 1
            return True
        except asyncio.QueueFull:
            # 背压：丢弃最旧，给新消息腾位
            try:
                dropped_msg = self._queue.get_nowait()
                self._queue.task_done()
            except asyncio.QueueEmpty:  # pragma: no cover - 竞态防御
                dropped_msg = None
            self.dropped += 1
            logger.warning(
                "[queue] 背压：队列已满（max=%d），丢弃最旧消息 msg_id=%s，累计丢弃 %d",
                self.maxsize, getattr(dropped_msg, "msg_id", "?"), self.dropped,
            )
            try:
                self._queue.put_nowait(msg)
                self.enqueued += 1
                return True
            except asyncio.QueueFull:  # pragma: no cover - 腾位后理论不可达
                self.dropped += 1
                logger.error("[queue] 背压：队列仍满，消息 msg_id=%s 被丢弃（累计 %d）", msg.msg_id, self.dropped)
                return False

    def start_consumer(self, handler: Callable[[InboundMessage], Awaitable[None]]) -> None:
        """启动消费者任务。handler 为异步处理函数（路由 → lumo → 回投）。"""
        self._handler = handler
        self._consumer_task = asyncio.create_task(self._consume(), name="lumo-gateway-consumer")

    async def _consume(self) -> None:
        while True:
            msg = await self._queue.get()
            try:
                if self._handler:
                    await self._handler(msg)
            except Exception as e:  # noqa: BLE001  # 消费者异常不中断循环（降级纪律）
                logger.exception("[queue] 消费者处理消息 %s 失败: %s", msg.msg_id, e)
            finally:
                self._queue.task_done()

    async def join(self) -> None:
        """等待队列清空（测试用）。"""
        await self._queue.join()

    async def stop(self) -> None:
        if self._consumer_task:
            self._consumer_task.cancel()
            try:
                await self._consumer_task
            except asyncio.CancelledError:
                pass
            self._consumer_task = None
