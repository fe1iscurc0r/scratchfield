"""queue 背压测试：队列上限 + 丢弃最旧 + 消费者处理。"""

from __future__ import annotations

import asyncio

from agentserver.lumo_gateway.models import InboundMessage
from agentserver.lumo_gateway.queue import MessageQueue


def _msg(i: int) -> InboundMessage:
    return InboundMessage(platform="qq", msg_id=f"m{i}", user_id="u1", content=f"内容{i}")


def test_backpressure_drops_oldest_when_full() -> None:
    """队列满时丢弃最旧消息（FIFO 背压），并统计 dropped/enqueued。"""

    async def scenario() -> None:
        q = MessageQueue(maxsize=2)
        assert await q.put(_msg(1)) is True  # 队列: [m1]
        assert await q.put(_msg(2)) is True  # 队列: [m1, m2]
        # 第 3 条触发背压：丢 m1，入 m3 → [m2, m3]
        assert await q.put(_msg(3)) is True
        assert q.dropped == 1
        assert q.enqueued == 3
        # 第 4 条再触发：丢 m2，入 m4 → [m3, m4]
        assert await q.put(_msg(4)) is True
        assert q.dropped == 2
        assert q.enqueued == 4
        # 队列内剩最新两条，顺序 FIFO
        assert (await q._queue.get()).msg_id == "m3"
        assert (await q._queue.get()).msg_id == "m4"

    asyncio.run(scenario())


def test_consumer_handles_messages_in_order() -> None:
    """消费者按 FIFO 顺序处理入队消息。"""

    async def scenario() -> None:
        q = MessageQueue(maxsize=4)
        seen: list[str] = []

        async def handler(msg: InboundMessage) -> None:
            seen.append(msg.msg_id)

        q.start_consumer(handler)
        for i in range(3):
            await q.put(_msg(i))
        await q.join()
        await q.stop()
        assert seen == ["m0", "m1", "m2"]

    asyncio.run(scenario())


def test_consumer_exception_does_not_stop_loop() -> None:
    """消费者内 handler 抛异常不中断消费循环（降级纪律）。"""

    async def scenario() -> None:
        q = MessageQueue(maxsize=4)
        seen: list[str] = []

        async def handler(msg: InboundMessage) -> None:
            if msg.msg_id == "m0":
                raise RuntimeError("boom")
            seen.append(msg.msg_id)

        q.start_consumer(handler)
        for i in range(3):
            await q.put(_msg(i))
        await q.join()
        await q.stop()
        assert seen == ["m1", "m2"]

    asyncio.run(scenario())
