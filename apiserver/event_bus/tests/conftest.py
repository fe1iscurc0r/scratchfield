"""测试隔离：总线测试不得写进用户真实的事件日志 / 审计日志。

背景（W119-02 自测发现）：总线 `_dispatch` 会自动把事件落盘到 `get_event_store()`，
而单例默认指向 `<user_data>/event_store/events.jsonl`；若测试直接 `bus.emit(...)`，
就会把 `t` / `test` / `gate` 这类测试 topic 灌进用户的真实审计日志（实测污染 1600+ 行）。
本 conftest 为每个用例换一个 tmp 事件存储，用完还原。
"""
from __future__ import annotations

import pytest

from apiserver.event_bus.event_store import EventStore, reset_event_store_for_tests


@pytest.fixture(autouse=True)
def _isolated_event_store(tmp_path):
    store = EventStore(tmp_path / "isolated_event_store" / "events.jsonl", buffer_lines=50)
    reset_event_store_for_tests(store)
    try:
        yield store
    finally:
        store.close(timeout=1.0)
        reset_event_store_for_tests(None)
