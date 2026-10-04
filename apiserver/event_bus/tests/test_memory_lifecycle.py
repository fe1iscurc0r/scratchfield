"""W120-03 验收：记忆事件化 + 分层（发布/消费/分层提升/配置）。

对应工单验收：
- 写入记忆 → 总线收到 MEMORY_CREATED（本地与模拟远程两路），payload 字段齐全
- lifespan 注册消费者（此处验证注册函数 + 消费者钩子可用）
- 分层规则可配且触发 MEMORY_ARCHIVED 事件
- 原记忆链路不回退（本地提取失败只记日志、不抛）
"""
from __future__ import annotations

import asyncio

from apiserver.event_bus import InProcessEventBus, Topics
from apiserver.event_bus.handlers import register_summer_memory_consumer
from apiserver.event_bus.memory_lifecycle import (
    MemoryLayering,
    SummerMemoryConsumer,
    register_compression_hint,
)


def test_memory_layering_promotes_on_capacity():
    bus = InProcessEventBus()
    archived: list[dict] = []
    bus.on(Topics.MEMORY_ARCHIVED, lambda e: archived.append(e))

    layering = MemoryLayering(bus, enabled=True, max_short_term=3, promote_after_seconds=3600)
    for i in range(5):
        layering.on_memory_created({"memory_id": f"m{i}", "summary": f"记忆{i}", "source": "local"})

    assert layering.stats()["short_term"] == 3
    assert layering.promoted_total == 2  # 前两条被提升
    assert [e["memory_id"] for e in archived] == ["m0", "m1"]
    assert all(e["reason"].startswith("layering:") and e["layer"] == "long_term" for e in archived)


def test_memory_layering_promotes_on_time_sweep():
    bus = InProcessEventBus()
    archived: list[dict] = []
    bus.on(Topics.MEMORY_ARCHIVED, lambda e: archived.append(e))

    layering = MemoryLayering(bus, enabled=True, max_short_term=10, promote_after_seconds=60)
    layering.on_memory_created({"memory_id": "old", "ts": 1.0})  # 很久以前
    layering.on_memory_created({"memory_id": "new"})
    promoted = layering.sweep()

    assert [p["memory_id"] for p in promoted] == ["old"]
    assert archived and archived[0]["reason"] == "layering:time"
    assert layering.stats()["short_term"] == 1


def test_consumer_registration_and_compression_hook():
    bus = InProcessEventBus()
    consumer = SummerMemoryConsumer(bus, layering=MemoryLayering(bus, max_short_term=2))
    register_summer_memory_consumer(bus, consumer)  # 与 lifespan 同一注册函数
    consumer.bus.on(Topics.MEMORY_ARCHIVED, consumer.on_memory_archived)  # lifespan 同款订阅

    hints: list[dict] = []
    register_compression_hint(consumer, lambda ev: hints.append(ev))

    bus.emit(Topics.MEMORY_CREATED, {"memory_id": "a", "summary": "一"})
    bus.emit(Topics.MEMORY_CREATED, {"memory_id": "b", "summary": "二"})
    bus.emit(Topics.MEMORY_CREATED, {"memory_id": "c", "summary": "三"})  # 超容量 → 提升 a
    assert consumer.created_seen == 3
    assert consumer.stats()["layering_promoted_total"] >= 1
    # 提升产生的 MEMORY_ARCHIVED 事件被压缩钩子收到
    assert hints and hints[0]["memory_id"] == "a"

    bus.emit(Topics.MEMORY_ARCHIVED, {"memory_id": "b"})
    assert consumer.archived_seen >= 2
    assert "b" in consumer.layering._long_ids


def test_message_manager_emits_memory_created_local_and_remote(monkeypatch):
    """两条写入路径都会发 MEMORY_CREATED；本地提取失败不抛（原链路不回退）。"""
    from apiserver import message_manager as mm_mod

    bus = InProcessEventBus()
    received: list[dict] = []
    bus.on(Topics.MEMORY_CREATED, lambda e: received.append(e))
    monkeypatch.setattr(mm_mod, "get_bus", lambda: bus, raising=False)
    # message_manager 内部用 `from apiserver.event_bus import get_bus` → 打补丁到包上
    import apiserver.event_bus as bus_pkg

    monkeypatch.setattr(bus_pkg, "get_bus", lambda: bus)

    manager = mm_mod.MessageManager.__new__(mm_mod.MessageManager)

    # 远程路径
    class FakeRemote:
        async def add_memory(self, user_message, assistant_response):
            return {"success": True, "memory_id": "remote-1"}

    asyncio.run(manager._add_memory_remote_only(FakeRemote(), "木质素碳化温度", "600-800°C"))

    # 本地路径（成功 → emit；失败 → 只记日志不抛）
    class FakeLocal:
        def __init__(self, fail=False):
            self.fail = fail

        async def add_conversation_memory(self, user_message, assistant_response):
            if self.fail:
                raise RuntimeError("提取失败")

    asyncio.run(manager._local_memory_and_emit(FakeLocal(), "导电水凝胶", "戊二醛交联"))
    asyncio.run(manager._local_memory_and_emit(FakeLocal(fail=True), "失败用例", "不应发事件"))

    assert len(received) == 2
    assert received[0]["source"] == "remote" and received[0]["memory_id"] == "remote-1"
    assert received[1]["source"] == "local"
    assert all({"id", "memory_id", "source", "summary", "ts"} <= set(e) for e in received)


def test_layering_config_defaults():
    import sys

    sys.path.insert(0, ".")
    from system.config import get_config

    layering = get_config().memory.layering
    assert layering.enabled is True
    assert layering.max_short_term >= 1
    assert layering.promote_after_seconds >= 60
