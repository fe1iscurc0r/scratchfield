"""R29 验收测试：频谱事件长历史查询原型。

覆盖：
  1. 近期全量：recent_events 返回最近 capacity 内的事件
  2. 长历史：count_between 能查到远超容量的早期事件
  3. 朴素环形缓存对比：早期时段朴素缓存为 0，环状强制记忆 > 0
  4. 内存有界：recent 长度不超过 capacity

运行：python -m pytest mcpserver/rf_brain/prototypes/test_ring_forced_memory.py -q
"""
from __future__ import annotations

import pytest

from . import ring_forced_memory as rfm


@pytest.fixture(scope="module")
def mem():
    m = rfm.RingForcedMemory(capacity=10, bucket_seconds=60.0)
    for i in range(1000):
        m.push(rfm.Event(timestamp=float(i), event_type="appear"))
    return m


def test_recent_full_detail(mem):
    recent = mem.recent_events(5)
    assert [int(e.timestamp) for e in recent] == [995, 996, 997, 998, 999]


def test_long_history_query(mem):
    # 早期时段（远超容量）仍可查询
    assert mem.count_between(0, 200) > 0


def test_naive_ring_would_return_zero(mem):
    # 朴素环形缓存（容量 10）只能保留最后 10 个事件，早期时段为 0
    naive = [e for e in mem.recent if e.timestamp <= 200]
    assert len(naive) == 0
    assert mem.count_between(0, 200) > 0  # 环状强制记忆保留早期


def test_memory_bounded(mem):
    assert len(mem.recent) <= mem.capacity
