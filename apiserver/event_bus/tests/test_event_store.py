"""W119-02 验收：事件持久化 + 回放（写入回放 / 轮转 / 容错 / 配置开关）。

对应工单验收：
- 写入后重开 EventStore 可回放
- 非法 JSON 行跳过并记 warning（日志不中断）
- 写盘失败降级不抛
- 配置关闭时零写盘
"""
from __future__ import annotations

import json
import time
from collections import deque
from pathlib import Path

from apiserver.event_bus import InProcessEventBus, build_envelope
from apiserver.event_bus.event_store import EventStore, reset_event_store_for_tests


def _mk(tmp_path: Path, **kwargs) -> EventStore:
    params = dict(buffer_lines=1, max_bytes=64 * 1024, keep_files=3)
    params.update(kwargs)
    return EventStore(tmp_path / "event_store" / "events.jsonl", **params)


def test_write_then_replay_after_reopen(tmp_path):
    """写入 → 关闭 → 重开同一个文件 → 仍可回放（含 topic/since/limit 过滤）。"""
    store = _mk(tmp_path)
    for i in range(5):
        store.append(build_envelope("t.alpha", "emit", {"i": i}))
    store.append(build_envelope("t.beta", "waterfall", {"x": 1}))
    store.close()

    reopened = _mk(tmp_path)
    all_events = list(reopened.replay())
    assert len(all_events) == 6
    assert {"id", "topic", "mode", "source", "trace_id", "timestamp", "payload"} <= set(all_events[0])

    only_alpha = list(reopened.replay(topic="t.alpha"))
    assert len(only_alpha) == 5 and all(e["topic"] == "t.alpha" for e in only_alpha)

    # replay 是「从最早开始」的流式迭代，limit = 最多取前 N 条（文档语义）
    first_two = list(reopened.replay(limit=2))
    assert len(first_two) == 2 and first_two[0]["payload"]["i"] == 0

    # 取「最近 N 条」由调用方做尾部窗口（/debug/dump/bus/history 端点即此实现）
    window: deque = deque(maxlen=2)
    for item in reopened.replay():
        window.append(item)
    tail = list(window)
    assert tail[-1]["payload"]["x"] == 1

    none_recent = list(reopened.replay(since_ts=time.time() + 60))
    assert none_recent == []
    reopened.close()


def test_rotation_and_prune(tmp_path):
    """单文件超 max_bytes 触发轮转，且只保留 keep_files 个历史文件。"""
    store = _mk(tmp_path, max_bytes=64 * 1024, keep_files=2, buffer_lines=1)
    big = "x" * 800
    for i in range(400):  # 400 * ~900B ≈ 360KB → 多次轮转
        store.append(build_envelope("t.big", "emit", {"i": i, "blob": big}))
    store.close()

    stats = store.stats()
    assert stats["rotations"] >= 2
    rotated = sorted(store.path.parent.glob(f"{store.path.stem}.*{store.path.suffix}"))
    assert len(rotated) <= 2  # keep_files 生效
    # 当前文件 + 历史文件仍可回放
    assert len(list(store.replay(limit=10_000))) > 0


def test_bad_lines_are_skipped(tmp_path):
    """非法 JSON 行与空行被跳过，不中断回放（bad_lines 计数）。"""
    store = _mk(tmp_path)
    store.append(build_envelope("t.ok", "emit", {"i": 1}))
    store.close()

    with open(store.path, "a", encoding="utf-8") as fh:
        fh.write("这不是 JSON\n")
        fh.write("\n")
        fh.write(json.dumps({"topic": "t.ok", "mode": "emit"}) + "\n")

    events = list(store.replay())
    assert len(events) == 2  # 两行合法
    assert store.stats()["bad_lines"] == 1


def test_disabled_store_writes_nothing(tmp_path):
    """配置关闭时零写盘（append 是 no-op，不创建文件）。"""
    store = _mk(tmp_path, enabled=False)
    store.append(build_envelope("t.off", "emit", {"i": 1}))
    store.close()
    assert not store.path.exists()
    assert store.stats()["written"] == 0


def test_degrade_on_unwritable_path(tmp_path):
    """写盘失败（路径不可写）→ 降级为内存-only，不抛异常。"""
    blocked = tmp_path / "blocked"
    blocked.mkdir()
    blocker = blocked / "events.jsonl"
    blocker.mkdir()  # 占位成目录 → 写文件必失败
    store = EventStore(blocker, buffer_lines=1)
    for i in range(3):
        store.append(build_envelope("t.degrade", "emit", {"i": i}))
    store.close()
    assert store.stats()["degraded"] is True


def test_bus_dispatch_persists_envelope(tmp_path):
    """总线分发自动落盘：emit 后能回放到同一 topic 的信封（含 mode/trace_id）。"""
    store = _mk(tmp_path)
    reset_event_store_for_tests(store)
    try:
        bus = InProcessEventBus()
        bus.on("t.wire", lambda e: None)
        bus.emit("t.wire", {"hello": "world"})

        assert store.flush(timeout=3.0)
        events = list(store.replay(topic="t.wire"))
        assert len(events) == 1
        envelope = events[0]
        assert envelope["mode"] == "emit"
        assert envelope["payload"] == {"hello": "world"}
        assert len(envelope["trace_id"]) == 32
    finally:
        reset_event_store_for_tests(None)
